"""Deterministic run episodes derived from project-local SQLite evidence."""

from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from architect.recorder.recorder import normalized_timeline
from architect.recorder.events import ArchitectEvent


def _project(connection, project_id):
    projects = connection.execute("SELECT id, root_path FROM projects ORDER BY id").fetchall()
    if len(projects) != 1:
        raise ValueError("Chronicle requires exactly one registered project per database")
    if projects[0]["id"] != project_id:
        raise ValueError("Unknown project in this database")
    return projects[0]


def _events(connection, run_id):
    rows = connection.execute(
        "SELECT id, payload FROM events WHERE run_id = ? ORDER BY id", (run_id,),
    ).fetchall()
    events = normalized_timeline(rows)
    seen = set()
    for event in events:
        if event.run_id != run_id or event.event_id in seen:
            raise ValueError("Inconsistent normalized evidence identity")
        seen.add(event.event_id)
    return events


@dataclass(frozen=True)
class ObservationFact:
    """Count of observations sharing normalized type, status and provenance.

    A successful tool observation does not imply a successful test or run.
    Missing provider/fidelity/status stays unknown, never inherited from a run.
    """

    event_type: str
    status: str | None
    provider: str | None
    fidelity: str | None
    evidence_event_ids: tuple[str, ...]

    @property
    def count(self) -> int:
        return len(self.evidence_event_ids)


