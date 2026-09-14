import json
import sqlite3

import pytest
from typer.testing import CliRunner

from architect.cli.main import app
from architect.session import SessionIntelligence
from architect.recorder.events import ArchitectEvent
from architect.recorder.recorder import FlightRecorder
from architect.storage.db import ensure_project, create_run
from test_git_history import git, commit, repo


@pytest.fixture
def session(repo, monkeypatch):
    monkeypatch.chdir(repo)
    (repo / 'file.txt').write_text('initial')
    first = commit(repo)
    db = repo / '.architect/architect.db'
    pid = ensure_project(repo, db_path=db)
    run = create_run('agent','NATIVE','task',run_id='a',status='PENDING',db_path=db)
    recorder = FlightRecorder(db)
    start = ArchitectEvent(run,'run_started',timestamp='2026-01-01T23:00:00Z')
    test = ArchitectEvent(run,'test_execution',timestamp='2026-01-02T00:30:00Z',status=None)
    recorder.record(start)
    recorder.record(test)
    return SessionIntelligence(db,pid), db, run, recorder, test, first


def test_status_resume_explain_preserve_evidence(session):
    service, db, run, recorder, event, first = session
    with sqlite3.connect(db) as con:
        before = list(con.iterdump())
    status = service.status()
    assert status['recorded_active_run_ids'] == [run] and status['live_process_state'] is None
    resumed = service.resume()
    assert resumed['run']['run_id'] == run and resumed['next_actions'] == []
    assert resumed['provider_resume_command'] is None
    explained = service.explain(run,event_id=event.event_id)
    assert explained['evidence'] == json.loads(event.to_json())
    assert explained['cause'] is None and explained['recommendations'] == []
    assert service.explain(run)['evidence']['evidence_event_ids'][-1] == event.event_id
    assert service.status() == status and service.resume() == resumed
    with sqlite3.connect(db) as con:
        assert list(con.iterdump()) == before


def test_day_timezone_event_boundary_not_run_start_only(session, repo):
    service, db, run, recorder, event, first = session
    utc = service.day(repo,'2026-01-02')
    assert [e['event_id'] for e in utc['work'][0]['observations']] == [event.event_id]
    previous = service.day(repo,'2026-01-01',timezone='America/New_York')
    assert len(previous['work'][0]['observations']) == 2
    assert previous == service.day(repo,'2026-01-01',timezone='America/New_York')
    assert service.day(repo,'2025-01-01')['work'] == []
    assert service.day(repo,'2026-01-01')['commits'][0]['commit_id'] == first


def test_changes_baseline_pinned_and_no_run_attribution(session, repo):
    service, db, run, recorder, event, first = session
    (repo / 'file.txt').write_text('new')
    # Do not accidentally commit test runtime state.
    git(repo,'add','file.txt')
    git(repo,'commit','-qm','second')
    second = git(repo,'rev-parse','HEAD').decode().strip()
    changes = service.changes(repo,since=first)
    assert [c['commit_id'] for c in changes['commits']] == [second]
    assert changes['run_attribution'] is None
    assert service.changes(repo,revision=first,since=first)['commits'] == []
    with pytest.raises(ValueError,match='reachable'):
        service.changes(repo,revision=first,since=second)


@pytest.mark.parametrize('report,args', [
    ('status',[]), ('resume',[]), ('changes',[]), ('day',['--date','2026-01-02']),
    ('explain',['--run','a']),
])
def test_real_cli_repeatability(session, report, args):
    cli = CliRunner()
    command = ['session',report,*args,'--json']
    result = cli.invoke(app,command)
    assert result.exit_code == 0 and result.stderr == ''
    assert json.loads(result.stdout)['report'] == report
    assert cli.invoke(app,command).stdout == result.stdout


@pytest.mark.parametrize('args', [
    ['day'], ['day','--date','invalid'], ['day','--date','2026-01-01','--timezone','invalid'],
    ['explain'], ['explain','--run','absent'], ['resume','--run','absent'],
    ['status','--date','2026-01-01'], ['status','--run','a'], ['invalid'],
])
def test_errors_without_partial_json(session, args):
    result = CliRunner().invoke(app,['session',*args,'--json'])
    assert result.exit_code != 0 and result.stdout == ''


def test_uninitialized_report_does_not_write(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app,['session','status','--json'])
    assert result.exit_code == 1
    assert not (tmp_path/'.architect').exists()


def test_empty_project_resume_has_no_invented_next_action(tmp_path):
    db=tmp_path/'.architect/architect.db'
    pid=ensure_project(tmp_path,db_path=db)
    service=SessionIntelligence(db,pid)
    assert service.resume()['run'] is None
    assert service.status()['runs'] == []
