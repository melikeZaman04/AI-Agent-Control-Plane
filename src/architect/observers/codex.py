"""Normalize the documented Codex OTel event families from synthetic records."""

from collections.abc import Mapping
from copy import deepcopy
import shlex

from architect.recorder.events import ArchitectEvent


_SENSITIVE_ATTRIBUTE_PARTS = (
    "authorization",
    "content",
    "key",
    "output",
    "password",
    "prompt",
    "secret",
    "token",
)
CODEX_EVENT_NAMES = frozenset({"codex.tool_result", "codex.tool_decision"})


def _required_string(values: Mapping, key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing or invalid {key}")
    return value


def _is_pytest(command: str) -> bool:
    if any(character in command for character in ";|&<>`$\n\r"):
        return False
    try:
        arguments = shlex.split(command)
    except ValueError:
        return False
    return bool(arguments) and (
        arguments[0] == "pytest"
        or arguments[:3] in (["python", "-m", "pytest"], ["python3", "-m", "pytest"])
    )


def _audit_attributes(attributes: Mapping) -> tuple[dict, list[str]]:
    retained = {}
    omitted = []
    for key, value in attributes.items():
        if not isinstance(key, str):
            raise ValueError("Codex attribute keys must be strings")
        lowered = key.lower()
        if any(part in lowered for part in _SENSITIVE_ATTRIBUTE_PARTS):
            omitted.append(key)
        else:
            retained[key] = deepcopy(value)
    return retained, sorted(omitted)


def codex_session_id(payload: Mapping) -> str:
    """Return the documented conversation identifier without treating it as a run ID."""
    if not isinstance(payload, Mapping):
        raise ValueError("Codex telemetry record must be an object")
    attributes = payload.get("attributes")
    if not isinstance(attributes, Mapping):
        raise ValueError("Codex telemetry attributes must be an object")
    return _required_string(attributes, "conversation.id")


class CodexObserver:
    """Translate a narrow synthetic representation of Codex OTel log records."""

    def normalize(self, payload: Mapping, *, run_id: str) -> list[ArchitectEvent]:
        if not isinstance(payload, Mapping):
            raise ValueError("Codex telemetry record must be an object")
        event_name = _required_string(payload, "event_name")

        # These documented event families do not map to current cross-provider events.
        if event_name not in CODEX_EVENT_NAMES:
            return []

        timestamp = _required_string(payload, "timestamp")
        attributes = payload.get("attributes")
        if not isinstance(attributes, Mapping):
            raise ValueError("Codex telemetry attributes must be an object")
        session_id = _required_string(attributes, "conversation.id")
        retained, omitted = _audit_attributes(attributes)
        metadata = {
            "native_event_name": event_name,
            "provider_session_id": session_id,
            "synthetic": True,
            "telemetry_source": "opentelemetry_log",
            "otel_attributes": retained,
        }
        if omitted:
            metadata["sensitive_attributes_omitted"] = omitted

        if event_name == "codex.tool_decision":
            decision = _required_string(attributes, "decision")
            decision_status = {
                "approved": "success",
                "approved_for_session": "success",
                "approved_with_amendment": "success",
                "denied": "blocked",
                "abort": "blocked",
            }
            if decision not in decision_status:
                raise ValueError("Unknown Codex approval decision")
            metadata["approval_decision"] = decision
            event_type = "approval_requested"
            status = decision_status[decision]
            tool = attributes.get("tool_name")
            duration_ms = None
        else:
            tool = _required_string(attributes, "tool_name")
            success = attributes.get("success")
            if not isinstance(success, bool):
                raise ValueError("Codex tool_result success must be boolean")
            status = "success" if success else "failed"
            duration_ms = attributes.get("duration_ms")
            command = attributes.get("command")
            if command is not None and not isinstance(command, str):
                raise ValueError("Codex command must be a string")
            event_type = "test_execution" if command and _is_pytest(command) else "tool_execution"
            if command:
                metadata["command"] = command

        return [
            ArchitectEvent(
                run_id=run_id,
                event_type=event_type,
                timestamp=timestamp,
                provider="codex",
                fidelity="NATIVE",
                actor="agent",
                tool=tool,
                status=status,
                duration_ms=duration_ms,
                metadata=metadata,
            )
        ]