@dataclass(frozen=True)
class ChronicleEpisode:
    """One run's structured history; run fields are sourced from runs[run_id]."""

    episode_id: str
    project_id: int
    project_root: str
    run_id: str
    began_at: str | None
    ended_at: str | None
    run_status: str
    evidence_event_ids: tuple[str, ...]
    facts: tuple[ObservationFact, ...]
    kind: str = "run"

    def to_json(self) -> str:
        data = asdict(self)
        data["facts"] = [asdict(fact) | {"count": fact.count} for fact in self.facts]
        return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _run_timestamp(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    # M0 uses SQLite CURRENT_TIMESTAMP, whose naive timestamps are UTC.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")


class ProjectChronicle:
    """Read-only, on-demand projection; no derived tables or rebuild cache.

    The current project-local schema has no run → project foreign key. Require
    exactly one registered project; never guess ownership in a shared database.
    Episode identity is (database, project_id, kind, full run_id).
    """

    def __init__(self, db_path: str | Path):
        self.database = Path(db_path).expanduser().resolve()

    def query(self, project_id: int, *, run_id: str | None = None) -> list[ChronicleEpisode]:
        """Read one consistent snapshot; run_id is exact, not a prefix.

        Order episodes by began_at ascending (unknown last), then full run_id.
        Evidence follows FlightRecorder order: UTC timestamp, insertion ID.
        Facts follow first supporting observation order. Repeating this query is
        the rebuild operation; new evidence updates the same episode identity.
        """
        with closing(sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN")
            project = _project(connection, project_id)
            runs = connection.execute(
                "SELECT run_id, started_at, ended_at, status FROM runs"
                + (" WHERE run_id = ?" if run_id is not None else ""),
                (run_id,) if run_id is not None else (),
            ).fetchall()
            episodes = []
            for run in runs:
                events = _events(connection, run["run_id"])
                groups = {}
                for event in events:
                    key = (event.event_type, event.status, event.provider, event.fidelity)
                    groups.setdefault(key, []).append(event.event_id)
                episodes.append(ChronicleEpisode(
                    episode_id=f"run:{project_id}:{run['run_id']}",
                    project_id=project_id, project_root=project["root_path"],
                    run_id=run["run_id"], began_at=_run_timestamp(run["started_at"]),
                    ended_at=_run_timestamp(run["ended_at"]), run_status=run["status"],
                    evidence_event_ids=tuple(event.event_id for event in events),
                    facts=tuple(ObservationFact(*key, tuple(ids)) for key, ids in groups.items()),
                ))
        episodes.sort(key=lambda episode: (
            episode.began_at is None, episode.began_at or "", episode.run_id,
        ))
        return episodes

    def evidence(self, project_id: int, *, run_id: str, event_id: str) -> ArchitectEvent:
        """Resolve an episode's exact source event ID within its project/run.

        Uses the same normalized evidence validation as query, in a read-only
        snapshot. Legacy payloads cannot be retrieved as normalized evidence.
        """
        with closing(sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN")
            _project(connection, project_id)
            if connection.execute("SELECT 1 FROM runs WHERE run_id = ?", (run_id,)).fetchone() is None:
                raise ValueError(f"Unknown run: {run_id}")
            events = _events(connection, run_id)
            for event in events:
                if event.event_id == event_id:
                    return event
        raise ValueError(f"Unknown normalized event in run {run_id}: {event_id}")

    def receipts(self, project_id: int, *, run_id: str | None = None) -> list[dict]:
        """Structured terminal/observed work, without inferring success or automation.

        Explicit boolean metadata.automated on normalized run lifecycle events
        identifies whole-run automation. Conflicting declarations stay unknown.
        Existing observers do not currently emit this optional declaration.
        """
        with closing(sqlite3.connect(self.database.as_uri() + '?mode=ro', uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute('BEGIN')
            project = _project(connection, project_id)
            runs = connection.execute(
                'SELECT run_id, started_at, ended_at, status FROM runs'
                + (' WHERE run_id = ?' if run_id is not None else ''),
                (run_id,) if run_id is not None else (),
            ).fetchall()
            receipts = []
            for run in runs:
                events = _events(connection, run['run_id'])
                if not events and run['status'] not in ('SUCCESS', 'FAILED', 'CANCELLED'):
                    continue
                declarations = [event for event in events
                                if event.event_type in ('run_started', 'run_finished')
                                and type(event.metadata.get('automated')) is bool]
                origins = {event.metadata['automated'] for event in declarations}
                automated = next(iter(origins)) if len(origins) == 1 else None
                source = {'table': 'runs', 'run_id': run['run_id']}
                failures = []
                if run['status'] == 'FAILED':
                    failures.append({
                        'kind': 'run_failure', 'run_source': source,
                        'timestamp': _run_timestamp(run['ended_at']),
                        'evidence_event_ids': [event.event_id for event in events
                                               if event.event_type == 'run_finished'
                                               and event.status == 'failed'
                                               and event.metadata.get('run_status') == 'FAILED'],
                    })
                def observation(event):
                    return {name: getattr(event, name) for name in (
                        'event_id', 'timestamp', 'event_type', 'status', 'provider',
                        'fidelity', 'tool', 'target',
                    )}
                failures.extend({'kind': 'event_failure', **observation(event)} for event in events
                                if event.event_type == 'error' or (
                                    event.event_type in ('tool_execution', 'test_execution')
                                    and event.status == 'failed'))
                failures.sort(key=lambda failure: (
                    failure['timestamp'] is None, failure['timestamp'] or '',
                    failure['kind'], failure.get('event_id', ''),
                ))
                receipts.append({
                    'receipt_id': f"work:{project_id}:{run['run_id']}",
                    'kind': 'automation_receipt' if automated is True else 'work_receipt',
                    'project_id': project_id, 'project_root': project['root_path'],
                    'run_id': run['run_id'], 'run_source': source,
                    'began_at': _run_timestamp(run['started_at']),
                    'ended_at': _run_timestamp(run['ended_at']), 'status': run['status'],
                    'automated': automated,
                    'automation_evidence_event_ids': [event.event_id for event in declarations],
                    'evidence_event_ids': [event.event_id for event in events],
                    'observations': [observation(event) for event in events],
                    'file_changes': [observation(event) for event in events
                                     if event.event_type == 'file_changed' and event.target is not None
                                     and event.status in (None, 'success')],
                    'tests': [observation(event) for event in events if event.event_type == 'test_execution'],
                    'failures': failures,
                })
        receipts.sort(key=lambda receipt: (
            receipt['began_at'] is None, receipt['began_at'] or '', receipt['run_id'],
        ))
        return receipts

    def failures(self, project_id: int, *, run_id: str | None = None) -> list[dict]:
        """Explicit run and event failures, ordered by time, run and source ID."""
        failures = [dict(failure, project_id=receipt['project_id'],
                         project_root=receipt['project_root'], run_id=receipt['run_id'])
                    for receipt in self.receipts(project_id, run_id=run_id)
                    for failure in receipt['failures']]
        failures.sort(key=lambda failure: (
            failure['timestamp'] is None, failure['timestamp'] or '', failure['run_id'],
            failure['kind'], failure.get('event_id', ''),
        ))
        return failures
