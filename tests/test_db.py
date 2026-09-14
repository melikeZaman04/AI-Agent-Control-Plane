import json
import sqlite3

import pytest

from architect.storage.db import (
    count_runs_by_status,
    create_run,
    ensure_project,
    initialize_database,
    list_recent_runs,
    log_event,
)


def test_schema_initialization_is_idempotent(tmp_path):
    database = tmp_path / "state" / "architect.db"

    assert initialize_database(database) == database.resolve()
    initialize_database(database)

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"projects", "runs", "events"} <= tables


def test_project_registration_does_not_duplicate_root(tmp_path):
    database = tmp_path / "architect.db"

    first_id = ensure_project(tmp_path, db_path=database)
    second_id = ensure_project(tmp_path, name="renamed", db_path=database)

    assert first_id == second_id
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
        name, root = connection.execute(
            "SELECT name, root_path FROM projects"
        ).fetchone()
    assert name == tmp_path.name
    assert root == str(tmp_path.resolve())


def test_runs_events_listing_counts_and_deterministic_json(tmp_path):
    database = tmp_path / "architect.db"
    first = create_run(
        "codex", "native", "first", run_id="run-1", db_path=database
    )
    create_run(
        "claude", "session_log", "second", run_id="run-2",
        status="success", db_path=database,
    )
    event_id = log_event(
        first, "tool_call", payload={"z": 1, "a": "value"}, db_path=database
    )

    assert event_id > 0
    assert count_runs_by_status(db_path=database) == {"RUNNING": 1, "SUCCESS": 1}
    assert [run["run_id"] for run in list_recent_runs(limit=2, db_path=database)] == [
        "run-2",
        "run-1",
    ]

    with sqlite3.connect(database) as connection:
        payload = connection.execute(
            "SELECT payload FROM events WHERE id = ?", (event_id,)
        ).fetchone()[0]
    assert payload == '{"a":"value","z":1}'
    assert json.loads(payload) == {"a": "value", "z": 1}


def test_foreign_keys_are_enforced(tmp_path):
    database = initialize_database(tmp_path / "architect.db")
    with pytest.raises(sqlite3.IntegrityError):
        log_event("missing", "error", db_path=database)


def test_storage_validation(tmp_path):
    database = tmp_path / "architect.db"
    with pytest.raises(ValueError, match="fidelity_level"):
        create_run("codex", "unknown", "task", db_path=database)
    with pytest.raises(ValueError, match="greater than zero"):
        list_recent_runs(limit=0, db_path=database)
