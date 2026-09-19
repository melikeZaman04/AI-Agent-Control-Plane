"""Independent acceptance counterexamples over disposable Git/SQLite projects."""

from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
import sys

import pytest
from typer.testing import CliRunner

from architect.benchmark import run_suite
from architect.chronicle import ProjectChronicle
from architect.cli.main import app
from architect.git_history import GitHistory
from architect.labs import Labs
from architect.recorder.events import ArchitectEvent
from architect.recorder.recorder import FlightRecorder
from architect.session import SessionIntelligence
from architect.storage.db import create_run, ensure_project, log_event
from test_git_history import repo, git, commit
from test_labs import REPAIRS


@pytest.fixture
def recorded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    database = tmp_path / '.architect/architect.db'
    pid = ensure_project(tmp_path)
    run = create_run('independent-provider', 'PASSIVE', 'acceptance', db_path=database)
    recorder = FlightRecorder(database)
    event = ArchitectEvent(run, 'tool_execution', status='failed')
    recorder.record(event)
    return database, pid, run, recorder, event


@pytest.mark.parametrize('damage', [
    'event_id', 'run_id', 'event_type', 'timestamp', 'truncated', 'null',
    'foreign-run', 'duplicate', 'extra-field', 'invalid-type',
])
def test_damaged_evidence_fails_all_read_surfaces_without_writes(recorded, damage):
    database, pid, run, recorder, event = recorded
    payload = json.loads(event.to_json())
    if damage in ('event_id', 'run_id', 'event_type', 'timestamp'):
        del payload[damage]
    elif damage == 'foreign-run':
        payload['run_id'] = 'another-run'
    elif damage == 'extra-field':
        payload['unsupported'] = True
    elif damage == 'invalid-type':
        payload['event_type'] = []
    encoded = json.dumps(payload)
    if damage == 'truncated':
        encoded = encoded[:30]
    elif damage == 'null':
        encoded = 'null'
    with sqlite3.connect(database) as connection:
        if damage == 'duplicate':
            connection.execute('INSERT INTO events(run_id,event_type,payload) VALUES (?,?,?)',
                               (run, 'tool_execution', encoded))
        else:
            connection.execute('UPDATE events SET payload=?', (encoded,))
    with sqlite3.connect(database) as connection:
        before = list(connection.iterdump())
    chronicle = ProjectChronicle(database)
    for read in (lambda: recorder.timeline(run), lambda: chronicle.query(pid),
                 lambda: chronicle.receipts(pid),
                 lambda: chronicle.evidence(pid, run_id=run, event_id=event.event_id)):
        with pytest.raises(ValueError):
            read()
    for command in (['inspect', run], ['chronicle', '--json'],
                    ['chronicle', '--run', run, '--event', event.event_id, '--json']):
        result = CliRunner().invoke(app, command)
        assert result.exit_code == 1
        assert result.stdout == '' and result.stderr
    with sqlite3.connect(database) as connection:
        assert list(connection.iterdump()) == before


def test_legacy_payloads_and_imported_normalized_identity(recorded):
    database, pid, run, recorder, event = recorded
    for payload in ('old text', '{broken legacy json', {'event_id': 'external-id'},
                    {'event_type': 'error', 'run_id': run}, ['legacy'], None):
        log_event(run, 'TOOL_CALL', payload=payload if not isinstance(payload, list) else json.dumps(payload),
                  db_path=database)
    assert recorder.timeline(run) == [event]
    assert ProjectChronicle(database).query(pid)[0].evidence_event_ids == (event.event_id,)
    foreign = ArchitectEvent('foreign', 'error')
    log_event(run, 'ERROR', payload=json.loads(foreign.to_json()), db_path=database)
    with pytest.raises(ValueError):
        recorder.timeline(run)


def test_missing_field_in_legacy_imported_normalized_envelope(recorded):
    database, pid, run, recorder, event = recorded
    payload = json.loads(event.to_json())
    del payload['timestamp']
    log_event(run, 'TOOL_CALL', payload=payload, db_path=database)
    with pytest.raises(ValueError):
        recorder.timeline(run)


@pytest.mark.parametrize('zone,day,expected', [
    ('UTC', '2026-01-02', ['running', 'terminal']),
    ('America/New_York', '2026-01-01', ['running', 'terminal']),
    ('UTC', '2026-01-01', []),
])
def test_day_includes_eventless_boundaries_without_inventing_work(repo, zone, day, expected):
    db = repo / '.architect/architect.db'
    pid = ensure_project(repo)
    for run, status in [('running', 'RUNNING'), ('pending', 'PENDING'), ('terminal', 'FAILED')]:
        create_run('fixture', 'PASSIVE', run, run_id=run, status=status, db_path=db)
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE runs SET started_at='2026-01-02 00:30:00' WHERE status!='PENDING'")
        connection.execute("UPDATE runs SET ended_at='2026-01-02 01:00:00' WHERE status='FAILED'")
    service = SessionIntelligence(db, pid)
    report = service.day(repo, day, timezone=zone)
    assert [item['run_id'] for item in report['work']] == expected
    assert all(item['observations'] == [] for item in report['work'])
    assert all(item['boundaries_on_day'] for item in report['work'])
    # M3 receipts retain their stricter work qualification.
    assert [r['run_id'] for r in ProjectChronicle(db).receipts(pid)] == ['terminal']
    assert service.day(repo, day, timezone=zone) == report


def test_day_boundaries_and_events_share_a_snapshot(repo, monkeypatch):
    import architect.chronicle as module
    db = repo / '.architect/architect.db'
    pid = ensure_project(repo)
    run = create_run('fixture', 'PASSIVE', 'snapshot', db_path=db)
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE runs SET started_at='2026-01-02 00:30:00'")
    recorder = FlightRecorder(db)
    original = module._project
    writes = []

    def concurrent_finish(connection, project_id):
        project = original(connection, project_id)  # Establish the read snapshot.
        if not writes:
            writes.append(recorder.record(ArchitectEvent(
                run, 'run_finished', timestamp='2026-01-02T01:00:00Z',
                status='failed', metadata={'run_status': 'FAILED'})))
        return project

    monkeypatch.setattr(module, '_project', concurrent_finish)
    service = SessionIntelligence(db, pid)
    before = service.day(repo, '2026-01-02')['work'][0]
    assert before['observations'] == []
    assert set(before['boundaries_on_day']) == {'began_at'}
    after = service.day(repo, '2026-01-02')['work'][0]
    assert [item['event_id'] for item in after['observations']] == writes
    assert set(after['boundaries_on_day']) == {'began_at', 'ended_at'}
