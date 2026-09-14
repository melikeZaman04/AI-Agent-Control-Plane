"""Normalized event contract; no provider-specific formats belong here."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import math
from uuid import uuid4

EVENT_TYPES = frozenset({
    "run_started", "run_finished", "tool_execution", "file_read",
    "file_changed", "test_execution", "approval_requested", "error",
})
EVENT_STATUSES = frozenset({"pending", "success", "failed", "blocked"})


def utc_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _json_value(value):
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float) and math.isfinite(value):
        return
    if isinstance(value, list):
        for item in value:
            _json_value(item)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _json_value(item)
        return
    raise ValueError("metadata must contain JSON values and string keys")


@dataclass(frozen=True)
class ArchitectEvent:
    run_id: str
    event_type: str
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    provider: str | None = None
    fidelity: str | None = None
    actor: str | None = None
    tool: str | None = None
    target: str | None = None
    status: str | None = None
    duration_ms: float | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        self.validate()
        object.__setattr__(self, "timestamp", utc_timestamp(self.timestamp))

    def validate(self):
        for name in ("run_id", "event_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be a nonempty string")
        if self.event_type not in EVENT_TYPES:
            raise ValueError("Unknown normalized event_type")
        if self.status is not None and self.status not in EVENT_STATUSES:
            raise ValueError("Invalid event status")
        if self.fidelity not in (None, "NATIVE", "SESSION_LOG", "PASSIVE"):
            raise ValueError("Invalid fidelity")
        for name in ("provider", "actor", "tool", "target"):
            if getattr(self, name) is not None and not isinstance(getattr(self, name), str):
                raise ValueError(f"{name} must be a string")
        if self.duration_ms is not None and (
            isinstance(self.duration_ms, bool)
            or not isinstance(self.duration_ms, (float, int))
            or not math.isfinite(self.duration_ms) or self.duration_ms < 0
        ):
            raise ValueError("duration_ms must be finite and nonnegative")
        utc_timestamp(self.timestamp)
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a JSON object")
        _json_value(self.metadata)

    def to_json(self) -> str:
        self.validate()
        return json.dumps(asdict(self), sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False)
