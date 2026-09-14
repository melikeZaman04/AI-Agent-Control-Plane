import json
import sqlite3

import pytest
from typer.testing import CliRunner

from architect.chronicle import ProjectChronicle
from architect.cli.main import app
from architect.recorder.events import ArchitectEvent
from architect.recorder.recorder import FlightRecorder
from architect.storage.db import ensure_project, create_run, log_event


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = tmp_path / '.architect/architect.db'
    pid = ensure_project(tmp_path, db_path=db)
    run = create_run('agent', 'NATIVE', 'work', run_id='work', status='PENDING', db_path=db)
    return db, pid, run, FlightRecorder(db), ProjectChronicle(db)


def event(recorder, run, kind, **kwargs):
    obj = ArchitectEvent(run, kind, timestamp='2026-01-01T00:00:00Z', **kwargs)
    recorder.record(obj)
    return obj


def test_receipts_failures_and_evidence_roundtrip(project):
    db, pid, run, recorder, chronicle = project
    start = event(recorder, run, 'run_started')
    changed = event(recorder, run, 'file_changed', target='src/main.py', provider='claude', fidelity='NATIVE')
    test = event(recorder, run, 'test_execution', tool='pytest', status='failed', provider='codex', fidelity='NATIVE')
    error = event(recorder, run, 'error')
    end = event(recorder, run, 'run_finished', status='failed', metadata={'run_status':'FAILED'})
    with sqlite3.connect(db) as con:
        before = list(con.iterdump())
    receipt, = chronicle.receipts(pid)
    assert receipt['kind'] == 'work_receipt' and receipt['automated'] is None
    assert receipt['status'] == 'FAILED' and receipt['ended_at'] == end.timestamp
    assert receipt['file_changes'][0]['event_id'] == changed.event_id
    assert receipt['tests'][0]['event_id'] == test.event_id
    assert receipt['evidence_event_ids'] == [e.event_id for e in (start, changed, test, error, end)]
    for eid in receipt['evidence_event_ids']:
        assert chronicle.evidence(pid, run_id=run, event_id=eid).event_id == eid
    failures = chronicle.failures(pid)
    assert len(failures) == 3
    assert {f['event_id'] for f in failures if f['kind'] == 'event_failure'} == {test.event_id, error.event_id}
    failed_run = next(f for f in failures if f['kind'] == 'run_failure')
    assert failed_run['evidence_event_ids'] == [end.event_id]
    assert failed_run['run_source'] == {'table':'runs','run_id':run}
    assert chronicle.receipts(pid) == [receipt] and chronicle.failures(pid) == failures
    cli = CliRunner().invoke(app, ['chronicle', '--view', 'receipts', '--json'])
    assert cli.exit_code == 0 and json.loads(cli.stdout) == [receipt]
    assert json.loads(CliRunner().invoke(app, ['chronicle','--view','failures','--json']).stdout) == failures
    with sqlite3.connect(db) as con:
        assert list(con.iterdump()) == before


@pytest.mark.parametrize('marker,expected', [(True, True), (False, False), ('true', None), (1, None), (None, None)])
def test_automation_requires_explicit_boolean_lifecycle_evidence(project, marker, expected):
    db, pid, run, recorder, chronicle = project
    source = event(recorder, run, 'run_started', metadata={'automated':marker})
    receipt, = chronicle.receipts(pid)
    assert receipt['automated'] is expected
    assert receipt['kind'] == ('automation_receipt' if expected is True else 'work_receipt')
    assert receipt['automation_evidence_event_ids'] == ([source.event_id] if type(marker) is bool else [])
    result = CliRunner().invoke(app, ['chronicle','--view','automations','--json'])
    assert json.loads(result.stdout) == ([receipt] if expected is True else [])


def test_conflicting_declarations_and_tool_metadata_do_not_infer_automation(project):
    db, pid, run, recorder, chronicle = project
    start = event(recorder, run, 'run_started', metadata={'automated': True})
    event(recorder, run, 'tool_execution', metadata={'automated': True})
    end = event(recorder, run, 'run_finished', status='success', metadata={'run_status':'SUCCESS','automated':False})
    receipt, = chronicle.receipts(pid)
    assert receipt['automated'] is None
    assert receipt['automation_evidence_event_ids'] == [start.event_id,end.event_id]
    assert chronicle.failures(pid) == []


