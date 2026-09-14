import json
import sqlite3

import pytest

from architect.chronicle import ProjectChronicle
from architect.observers.claude import ClaudeObserver
from architect.observers.codex import CodexObserver
from architect.recorder.events import ArchitectEvent, EVENT_TYPES
from architect.recorder.recorder import FlightRecorder
from architect.storage.db import create_run, ensure_project, log_event


@pytest.fixture
def project(tmp_path):
    database = tmp_path / '.architect/architect.db'
    project_id = ensure_project(tmp_path, db_path=database)
    run = create_run('any-agent', 'NATIVE', 'Chronicle fixture', run_id='run-one',
                     status='PENDING', db_path=database)
    return database, project_id, run, FlightRecorder(database)


def record(recorder, run, event_type, timestamp='2026-09-15T10:00:00Z', **kwargs):
    event = ArchitectEvent(run, event_type, timestamp=timestamp, **kwargs)
    recorder.record(event)
    return event


def test_end_to_end_lifecycle_provenance_and_read_only(project):
    database, pid, run, recorder = project
    start = record(recorder, run, 'run_started')
    first = record(recorder, run, 'test_execution', status='success', provider='arbitrary',
                   fidelity='SESSION_LOG', tool='pytest', metadata={'stdout': 'PRIVATE'})
    second = record(recorder, run, 'test_execution', status='success', provider='arbitrary',
                    fidelity='SESSION_LOG', tool='pytest')
    end = record(recorder, run, 'run_finished', '2026-09-15T11:00:00Z',
                 status='success', metadata={'run_status': 'SUCCESS'})
    with sqlite3.connect(database) as connection:
        before = list(connection.iterdump())
    episode, = ProjectChronicle(database).query(pid, run_id=run)
    assert (episode.project_id, episode.project_root, episode.run_id, episode.kind) == (
        pid, str(database.parent.parent), run, 'run')
    assert (episode.began_at, episode.ended_at, episode.run_status) == (
        start.timestamp, end.timestamp, 'SUCCESS')
    assert episode.evidence_event_ids == (start.event_id, first.event_id, second.event_id, end.event_id)
    fact = episode.facts[1]
    assert (fact.event_type, fact.status, fact.provider, fact.fidelity, fact.count) == (
        'test_execution', 'success', 'arbitrary', 'SESSION_LOG', 2)
    source = {event.event_id: event for event in recorder.timeline(run)}
    assert all(source[eid].event_type == fact.event_type for eid in fact.evidence_event_ids)
    assert json.loads(episode.to_json())['facts'][1]['count'] == 2
    assert 'PRIVATE' not in episode.to_json()
    with sqlite3.connect(database) as connection:
        assert list(connection.iterdump()) == before
        for eid in episode.evidence_event_ids:
            payload, = connection.execute(
                "SELECT payload FROM events WHERE json_extract(payload, '$.event_id') = ?", (eid,),
            ).fetchone()
            assert json.loads(payload)['event_id'] == eid


def test_idempotent_rebuild_update_and_relocated_database(project, tmp_path):
    database, pid, run, recorder = project
    chronicle = ProjectChronicle(database)
    initial, = chronicle.query(pid)
    assert initial.began_at is initial.ended_at is None
    assert initial.facts == initial.evidence_event_ids == ()
    event = record(recorder, run, 'file_changed')
    updated, = chronicle.query(pid)
    assert updated.episode_id == initial.episode_id
    assert updated.evidence_event_ids == (event.event_id,)
    assert updated.ended_at is None  # Last observation does not prove completion.
    assert chronicle.query(pid) == [updated]
    assert chronicle.query(pid)[0].to_json() == updated.to_json()
    backup = tmp_path / 'copy.db'
    with sqlite3.connect(database) as source, sqlite3.connect(backup) as dest:
        source.backup(dest)
    assert ProjectChronicle(backup).query(pid)[0].to_json() == updated.to_json()


def test_chronological_order_ties_and_unknown_start(project):
    database, pid, run, recorder = project
    for name, timestamp in [('z', '2026-09-15T03:00:00+03:00'),
                            ('a', '2026-09-15T00:00:00Z'),
                            ('later', '2026-09-16T00:00:00Z')]:
        create_run('agent', 'NATIVE', 'order', run_id=name, status='PENDING', db_path=database)
        record(recorder, name, 'run_started', timestamp)
    chronicle = ProjectChronicle(database)
    assert [e.run_id for e in chronicle.query(pid)] == ['a', 'z', 'later', run]
    assert chronicle.query(pid, run_id='run') == []  # exact IDs only
    late = record(recorder, run, 'error', '2026-09-15T12:00:00Z', event_id='a')
    first = record(recorder, run, 'file_read', event_id='z')
    tie = record(recorder, run, 'file_read', event_id='b')
    episode, = chronicle.query(pid, run_id=run)
    assert episode.evidence_event_ids == (first.event_id, tie.event_id, late.event_id)
    assert episode.facts[0].evidence_event_ids == (first.event_id, tie.event_id)


