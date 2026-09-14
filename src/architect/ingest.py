"""Synchronous synthetic ingestion through the observer/recorder boundary."""

from collections.abc import Mapping
from pathlib import Path
from architect.observers.base import Observer
from architect.observers.claude import ClaudeObserver
from architect.observers.codex import CODEX_EVENT_NAMES, CodexObserver, codex_session_id
from architect.recorder.recorder import FlightRecorder
from architect.storage.sessions import bind_session, resolve_session


def ingest(provider: str, payload: Mapping, *, db_path: str | Path,
           live: bool = False, run_id: str | None = None) -> list[str]:
    if provider not in {"claude", "codex"}:
        raise ValueError(f"Unsupported provider: {provider}")
    if not isinstance(payload, Mapping):
        raise ValueError("Provider payload must be an object")
    if provider == "codex" and live:
        raise ValueError("Live Codex transport is not implemented")
    if provider == "claude" and live:
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
    if provider == "codex":
        if payload.get("event_name") not in CODEX_EVENT_NAMES:
            return []
        session_id = codex_session_id(payload)
        observer: Observer = CodexObserver()
    else:
        session_id = payload.get("session_id")
        observer = ClaudeObserver(live=live)
    run_id = resolve_session(provider, session_id, db_path=db_path)
    events = observer.normalize(payload, run_id=run_id)
    recorder = FlightRecorder(db_path)
    return [recorder.record(event) for event in events]