def test_no_invented_work_decisions_failures_or_file_changes(project):
    db, pid, run, recorder, chronicle = project
    assert chronicle.receipts(pid) == []  # Unobserved pending work is not a receipt.
    log_event(run, 'ERROR', payload={'automated':True,'status':'failed'}, db_path=db)
    assert chronicle.receipts(pid) == []
    event(recorder, run, 'approval_requested', status='blocked', metadata={'automated':True})
    event(recorder, run, 'file_read', target='read.py')
    event(recorder, run, 'file_changed', target='failed.py', status='failed')
    event(recorder, run, 'tool_execution', metadata={'command':'pytest','exit_code':1})
    receipt, = chronicle.receipts(pid)
    assert receipt['automated'] is None
    assert receipt['file_changes'] == receipt['tests'] == receipt['failures'] == []


def test_legacy_terminal_run_receipt_uses_run_row_source(project):
    db, pid, run, recorder, chronicle = project
    failed = create_run('agent','NATIVE','legacy failure', status='FAILED', db_path=db)
    receipt, = chronicle.receipts(pid)
    assert receipt['run_id'] == failed and receipt['evidence_event_ids'] == []
    failure, = chronicle.failures(pid)
    assert failure['run_source']['run_id'] == failed and failure['evidence_event_ids'] == []
    with sqlite3.connect(db) as con:
        assert con.execute('SELECT status FROM runs WHERE run_id=?',(failed,)).fetchone()[0] == 'FAILED'


@pytest.mark.parametrize('args', [
    ['--view','bad'], ['--view','changes','--run','work'],
    ['--view','receipts','--event','x','--run','work'],
    ['--view','failures','--revision','other'],
    ['--view','receipts','--run','absent'],
])
def test_invalid_history_selection(project, args):
    result = CliRunner().invoke(app, ['chronicle', *args, '--json'])
    assert result.exit_code != 0 and result.stdout == ''


@pytest.mark.parametrize('provider', ['claude','codex'])
def test_real_observers_feed_receipts_without_automation_inference(project, provider):
    from architect.observers.claude import ClaudeObserver
    from architect.observers.codex import CodexObserver
    db, pid, run, recorder, chronicle = project
    if provider == 'claude':
        events = ClaudeObserver(live=True).normalize({
            'hook_event_name':'PostToolUse', 'session_id':'fixture', 'tool_name':'Bash',
            'tool_input':{'command':'pytest -q'}, 'tool_response':{'stdout':'passed'},
        }, run_id=run)
    else:
        events = CodexObserver(live=True).normalize({
            'event_name':'codex.tool_result','timestamp':'2026-01-01T00:00:00Z',
            'attributes':{'conversation.id':'fixture','tool_name':'exec_command','success':False},
        }, run_id=run)
    for obj in events:
        recorder.record(obj)
    receipt, = chronicle.receipts(pid)
    assert receipt['automated'] is None
    assert receipt['observations'][0]['provider'] == provider
    assert receipt['observations'][0]['fidelity'] == 'NATIVE'
    assert receipt['evidence_event_ids'] == [obj.event_id for obj in events]
    if provider == 'claude':
        assert receipt['tests'][0]['status'] is None and receipt['failures'] == []
    else:
        assert receipt['tests'] == [] and len(receipt['failures']) == 1


def test_receipt_identity_update_order_and_project_isolation(project, tmp_path):
    db, pid, run, recorder, chronicle = project
    event(recorder, run, 'run_started')
    original, = chronicle.receipts(pid)
    event(recorder, run, 'run_finished', status='success', metadata={'run_status':'SUCCESS'})
    updated, = chronicle.receipts(pid)
    assert original['receipt_id'] == updated['receipt_id'] and updated['status'] == 'SUCCESS'
    create_run('agent','NATIVE','second',run_id='a',status='SUCCESS',db_path=db)
    with sqlite3.connect(db) as con:
        con.execute('UPDATE runs SET started_at=? WHERE run_id=?',(updated['began_at'],'a'))
    assert [r['run_id'] for r in chronicle.receipts(pid)] == ['a', run]
    with pytest.raises(ValueError, match='Unknown project'):
        chronicle.receipts(pid+1)
    ensure_project(tmp_path/'other', db_path=db)
    with pytest.raises(ValueError, match='exactly one'):
        chronicle.failures(pid)
