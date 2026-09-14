"""Claude hook normalization, with an explicit legacy synthetic mode."""

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
import shlex

from architect.recorder.events import ArchitectEvent


def _required(payload: Mapping, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing or invalid {key}")
    return value


def _pytest(command: str) -> bool:
    # Conservative: do not interpret shell composition, expansion, or wrappers.
    if any(char in command for char in ";|&<>`$\n\r"):
        return False
    try:
        args = shlex.split(command)
    except ValueError:
        return False
    return bool(args) and (args[0] == "pytest" or
        (args[:3] in (["python", "-m", "pytest"], ["python3", "-m", "pytest"])))


class ClaudeObserver:
    def __init__(self, *, live: bool = False):
        self.live = live

    def normalize(self, payload: Mapping, *, run_id: str) -> list[ArchitectEvent]:
        if not isinstance(payload, Mapping):
            raise ValueError("Provider payload must be an object")
        name = _required(payload, "hook_event_name")
        if name not in {"SessionStart", "Stop", "SessionEnd", "PostToolUse", "PostToolUseFailure"}:
            return []
        session = _required(payload, "session_id")
        if self.live and name in {"SessionStart", "Stop", "SessionEnd"}:
            return []  # Session binding is not evidence of Architect run completion.
        timestamp = (datetime.now(timezone.utc).isoformat() if self.live
                     else _required(payload, "timestamp"))
        metadata = {"provider_event_name": name, "provider_session_id": session,
                    "synthetic": not self.live}
        if self.live:
            metadata["timestamp_source"] = "hook_received_at"
            for key in ("tool_use_id", "cwd", "permission_mode", "is_interrupt"):
                if key in payload:
                    metadata[key] = deepcopy(payload[key])
        for key in ("hook_source", "tool_response", "error"):
            if key in payload:
                metadata[key] = deepcopy(payload[key])
        tool = target = status = None
        if name in {"SessionStart", "Stop", "SessionEnd"}:
            # Explicit synthetic evidence relates THIS run to a session boundary.
            if payload.get("run_scope") != "bound_run":
                return []
            if name == "SessionStart":
                if payload.get("run_started") is not True:
                    return []
                event_type = "run_started"
            else:
                outcome = payload.get("run_outcome")
                if outcome not in ("SUCCESS", "FAILED", "CANCELLED"):
                    return []
                event_type = "run_finished"
                metadata["run_status"] = outcome
                status = {"SUCCESS": "success", "FAILED": "failed", "CANCELLED": "blocked"}[outcome]
        else:
            native_tool = _required(payload, "tool_name")
            inputs = payload.get("tool_input")
            if not isinstance(inputs, dict):
                raise ValueError("tool_input must be an object")
            metadata.update(native_tool_name=native_tool, tool_input=deepcopy(inputs))
            if name == "PostToolUseFailure":
                event_type, status = "tool_execution", "failed"
            elif native_tool == "Read":
                target = _required(inputs, "file_path")
                event_type = "file_read"
            elif native_tool == "Bash":
                command = _required(inputs, "command")
                metadata["command"] = command
                event_type = "test_execution" if _pytest(command) else "tool_execution"
            else:
                return []
            tool = {"Read": "read", "Bash": "shell"}.get(native_tool)
            if self.live and name == "PostToolUse" and native_tool == "Read":
                status = "success"
            # PostToolUse does not itself prove a command/test exit status.
        return [ArchitectEvent(run_id, event_type, timestamp=timestamp, provider="claude",
                               fidelity="NATIVE", tool=tool, target=target, status=status,
                               metadata=metadata)]
