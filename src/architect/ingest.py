"""Synchronous synthetic ingestion through the observer/recorder boundary."""

from collections.abc import Mapping
from pathlib import Path
from architect.observers.base import Observer
from architect.observers.claude import ClaudeObserver
from architect.recorder.recorder import FlightRecorder
from architect.storage.sessions import bind_session, resolve_session


def ingest(provider: str, payload: Mapping, *, db_path: str | Path,
           live: bool = False, run_id: str | None = None) -> list[str]:
    if provider != "claude":
        raise ValueError(f"Unsupported provider: {provider}")
    if not isinstance(payload, Mapping):
        raise ValueError("Provider payload must be an object")
    if live:
        name = payload.get("hook_event_name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Missing or invalid hook_event_name")
        if name not in {"SessionStart", "PostToolUse", "PostToolUseFailure", "Stop", "SessionEnd"}:
            return []
        if name == "SessionStart":
            if not isinstance(run_id, str) or not run_id.strip():
                raise ValueError("SessionStart requires ARCHITECT_RUN_ID (full existing run ID)")
            bind_session(provider, payload.get("session_id"), run_id, db_path=db_path)
            return []
    run_id = resolve_session(provider, payload.get("session_id"), db_path=db_path)
    observer: Observer = ClaudeObserver(live=live)
    events = observer.normalize(payload, run_id=run_id)
    recorder = FlightRecorder(db_path)
    return [recorder.record(event) for event in events]
