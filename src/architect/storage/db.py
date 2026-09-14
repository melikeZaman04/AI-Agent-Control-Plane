"""SQLite persistence primitives for Architect OS's flight recorder."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = PROJECT_ROOT / ".architect" / "architect.db"
DEFAULT_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

FIDELITY_LEVELS = frozenset({"NATIVE", "SESSION_LOG", "PASSIVE"})
RUN_STATUSES = frozenset({"PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED"})


def project_database_path(project_root: str | Path) -> Path:
    """Return the conventional database path for a project root."""
    return Path(project_root).expanduser().resolve() / ".architect" / "architect.db"


def initialize_database(
    db_path: str | Path = DEFAULT_DB_PATH,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
) -> Path:
    """Create the database and apply the idempotent schema."""
    database = Path(db_path).expanduser().resolve()
    schema = Path(schema_path).expanduser().resolve()

    if not schema.is_file():
        raise FileNotFoundError(f"Database schema not found: {schema}")

    database.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = schema.read_text(encoding="utf-8")

    with _connect(database) as connection:
        connection.executescript(schema_sql)

    return database


def ensure_project(
    project_root: str | Path,
    *,
    name: str | None = None,
    db_path: str | Path | None = None,
) -> int:
    """Register a project once and return its stable database identifier."""
    root = Path(project_root).expanduser().resolve()
    database = initialize_database(db_path or project_database_path(root))

    with _connect(database) as connection:
        row = connection.execute(
            "SELECT id FROM projects WHERE root_path = ? ORDER BY id LIMIT 1",
            (str(root),),
        ).fetchone()
        if row is not None:
            return int(row[0])

        cursor = connection.execute(
            "INSERT INTO projects (name, root_path) VALUES (?, ?)",
            (name or root.name, str(root)),
        )
        project_id = cursor.lastrowid

    if project_id is None:
        raise RuntimeError("SQLite did not return a project id")
    return project_id


def create_run(
    agent_name: str,
    fidelity_level: str,
    task_description: str,
    *,
    run_id: str | None = None,
    status: str = "RUNNING",
    context_tokens: int = 0,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> str:
    """Create a run and return its caller-supplied or generated identifier."""
    fidelity_level = fidelity_level.upper()
    status = status.upper()
    _require_choice("fidelity_level", fidelity_level, FIDELITY_LEVELS)
    _require_choice("status", status, RUN_STATUSES)

    if context_tokens < 0:
        raise ValueError("context_tokens cannot be negative")

    resolved_run_id = run_id or str(uuid4())
    database = initialize_database(db_path)

    with _connect(database) as connection:
        connection.execute(
            """
            INSERT INTO runs (
                run_id, agent_name, fidelity_level, task_description,
                status, context_tokens
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                resolved_run_id,
                agent_name,
                fidelity_level,
                task_description,
                status,
                context_tokens,
            ),
        )
        if status in {"SUCCESS", "FAILED", "CANCELLED"}:
            connection.execute(
                "UPDATE runs SET ended_at = started_at WHERE run_id = ?", (resolved_run_id,)
            )
        elif status == "PENDING":
            connection.execute(
                "UPDATE runs SET started_at = NULL WHERE run_id = ?", (resolved_run_id,)
            )

    return resolved_run_id


def get_run(run_id: str, *, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    """Resolve an exact ID first, otherwise a unique literal, case-sensitive prefix."""
    database = initialize_database(db_path)
    with _connect(database) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None and run_id:
            rows = connection.execute(
                "SELECT * FROM runs WHERE substr(run_id, 1, length(?)) = ? "
                "ORDER BY run_id LIMIT 2", (run_id, run_id),
            ).fetchall()
            if len(rows) > 1:
                raise ValueError("Ambiguous run ID prefix. Use more characters.")
            row = rows[0] if rows else None
    return dict(row) if row else None


def log_event(
    run_id: str | None,
    event_type: str,
    *,
    target: str | None = None,
    payload: str | Mapping[str, Any] | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """Append an event to the flight recorder and return its row id."""
    database = initialize_database(db_path)
    serialized_payload = _serialize_payload(payload)

    with _connect(database) as connection:
        cursor = connection.execute(
            """
            INSERT INTO events (run_id, event_type, target, payload)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, event_type.upper(), target, serialized_payload),
        )
        event_id = cursor.lastrowid

    if event_id is None:  # Defensive: SQLite supplies this for INTEGER PRIMARY KEY.
        raise RuntimeError("SQLite did not return an event id")
    return event_id


def list_recent_runs(
    *,
    limit: int = 10,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """Return the most recent runs as plain dictionaries."""
    if limit <= 0:
        raise ValueError("limit must be greater than zero")

    database = initialize_database(db_path)
    with _connect(database) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                run_id, agent_name, fidelity_level, task_description,
                status, started_at, ended_at, context_tokens
            FROM runs
            ORDER BY started_at DESC, rowid DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def count_runs_by_status(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, int]:
    """Return run counts grouped by status for the status overview."""
    database = initialize_database(db_path)
    with _connect(database) as connection:
        rows = connection.execute(
            "SELECT status, COUNT(*) FROM runs GROUP BY status ORDER BY status"
        ).fetchall()

    return {status: count for status, count in rows}


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=30.0)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def _serialize_payload(payload: str | Mapping[str, Any] | None) -> str | None:
    if payload is None or isinstance(payload, str):
        return payload
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _require_choice(name: str, value: str, choices: frozenset[str]) -> None:
    if value not in choices:
        expected = ", ".join(sorted(choices))
        raise ValueError(f"{name} must be one of: {expected}")
