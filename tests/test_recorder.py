import json
import sqlite3

import pytest
from typer.testing import CliRunner

from architect.cli.main import app
from architect.recorder.events import ArchitectEvent, EVENT_TYPES
from architect.recorder.recorder import FlightRecorder
from architect.storage.db import create_run, get_run, log_event


@pytest.fixture
def recording(tmp_path):
    database = tmp_path / '.architect' / 'architect.db'
    run_id = create_run('codex', 'NATIVE', 'M1 test', status='PENDING', db_path=database)
    return database, run_id, FlightRecorder(database)


@pytest.mark.parametrize('event_type', sorted(EVENT_TYPES))
def test_contract(event_type):
    event = ArchitectEvent('run', event_type, event_id='event',
                           timestamp='2026-01-01T03:00:00+03:00',
                           metadata={'z': [1, True, None], 'a': {'b': 'ü'}})
    assert event.timestamp == '2026-01-01T00:00:00.000000+00:00'
    assert event.tool is None
    assert event.to_json() == ArchitectEvent(**json.loads(event.to_json())).to_json()
    other = ArchitectEvent('run', event_type, event_id='event', timestamp=event.timestamp,
                           metadata={'a': {'b': 'ü'}, 'z': [1, True, None]})
    assert event.to_json() == other.to_json()


@pytest.mark.parametrize('kwargs', [
    {'event_type': 'native_tool'}, {'status': 'unknown'}, {'fidelity': 'invented'},
    {'duration_ms': -1}, {'duration_ms': float('nan')}, {'duration_ms': True},
    {'metadata': {1: 'bad'}}, {'metadata': {'a': float('inf')}},
    {'timestamp': '2026-01-01'}, {'run_id': ''},
])
def test_invalid_contract(kwargs):
    data = {'run_id': 'run', 'event_type': 'error'} | kwargs
    with pytest.raises(ValueError):
        ArchitectEvent(**data)


def test_persistence_order_and_legacy(recording):
    database, run, recorder = recording
    legacy = log_event(run, 'TOOL_CALL', payload='old text', db_path=database)
    later = ArchitectEvent(run, 'file_read', timestamp='2026-02-02T00:00:00Z')
    first = ArchitectEvent(run, 'error', timestamp='2026-01-01T00:00:00Z')
    second = ArchitectEvent(run, 'test_execution', timestamp=first.timestamp)
    for event in (later, first, second):
        assert recorder.record(event) == event.event_id
    assert recorder.timeline(run) == [first, second, later]
    assert recorder.timeline('other') == []
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT payload FROM events WHERE id=?', (legacy,)).fetchone()[0] == 'old text'


def test_invalid_run_duplicate_and_mutated_metadata(recording):
    _, run, recorder = recording
    with pytest.raises(ValueError, match='Unknown run'):
        recorder.record(ArchitectEvent('absent', 'error'))
    event = ArchitectEvent(run, 'error')
    recorder.record(event)
    with pytest.raises(ValueError, match='Duplicate'):
        recorder.record(event)
    event.metadata['bad'] = object()
    with pytest.raises(ValueError):
        recorder.record(event)
    assert len(recorder.timeline(run)) == 1


@pytest.mark.parametrize('outcome', ['SUCCESS', 'FAILED', 'CANCELLED'])
def test_lifecycle(recording, outcome):
    database, run, recorder = recording
    assert get_run(run, db_path=database)['status'] == 'PENDING'
    recorder.start_run(run)
    assert get_run(run, db_path=database)['status'] == 'RUNNING'
    with pytest.raises(ValueError, match='already recorded'):
        recorder.start_run(run)
    recorder.finish_run(run, outcome)
    stored = get_run(run, db_path=database)
    assert stored['status'] == outcome
    assert stored['ended_at'] == recorder.timeline(run)[-1].timestamp
    with pytest.raises(ValueError, match='terminal'):
        recorder.start_run(run)
    with pytest.raises(ValueError, match='terminal'):
        recorder.finish_run(run)
    assert len(recorder.timeline(run)) == 2


def test_failed_finish_does_not_change_state(recording):
    database, run, recorder = recording
    with pytest.raises(ValueError, match='consistent'):
        recorder.record(ArchitectEvent(run, 'run_finished', status='success',
                                       metadata={'run_status': 'FAILED'}))
    assert get_run(run, db_path=database)['status'] == 'PENDING'
    assert recorder.timeline(run) == []


def test_transaction_rollback(recording):
    database, run, recorder = recording
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TRIGGER reject_event BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT, 'test'); END")
    with pytest.raises(sqlite3.IntegrityError):
        recorder.finish_run(run)
    assert get_run(run, db_path=database)['status'] == 'PENDING'
    assert get_run(run, db_path=database)['ended_at'] is None


def test_inspect(recording, monkeypatch, tmp_path):
    _, run, recorder = recording
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    empty = runner.invoke(app, ['inspect', run])
    assert empty.exit_code == 0
    assert 'No normalized events' in empty.stdout
    recorder.start_run(run)
    recorder.record(ArchitectEvent(run, 'file_read', target='README.md'))
    recorder.finish_run(run)
    result = runner.invoke(app, ['inspect', run])
    assert result.exit_code == 0
    assert 'SUCCESS' in result.stdout
    assert 'README.md' in result.stdout
    assert result.stdout.index('RUN_STARTED') < result.stdout.index('FILE_READ') < result.stdout.index('RUN_FINISHED')
    unknown = runner.invoke(app, ['inspect', 'absent'])
    assert unknown.exit_code == 1
    assert 'Unknown run' in unknown.stdout


@pytest.mark.parametrize('status', ['SUCCESS', 'FAILED', 'CANCELLED'])
def test_legacy_terminal_creation_timestamp(tmp_path, status):
    database = tmp_path / 'db.sqlite'
    run = create_run('codex', 'NATIVE', 'legacy', status=status, db_path=database)
    assert get_run(run, db_path=database)['ended_at'] is not None
