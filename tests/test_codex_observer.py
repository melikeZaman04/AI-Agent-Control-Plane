from copy import deepcopy

import pytest
from typer.testing import CliRunner

from architect.cli.main import app
from architect.ingest import ingest
from architect.observers.base import Observer
from architect.observers.codex import CodexObserver, codex_session_id
from architect.recorder.recorder import FlightRecorder
from architect.storage.db import create_run
from architect.storage.sessions import bind_session


@pytest.fixture
def tool_record():
    return {
        "event_name": "codex.tool_result",
        "timestamp": "2026-09-15T10:00:00Z",
        "attributes": {
            "conversation.id": "codex-thread-123",
            "tool_name": "exec_command",
            "success": True,
            "duration_ms": 12.5,
            "command": "git status --short",
            "call_id": "call-1",
            "model": "documented-fixture-model",
            "output_snippet": "must not be retained",
            "prompt": "must not be retained",
        },
    }


def test_tool_result_success_and_metadata(tool_record):
    original = deepcopy(tool_record)
    observer: Observer = CodexObserver()

    event, = observer.normalize(tool_record, run_id="architect-run")

    assert tool_record == original
    assert event.run_id == "architect-run"
    assert event.event_type == "tool_execution"
    assert event.status == "success"
    assert event.provider == "codex"
    assert event.fidelity == "NATIVE"
    assert event.tool == "exec_command"
    assert event.duration_ms == 12.5
    assert event.metadata["native_event_name"] == "codex.tool_result"
    assert event.metadata["provider_session_id"] == "codex-thread-123"
    assert event.metadata["telemetry_source"] == "opentelemetry_log"
    assert event.metadata["otel_attributes"]["call_id"] == "call-1"
    assert "output_snippet" not in event.metadata["otel_attributes"]
    assert event.metadata["sensitive_attributes_omitted"] == ["output_snippet", "prompt"]


def test_normalization_is_deterministic_except_generated_event_id(tool_record):
    first, = CodexObserver().normalize(tool_record, run_id="run")
    second, = CodexObserver().normalize(deepcopy(tool_record), run_id="run")
    first_values = vars(first) | {"event_id": "generated"}
    second_values = vars(second) | {"event_id": "generated"}
    assert first_values == second_values


def test_mcp_tool_stays_a_tool_execution(tool_record):
    tool_record["attributes"].update(
        tool_name="mcp_call",
        command=None,
        **{"mcp.server": "filesystem", "mcp.tool": "read_file"},
    )
    event, = CodexObserver().normalize(tool_record, run_id="run")
    assert event.event_type == "tool_execution"
    assert event.metadata["otel_attributes"]["mcp.server"] == "filesystem"


@pytest.mark.parametrize(
    ("command", "event_type"),
    [
        ("pytest -q", "test_execution"),
        ("python -m pytest tests/unit", "test_execution"),
        ("python3 -m pytest", "test_execution"),
        ("pytest -q && echo done", "tool_execution"),
        ("echo pytest", "tool_execution"),
    ],
)
def test_pytest_recognition(tool_record, command, event_type):
    tool_record["attributes"]["command"] = command
    event, = CodexObserver().normalize(tool_record, run_id="run")
    assert event.event_type == event_type
    assert event.metadata["command"] == command


def test_tool_failure(tool_record):
    tool_record["attributes"].update(success=False, error_type="sandbox_denied")
    event, = CodexObserver().normalize(tool_record, run_id="run")
    assert event.event_type == "tool_execution"
    assert event.status == "failed"
    assert event.metadata["otel_attributes"]["error_type"] == "sandbox_denied"


@pytest.mark.parametrize(
    ("decision", "status"),
    [
        ("approved", "success"),
        ("approved_with_amendment", "success"),
        ("approved_for_session", "success"),
        ("denied", "blocked"),
        ("abort", "blocked"),
    ],
)
def test_approval_decision(decision, status):
    record = {
        "event_name": "codex.tool_decision",
        "timestamp": "2026-09-15T10:00:00+00:00",
        "attributes": {
            "conversation.id": "thread",
            "tool_name": "exec_command",
            "decision": decision,
            "decision_source": "user",
        },
    }
    event, = CodexObserver().normalize(record, run_id="run")
    assert event.event_type == "approval_requested"
    assert event.status == status
    assert event.metadata["approval_decision"] == decision
    assert event.metadata["otel_attributes"]["decision_source"] == "user"


@pytest.mark.parametrize(
    "record",
    [
        {},
        {"event_name": "codex.tool_result"},
        {"event_name": "codex.tool_result", "timestamp": "2026-01-01T00:00:00Z", "attributes": {}},
        {
            "event_name": "codex.tool_result",
            "timestamp": "2026-01-01T00:00:00Z",
            "attributes": {"conversation.id": "thread", "tool_name": "tool", "success": "yes"},
        },
    ],
)
def test_malformed_supported_records(record):
    with pytest.raises(ValueError):
        CodexObserver().normalize(record, run_id="run")


@pytest.mark.parametrize(
    "event_name",
    ["codex.user_prompt", "codex.conversation_starts", "codex.api_request", "codex.sse_event", "future.event"],
)
def test_unmapped_and_prompt_events_are_ignored(event_name):
    record = {"event_name": event_name, "prompt": "sensitive value"}
    assert CodexObserver().normalize(record, run_id="run") == []


def test_session_identifier_is_provider_owned(tool_record):
    assert codex_session_id(tool_record) == "codex-thread-123"
    with pytest.raises(ValueError):
        codex_session_id({"attributes": {}})


def test_synthetic_pipeline_and_inspect(tool_record, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    database = tmp_path / ".architect" / "architect.db"
    run_id = create_run("codex", "NATIVE", "M2.3a pipeline", db_path=database)
    bind_session("codex", "codex-thread-123", run_id, db_path=database)

    event_ids = ingest("codex", tool_record, db_path=database)
    timeline = FlightRecorder(database).timeline(run_id)

    assert [event.event_id for event in timeline] == event_ids
    assert timeline[0].provider == "codex"
    result = CliRunner().invoke(app, ["inspect", run_id[:8]])
    assert result.exit_code == 0
    assert "TOOL_EXECUTION" in result.stdout
    assert "exec_command" in result.stdout


def test_ingest_unknown_is_noop_without_session(tmp_path):
    database = tmp_path / "architect.db"
    assert ingest("codex", {"event_name": "codex.user_prompt", "prompt": "private"}, db_path=database) == []
    assert ingest("codex", {"event_name": "unknown"}, db_path=database) == []


def test_ingest_requires_bound_session(tool_record, tmp_path):
    database = tmp_path / "architect.db"
    with pytest.raises(ValueError, match="Unknown provider session"):
        ingest("codex", tool_record, db_path=database)


def test_live_transport_is_explicitly_unavailable(tool_record, tmp_path):
    with pytest.raises(ValueError, match="Live Codex transport is not implemented"):
        ingest("codex", tool_record, db_path=tmp_path / "architect.db", live=True)
