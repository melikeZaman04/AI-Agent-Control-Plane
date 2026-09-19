"""Atomic event persistence and minimal run lifecycle."""

import json
from pathlib import Path

from architect.recorder.events import ArchitectEvent, EVENT_TYPES
from architect.storage.db import _connect, initialize_database


class FlightRecorder:
    def __init__(self, db_path: str | Path):
        self.database = initialize_database(db_path)

    def record(self, event: ArchitectEvent) -> str:
        payload = event.to_json()
        with _connect(self.database) as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT status FROM runs WHERE run_id = ?", (event.run_id,)
            ).fetchone()
            if run is None:
                raise ValueError(f"Unknown run: {event.run_id}")
            duplicate = connection.execute(
                "SELECT 1 FROM events WHERE json_valid(payload) AND "
                "json_extract(payload, '$.event_id') = ?", (event.event_id,)
            ).fetchone()
            if duplicate:
                raise ValueError(f"Duplicate event_id: {event.event_id}")
            if event.event_type == "run_started":
                if run[0] not in {"PENDING", "RUNNING"}:
                    raise ValueError("Cannot start a terminal run")
                if connection.execute(
                    "SELECT 1 FROM events WHERE run_id = ? AND event_type = 'run_started'",
                    (event.run_id,),
                ).fetchone():
                    raise ValueError("Run start already recorded")
                connection.execute(
                    "UPDATE runs SET status = 'RUNNING', started_at = ? WHERE run_id = ?",
                    (event.timestamp, event.run_id),
                )
            elif event.event_type == "run_finished":
                outcome = event.metadata.get("run_status")
                expected = {"SUCCESS": "success", "FAILED": "failed", "CANCELLED": "blocked"}
                if outcome not in expected or event.status != expected[outcome]:
                    raise ValueError("run_finished requires consistent status and metadata.run_status")
                if run[0] not in {"PENDING", "RUNNING"}:
                    raise ValueError("Run is already terminal")
                connection.execute(
                    "UPDATE runs SET status = ?, ended_at = ? WHERE run_id = ?",
                    (outcome, event.timestamp, event.run_id),
                )
            connection.execute(
                "INSERT INTO events (run_id, timestamp, event_type, target, payload) "
                "VALUES (?, ?, ?, ?, ?)",
                (event.run_id, event.timestamp, event.event_type, event.target, payload),
            )
        return event.event_id

    def start_run(self, run_id: str) -> str:
        return self.record(ArchitectEvent(run_id, "run_started"))

    def finish_run(self, run_id: str, status: str = "SUCCESS") -> str:
        status = status.upper()
        event_status = {"SUCCESS": "success", "FAILED": "failed", "CANCELLED": "blocked"}
        if status not in event_status:
            raise ValueError("Invalid terminal status")
        return self.record(ArchitectEvent(
            run_id, "run_finished", status=event_status[status], metadata={"run_status": status},
        ))

    def timeline(self, run_id: str) -> list[ArchitectEvent]:
        with _connect(self.database) as connection:
            rows = connection.execute(
                "SELECT id, payload, event_type FROM events WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        return normalized_timeline(rows, run_id=run_id)


def normalized_timeline(rows, *, run_id: str | None = None) -> list[ArchitectEvent]:
    """Decode (insertion ID, payload[, stored type]) rows, validating identity.

    Recorder writes lowercase normalized types; M0 log_event writes uppercase.
    Imported JSON with at least three envelope keys is also recognizable as
    normalized evidence. Unrecognizable legacy content stays stored but omitted.
    No missing required field may be supplied by dataclass defaults on reads.
    """
    events = []
    seen = set()
    required = {"event_id", "run_id", "event_type", "timestamp"}
    for row in rows:
        insertion_id, payload = row[:2]
        stored_type = row[2] if len(row) > 2 else None
        normalized_row = stored_type in EVENT_TYPES
        try:
            data = json.loads(payload)
        except (TypeError, ValueError) as error:
            if normalized_row:
                raise ValueError(f"Invalid normalized evidence at row {insertion_id}") from error
            continue  # M0 free-text payloads are not normalized events.
        envelope_keys = required.intersection(data) if isinstance(data, dict) else set()
        if not normalized_row and len(envelope_keys) < 3:
            continue
        if envelope_keys != required:
            raise ValueError(f"Incomplete normalized evidence at row {insertion_id}")
        try:
            event = ArchitectEvent(**data)
        except (ValueError, TypeError) as error:
            raise ValueError(f"Invalid normalized evidence at row {insertion_id}") from error
        if (run_id is not None and event.run_id != run_id) or event.event_id in seen:
            raise ValueError("Inconsistent normalized evidence identity")
        if normalized_row and event.event_type != stored_type:
            raise ValueError(f"Inconsistent normalized event type at row {insertion_id}")
        seen.add(event.event_id)
        events.append((event, insertion_id))
    events.sort(key=lambda pair: (pair[0].timestamp, pair[1]))
    return [event for event, _ in events]