def test_legacy_not_promoted_and_no_invented_success(project):
    database, pid, run, recorder = project
    for payload in ['pytest passed', {'status': 'success', 'event_type': 'test_execution'},
                    {'command': 'pytest -q', 'exit_code': 0}]:
        log_event(run, 'TEST_EXECUTION', payload=payload, db_path=database)
    unknown = record(recorder, run, 'test_execution', metadata={'exit_code': 0})
    tool = record(recorder, run, 'tool_execution', status='success',
                  metadata={'command': 'pytest -q', 'provider': 'codex'})
    episode, = ProjectChronicle(database).query(pid)
    assert episode.evidence_event_ids == (unknown.event_id, tool.event_id)
    assert [(f.event_type, f.status, f.provider, f.fidelity) for f in episode.facts] == [
        ('test_execution', None, None, None), ('tool_execution', 'success', None, None)]
    assert episode.run_status == 'PENDING'


@pytest.mark.parametrize('event_type', sorted(EVENT_TYPES))
def test_normalized_vocabulary_remains_provider_independent(project, event_type):
    database, pid, run, recorder = project
    kwargs = {'status': 'failed', 'metadata': {'run_status': 'FAILED'}} if event_type == 'run_finished' else {}
    event = record(recorder, run, event_type, provider='future-agent', fidelity='PASSIVE', **kwargs)
    episode, = ProjectChronicle(database).query(pid)
    fact, = episode.facts
    assert (fact.event_type, fact.provider, fact.fidelity, fact.evidence_event_ids) == (
        event_type, 'future-agent', 'PASSIVE', (event.event_id,))


@pytest.mark.parametrize('provider', ['claude', 'codex'])
def test_live_format_observers_through_real_recorder(project, provider):
    database, pid, run, recorder = project
    if provider == 'claude':
        events = ClaudeObserver(live=True).normalize({
            'hook_event_name': 'PostToolUse', 'session_id': 'claude-thread',
            'tool_name': 'Bash', 'tool_input': {'command': 'pytest -q'},
            'tool_response': {'stdout': 'fixture', 'stderr': '', 'interrupted': False},
        }, run_id=run)
        expected = ('test_execution', None)
    else:
        events = CodexObserver(live=True).normalize({
            'event_name': 'codex.tool_result', 'timestamp': '2026-09-15T10:00:00Z',
            'attributes': {'conversation.id': 'codex-thread', 'tool_name': 'exec_command',
                           'success': 'true', 'command': 'pytest -q'},
        }, run_id=run)
        expected = ('tool_execution', 'success')  # Live command capture is disabled.
    for event in events:
        recorder.record(event)
    episode, = ProjectChronicle(database).query(pid, run_id=run)
    fact, = episode.facts
    assert (fact.event_type, fact.status) == expected
    assert (fact.provider, fact.fidelity) == (provider, 'NATIVE')
    assert fact.evidence_event_ids == tuple(e.event_id for e in recorder.timeline(run))
    assert all(e.metadata['synthetic'] is False for e in recorder.timeline(run))


def test_distinct_provenance_groups(project):
    database, pid, run, recorder = project
    for provider, fidelity in [('claude', 'NATIVE'), ('codex', 'NATIVE'), (None, None)]:
        record(recorder, run, 'tool_execution', provider=provider, fidelity=fidelity)
    episode, = ProjectChronicle(database).query(pid)
    assert [(f.provider, f.fidelity, f.count) for f in episode.facts] == [
        ('claude', 'NATIVE', 1), ('codex', 'NATIVE', 1), (None, None, 1)]


def test_project_isolation_and_ambiguous_database(project, tmp_path):
    database, pid, run, recorder = project
    chronicle = ProjectChronicle(database)
    with pytest.raises(ValueError, match='Unknown project'):
        chronicle.query(pid + 1)
    other_db = tmp_path / 'other/architect.db'
    other_pid = ensure_project(tmp_path / 'other', db_path=other_db)
    assert ProjectChronicle(other_db).query(other_pid) == []
    ensure_project(tmp_path / 'shared-project', db_path=database)
    with pytest.raises(ValueError, match='exactly one'):
        chronicle.query(pid)


def test_missing_database_is_not_created(tmp_path):
    database = tmp_path / 'missing.db'
    with pytest.raises(sqlite3.OperationalError):
        ProjectChronicle(database).query(1)
    assert not database.exists()


def test_database_without_registered_project_is_rejected(tmp_path):
    database = tmp_path / 'unregistered.db'
    create_run('agent', 'NATIVE', 'no project', db_path=database)
    with pytest.raises(ValueError, match='exactly one'):
        ProjectChronicle(database).query(1)


@pytest.mark.parametrize('corruption', ['wrong-run', 'invalid-event', 'duplicate'])
def test_corrupt_normalized_evidence_is_not_silently_summarized(project, corruption):
    database, pid, run, recorder = project
    event = record(recorder, run, 'error')
    payload = json.loads(event.to_json())
    if corruption == 'wrong-run':
        payload['run_id'] = 'another-run'
    elif corruption == 'invalid-event':
        payload['event_type'] = 'invented'
    with sqlite3.connect(database) as connection:
        if corruption == 'duplicate':
            connection.execute('INSERT INTO events(run_id,event_type,payload) VALUES (?,?,?)',
                               (run, 'error', event.to_json()))
        else:
            connection.execute('UPDATE events SET payload = ?', (json.dumps(payload),))
    with pytest.raises(ValueError):
        ProjectChronicle(database).query(pid)


def test_m0_run_timestamps_are_explicitly_utc(project):
    database, pid, run, recorder = project
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE runs SET started_at='2026-09-15 10:00:00' WHERE run_id=?", (run,))
    episode, = ProjectChronicle(database).query(pid)
    assert episode.began_at == '2026-09-15T10:00:00.000000+00:00'
