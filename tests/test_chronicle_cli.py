import json
import sqlite3
import subprocess
import sys

import pytest
from typer.testing import CliRunner

from architect.cli.main import app
from architect.chronicle import ProjectChronicle
from architect.observers.claude import ClaudeObserver
from architect.observers.codex import CodexObserver
from architect.recorder.events import ArchitectEvent
from architect.recorder.recorder import FlightRecorder
from architect.storage.db import create_run, ensure_project, log_event

runner = CliRunner()


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = tmp_path / '.architect/architect.db'
    pid = ensure_project(tmp_path, db_path=db)
    run = create_run('agent', 'NATIVE', 'CLI fixture', run_id='run-one', status='PENDING', db_path=db)
    return db, pid, run, FlightRecorder(db)


def invoke(*args):
    return runner.invoke(app, ['chronicle', *args])


def dump(db):
    with sqlite3.connect(db) as connection:
        return list(connection.iterdump())


def test_listing_order_json_text_and_read_only(project):
    db, pid, run, recorder = project
    other = create_run('other', 'PASSIVE', 'second', run_id='a-first', status='PENDING', db_path=db)
    for name in (run, other):
        recorder.record(ArchitectEvent(name, 'run_started', event_id=name + '-start', timestamp='2026-09-15T01:00:00Z'))
    event = ArchitectEvent(run, 'test_execution', event_id='test-id', timestamp='2026-09-15T02:00:00Z',
                           provider='[bold]literal[/bold]', fidelity='NATIVE')
    recorder.record(event)
    before = dump(db)
    result = invoke('--json')
    assert result.exit_code == 0 and result.stderr == ''
    entries = json.loads(result.stdout)
    assert [entry['run_id'] for entry in entries] == [other, run]
    assert entries == [json.loads(e.to_json()) for e in ProjectChronicle(db).query(pid)]
    assert invoke('--json').stdout == result.stdout
    text = invoke()
    assert text.exit_code == 0 and 'status=unknown' in text.stdout
    assert '[bold]literal[/bold]' in text.stdout and 'test-id' in text.stdout
    assert text.stdout.index('Run: a-first') < text.stdout.index('Run: run-one')
    assert invoke().stdout == text.stdout
    selected = json.loads(invoke('--run', run, '--json').stdout)
    assert len(selected) == 1 and selected[0]['run_id'] == run
    assert dump(db) == before


@pytest.mark.parametrize('provider', ['claude', 'codex'])
def test_provider_evidence_cli_roundtrip(project, provider):
    db, pid, run, recorder = project
    if provider == 'claude':
        events = ClaudeObserver(live=True).normalize({
            'hook_event_name': 'PostToolUse', 'session_id': 'thread', 'tool_name': 'Read',
            'tool_input': {'file_path': 'README.md'}, 'tool_response': {'content': 'fixture'},
        }, run_id=run)
    else:
        events = CodexObserver(live=True).normalize({
            'event_name': 'codex.tool_result', 'timestamp': '2026-09-15T01:00:00Z',
            'attributes': {'tool_name': 'exec_command', 'success': 'true', 'conversation.id': 'thread'},
        }, run_id=run)
    event, = events
    recorder.record(event)
    before = dump(db)
    listing = json.loads(invoke('--run', run, '--json').stdout)
    eid, = listing[0]['evidence_event_ids']
    result = invoke('--run', run, '--event', eid, '--json')
    assert result.exit_code == 0 and result.stderr == ''
    assert json.loads(result.stdout) == json.loads(event.to_json())
    assert result.stdout == invoke('--run', run, '--event', eid, '--json').stdout
    assert ProjectChronicle(db).evidence(pid, run_id=run, event_id=eid) == event
    text = invoke('--run', run, '--event', eid)
    assert text.exit_code == 0 and text.stdout.startswith('Evidence\n')
    assert json.loads(text.stdout.split('\n', 1)[1]) == json.loads(event.to_json())
    assert dump(db) == before


