import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner
from architect.cli.main import app
from architect.recorder.recorder import FlightRecorder
from architect.storage.db import create_run, get_run
from architect.storage.sessions import resolve_session


@pytest.fixture
def live_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = tmp_path / '.architect/architect.db'
    run = create_run('claude', 'NATIVE', 'live-format fixture', db_path=db)
    monkeypatch.setenv('ARCHITECT_RUN_ID', run)
    return db, run


def invoke(payload):
    return CliRunner().invoke(app, ['ingest', 'claude'], input=json.dumps(payload))


def start():
    return invoke(dict(hook_event_name='SessionStart', session_id='claude-session', source='startup'))


def test_binding_repeat_and_environment_independence(live_project, monkeypatch):
    db, run = live_project
    for _ in range(2):
        result = start()
        assert result.exit_code == 0 and result.stdout == result.stderr == ''
    assert resolve_session('claude', 'claude-session', db_path=db) == run
    monkeypatch.delenv('ARCHITECT_RUN_ID')
    result = invoke(dict(hook_event_name='PostToolUse', session_id='claude-session',
                         tool_name='Read', tool_input={'file_path': '/tmp/README.md'},
                         tool_response={'file': {'content': 'fixture'}}, tool_use_id='toolu_fixture'))
    assert result.exit_code == 0 and result.stdout == result.stderr == ''
    event, = FlightRecorder(db).timeline(run)
    assert event.event_type == 'file_read' and event.status == 'success'
    assert event.fidelity == 'NATIVE' and event.metadata['synthetic'] is False
    assert event.metadata['timestamp_source'] == 'hook_received_at'
    assert event.metadata['tool_use_id'] == 'toolu_fixture'
    assert get_run(run, db_path=db)['status'] == 'RUNNING'
    inspected = CliRunner().invoke(app, ['inspect', run[:8]])
    assert inspected.exit_code == 0 and 'FILE_READ' in inspected.stdout


@pytest.mark.parametrize('value', [None, '', 'missing', 'prefix'])
def test_invalid_run_binding(live_project, monkeypatch, value):
    db, run = live_project
    if value is None:
        monkeypatch.delenv('ARCHITECT_RUN_ID')
    else:
        monkeypatch.setenv('ARCHITECT_RUN_ID', run[:8] if value == 'prefix' else value)
    result = start()
    assert result.exit_code == 1 and not result.stdout
    assert 'Architect ingest failed' in result.stderr
    with pytest.raises(ValueError, match='Unknown provider session'):
        resolve_session('claude', 'claude-session', db_path=db)


@pytest.mark.parametrize('name,tool,inputs,expected,status', [
    ('PostToolUse', 'Bash', {'command': 'git status'}, 'tool_execution', None),
    ('PostToolUse', 'Bash', {'command': 'pytest -q'}, 'test_execution', None),
    ('PostToolUseFailure', 'Bash', {'command': 'pytest -q'}, 'tool_execution', 'failed'),
])
def test_live_tools(live_project, name, tool, inputs, expected, status):
    db, run = live_project
    assert start().exit_code == 0
    payload = dict(hook_event_name=name, session_id='claude-session', tool_name=tool,
                   tool_input=inputs, cwd='/different/directory', tool_use_id='toolu_fixture')
    if name == 'PostToolUseFailure':
        payload.update(error='command failed', is_interrupt=False)
    else:
        payload['tool_response'] = {'stdout': 'fixture output', 'stderr': '', 'interrupted': False}
    result = invoke(payload)
    assert result.exit_code == 0 and result.stdout == result.stderr == ''
    event, = FlightRecorder(db).timeline(run)
    assert (event.event_type, event.status) == (expected, status)
    assert event.metadata['cwd'] == '/different/directory'


def test_lifecycle_and_unknown_ignored(live_project):
    db, run = live_project
    assert invoke({'hook_event_name': 'Unknown'}).exit_code == 0
    assert start().exit_code == 0
    for name in ('Stop', 'SessionEnd'):
        result = invoke(dict(hook_event_name=name, session_id='claude-session',
                             run_scope='bound_run', run_outcome='SUCCESS'))
        assert result.exit_code == 0 and not result.stdout
    assert get_run(run, db_path=db)['status'] == 'RUNNING'
    assert FlightRecorder(db).timeline(run) == []


@pytest.mark.parametrize('raw', ['bad json', '[]', '{}', '{} {}'])
def test_malformed_stdin(live_project, raw):
    result = CliRunner().invoke(app, ['ingest', 'claude'], input=raw)
    assert result.exit_code == 1 and not result.stdout
    assert 'Architect ingest failed' in result.stderr


def test_missing_session_and_conflict(live_project, monkeypatch):
    db, run = live_project
    result = invoke(dict(hook_event_name='PostToolUse', session_id='unknown'))
    assert result.exit_code == 1 and 'Unknown provider session' in result.stderr
    assert start().exit_code == 0
    other = create_run('claude', 'NATIVE', 'other', db_path=db)
    monkeypatch.setenv('ARCHITECT_RUN_ID', other)
    result = start()
    assert result.exit_code == 1 and 'Conflicting' in result.stderr
    assert resolve_session('claude', 'claude-session', db_path=db) == run


def test_checked_hook_command(live_project, monkeypatch, tmp_path):
    # Actual subprocess stdin + shell quoting + executable with spaces, no Claude account.
    repo = Path(__file__).resolve().parents[1]
    settings = json.loads((repo / 'docs/integrations/claude-settings.example.json').read_text())
    monkeypatch.setenv('CLAUDE_PROJECT_DIR', str(tmp_path))
    monkeypatch.setenv('ARCHITECT_EXECUTABLE', str(repo / '.venv/bin/architect'))
    command = settings['hooks']['SessionStart'][0]['hooks'][0]['command']
    result = subprocess.run(command, shell=True, cwd='/tmp', capture_output=True, text=True,
                            input=json.dumps(dict(hook_event_name='SessionStart', session_id='subprocess')))
    assert result.returncode == 0 and result.stdout == result.stderr == ''
    assert resolve_session('claude', 'subprocess', db_path=live_project[0]) == live_project[1]
