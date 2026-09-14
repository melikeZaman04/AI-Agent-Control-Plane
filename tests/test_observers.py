from copy import deepcopy
import sqlite3

import pytest
from typer.testing import CliRunner
from architect.cli.main import app
from architect.ingest import ingest
from architect.observers.base import Observer
from architect.observers.claude import ClaudeObserver
from architect.recorder.recorder import FlightRecorder
from architect.storage.db import create_run, get_run, initialize_database, log_event
from architect.storage.sessions import bind_session, resolve_session


@pytest.fixture
def payload():
    return dict(hook_event_name='PostToolUse', session_id='synthetic-session',
                timestamp='2026-01-01T00:00:00Z', tool_name='Read',
                tool_input={'file_path': 'example.py'}, hook_source='synthetic fixture')


@pytest.fixture
def database(tmp_path):
    path = tmp_path / '.architect/architect.db'
    create_run('claude', 'NATIVE', 'synthetic task', run_id='abcdef00-full', db_path=path)
    bind_session('claude', 'synthetic-session', 'abcdef00-full', db_path=path)
    return path


@pytest.mark.parametrize('tool,inputs,expected', [
    ('Read', {'file_path': 'example.py'}, 'file_read'),
    ('Bash', {'command': 'git status'}, 'tool_execution'),
    ('Bash', {'command': 'pytest -q'}, 'test_execution'),
    ('Bash', {'command': 'python -m pytest tests/'}, 'test_execution'),
    ('Bash', {'command': 'python3 -m pytest'}, 'test_execution'),
    ('Bash', {'command': 'echo pytest'}, 'tool_execution'),
    ('Bash', {'command': 'pytest && echo ok'}, 'tool_execution'),
    ('Bash', {'command': 'pytest; false'}, 'tool_execution'),
    ('Bash', {'command': 'pytest $(echo x)'}, 'tool_execution'),
])
def test_normalize(payload, tool, inputs, expected):
    payload.update(tool_name=tool, tool_input=inputs)
    original = deepcopy(payload)
    observer: Observer = ClaudeObserver()
    event, = observer.normalize(payload, run_id='run')
    assert event.event_type == expected
    assert event.provider == 'claude' and event.fidelity == 'NATIVE'
    assert event.run_id == 'run' and event.status is None
    assert event.metadata['native_tool_name'] == tool
    assert event.metadata['provider_session_id'] == 'synthetic-session'
    assert event.metadata['hook_source'] == 'synthetic fixture'
    assert payload == original
    payload['tool_input']['extra'] = True
    assert 'extra' not in event.metadata['tool_input']


def test_failure(payload):
    payload.update(hook_event_name='PostToolUseFailure', error='permission denied')
    event, = ClaudeObserver().normalize(payload, run_id='run')
    assert (event.event_type, event.status) == ('tool_execution', 'failed')
    assert event.metadata['error'] == 'permission denied'


@pytest.mark.parametrize('name', ['UnknownHook', 'Stop', 'SessionEnd', 'SessionStart'])
def test_insufficient_evidence_ignored(payload, name):
    payload['hook_event_name'] = name
    assert ClaudeObserver().normalize(payload, run_id='run') == []


@pytest.mark.parametrize('field', ['session_id', 'timestamp', 'tool_input', 'tool_name'])
def test_missing_fields(payload, field):
    del payload[field]
    with pytest.raises(ValueError):
        ClaudeObserver().normalize(payload, run_id='run')


def test_binding(database):
    assert bind_session('claude', 'synthetic-session', 'abcdef00-full', db_path=database) == 'abcdef00-full'
    assert resolve_session('claude', 'synthetic-session', db_path=database) == 'abcdef00-full'
    create_run('claude', 'NATIVE', 'other', run_id='other', db_path=database)
    with pytest.raises(ValueError, match='Conflicting'):
        bind_session('claude', 'synthetic-session', 'other', db_path=database)
    with pytest.raises(ValueError, match='Unknown run'):
        bind_session('claude', 'new', 'abcdef00', db_path=database)
    with pytest.raises(ValueError, match='Unknown provider session'):
        resolve_session('other', 'synthetic-session', db_path=database)
    bind_session('other', 'synthetic-session', 'other', db_path=database)
    assert resolve_session('other', 'synthetic-session', db_path=database) == 'other'
    initialize_database(database)
    initialize_database(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT count(*) FROM provider_sessions').fetchone()[0] == 2


def test_pipeline(database, payload, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    legacy = log_event('abcdef00-full', 'TOOL_CALL', payload='legacy', db_path=database)
    ids = ingest('claude', payload, db_path=database)
    events = FlightRecorder(database).timeline('abcdef00-full')
    assert [event.event_id for event in events] == ids
    assert events[0].target == 'example.py'
    result = CliRunner().invoke(app, ['inspect', 'abcdef00'])
    assert result.exit_code == 0
    assert 'FILE_READ' in result.stdout and 'example.py' in result.stdout
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT payload FROM events WHERE id=?', (legacy,)).fetchone()[0] == 'legacy'
    payload['session_id'] = 'missing'
    with pytest.raises(ValueError, match='Unknown provider session'):
        ingest('claude', payload, db_path=database)
    with pytest.raises(ValueError, match='Unsupported provider'):
        ingest('unknown', payload, db_path=database)
    assert len(FlightRecorder(database).timeline('abcdef00-full')) == 1


@pytest.mark.parametrize('outcome', ['SUCCESS', 'FAILED', 'CANCELLED'])
def test_explicit_synthetic_lifecycle(database, payload, outcome):
    payload.update(hook_event_name='SessionStart', run_scope='bound_run', run_started=True)
    ingest('claude', payload, db_path=database)
    payload.update(hook_event_name='SessionEnd', run_outcome=outcome)
    ingest('claude', payload, db_path=database)
    assert get_run('abcdef00-full', db_path=database)['status'] == outcome
    assert [e.event_type for e in FlightRecorder(database).timeline('abcdef00-full')] == ['run_started', 'run_finished']


def test_additive_schema_preserves_legacy(database):
    # Simulate the pre-M2 schema using an isolated database with real M1 data.
    log_event('abcdef00-full', 'ERROR', payload='old event', db_path=database)
    with sqlite3.connect(database) as connection:
        connection.execute('DROP TABLE provider_sessions')
    initialize_database(database)
    initialize_database(database)
    bind_session('claude', 'restored-session', 'abcdef00-full', db_path=database)
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT count(*) FROM runs').fetchone()[0] == 1
        assert connection.execute('SELECT payload FROM events').fetchone()[0] == 'old event'
        connection.execute('PRAGMA foreign_keys = ON')
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO provider_sessions VALUES ('claude', 'bad', 'missing')")


def test_unknown_ingest_is_noop(database, payload):
    payload['hook_event_name'] = 'UnknownHook'
    assert ingest('claude', payload, db_path=database) == []
    assert FlightRecorder(database).timeline('abcdef00-full') == []