def test_empty_project_and_empty_run(project, tmp_path, monkeypatch):
    db, pid, run, recorder = project
    entry, = json.loads(invoke('--json').stdout)
    assert entry['facts'] == [] and entry['began_at'] is None
    assert 'No normalized evidence.' in invoke().stdout
    # Separate initialized project with no runs, via the real CLI.
    empty = tmp_path / 'empty'
    empty.mkdir()
    monkeypatch.chdir(empty)
    assert runner.invoke(app, ['init']).exit_code == 0
    assert invoke('--json').stdout == '[]\n'
    assert invoke().stdout == 'No Chronicle episodes.\n'


@pytest.mark.parametrize('args,code,message', [
    (['--event', 'event'], 2, '--event requires --run'),
    (['--run', 'run'], 1, 'Unknown run'),
    (['--run', 'absent'], 1, 'Unknown run'),
    (['--run', 'absent', '--event', 'absent'], 1, 'Unknown run'),
    (['--run', 'run-one', '--event', 'absent'], 1, 'Unknown normalized event'),
])
def test_explicit_errors_and_no_partial_json(project, args, code, message):
    before = dump(project[0])
    result = invoke(*args, '--json')
    assert result.exit_code == code and result.stdout == '' and message in result.stderr
    assert dump(project[0]) == before


def test_legacy_and_cross_run_evidence_cannot_resolve(project):
    db, pid, run, recorder = project
    row = log_event(run, 'TEST_EXECUTION', payload={'status': 'success'}, db_path=db)
    other = create_run('agent', 'NATIVE', 'other', db_path=db)
    event = ArchitectEvent(other, 'error')
    recorder.record(event)
    for eid in (str(row), event.event_id):
        result = invoke('--run', run, '--event', eid, '--json')
        assert result.exit_code == 1 and result.stdout == ''
    assert json.loads(invoke('--run', run, '--json').stdout)[0]['facts'] == []


@pytest.mark.parametrize('mode', ['multiple', 'wrong-root', 'unregistered'])
def test_project_ownership_errors(project, tmp_path, mode):
    db, pid, run, recorder = project
    if mode == 'multiple':
        ensure_project(tmp_path / 'other', db_path=db)
    else:
        with sqlite3.connect(db) as connection:
            if mode == 'wrong-root':
                connection.execute("UPDATE projects SET root_path = '/wrong'")
            else:
                connection.execute('DELETE FROM projects')
    before = dump(db)
    result = invoke('--json')
    assert result.exit_code == 1 and result.stdout == '' and 'Chronicle failed' in result.stderr
    assert dump(db) == before


def test_missing_database_does_not_initialize(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = invoke('--json')
    assert result.exit_code == 1 and 'Project database missing' in result.stderr
    assert not (tmp_path / '.architect').exists()


@pytest.mark.parametrize('mode', ['invalid-type', 'duplicate', 'wrong-run'])
def test_corrupt_evidence_fails_listing_and_resolution(project, mode):
    db, pid, run, recorder = project
    event = ArchitectEvent(run, 'error', event_id='evidence')
    recorder.record(event)
    data = json.loads(event.to_json())
    with sqlite3.connect(db) as connection:
        if mode == 'duplicate':
            connection.execute('INSERT INTO events(run_id,event_type,payload) VALUES (?,?,?)',
                               (run, 'error', event.to_json()))
        else:
            data['event_type' if mode == 'invalid-type' else 'run_id'] = 'bad'
            connection.execute('UPDATE events SET payload = ?', (json.dumps(data),))
    for args in ([], ['--run', run, '--event', event.event_id]):
        result = invoke(*args, '--json')
        assert result.exit_code == 1 and result.stdout == '' and 'Chronicle failed' in result.stderr


def test_real_process_json(project):
    result = subprocess.run([sys.executable, '-m', 'architect.cli.main', 'chronicle', '--json'],
                            capture_output=True, text=True, check=True)
    assert result.stderr == ''
    assert json.loads(result.stdout)[0]['run_id'] == project[2]
