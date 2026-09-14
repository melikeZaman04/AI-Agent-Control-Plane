"""Atomic event persistence and minimal run lifecycle."""

import json
from pathlib import Path

from architect.recorder.events import ArchitectEvent
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
                "SELECT id, payload FROM events WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        return normalized_timeline(rows)


def normalized_timeline(rows) -> list[ArchitectEvent]:
    """Decode stored (insertion ID, payload) pairs using the recorder contract.

    Legacy payloads are not normalized evidence. Invalid normalized envelopes
    raise instead of silently erasing evidence. Callers may use a SQLite snapshot.
    """
    events = []
    for insertion_id, payload in rows:
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            continue  # M0 free-text payloads are not normalized events.
        if isinstance(data, dict) and {"event_id", "run_id", "event_type", "timestamp"} <= data.keys():
            events.append((ArchitectEvent(**data), insertion_id))
    events.sort(key=lambda pair: (pair[0].timestamp, pair[1]))
    return [event for event, _ in events]
