"""Exact provider-session bindings, separate from Architect run identity."""

from pathlib import Path
from architect.storage.db import _connect, initialize_database


def _validate(*values: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("Binding identifiers must be nonempty strings")


def bind_session(provider: str, session_id: str, run_id: str, *, db_path: str | Path) -> str:
    _validate(provider, session_id, run_id)
    database = initialize_database(db_path)
    with _connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT run_id FROM provider_sessions WHERE provider=? AND provider_session_id=?",
            (provider, session_id),
        ).fetchone()
        if existing:
            if existing[0] != run_id:
                raise ValueError("Conflicting provider-session binding")
            return run_id
        if not connection.execute("SELECT 1 FROM runs WHERE run_id=?", (run_id,)).fetchone():
            raise ValueError(f"Unknown run: {run_id}")
        connection.execute("INSERT INTO provider_sessions VALUES (?, ?, ?)",
                           (provider, session_id, run_id))
    return run_id


def resolve_session(provider: str, session_id: str, *, db_path: str | Path) -> str:
    _validate(provider, session_id)
    with _connect(initialize_database(db_path)) as connection:
        row = connection.execute(
            "SELECT run_id FROM provider_sessions WHERE provider=? AND provider_session_id=?",
            (provider, session_id),
        ).fetchone()
    if row is None:
        raise ValueError(f"Unknown provider session: {provider}/{session_id}")
    return row[0]
