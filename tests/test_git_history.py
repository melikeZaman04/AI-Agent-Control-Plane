import os
from pathlib import Path
import subprocess

import pytest

from architect.git_history import GitHistory


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE)


def commit(root, message='fixture'):
    git(root, 'add', '-A')
    git(root, 'commit', '-qm', message)
    return git(root, 'rev-parse', 'HEAD').decode().strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    git(tmp_path, 'init', '-q', '-b', 'main')
    git(tmp_path, 'config', 'user.name', 'Fixture')
    git(tmp_path, 'config', 'user.email', 'fixture@example.invalid')
    monkeypatch.setenv('GIT_AUTHOR_DATE', '2026-01-01T00:00:00Z')
    monkeypatch.setenv('GIT_COMMITTER_DATE', '2026-01-01T00:00:00Z')
    return tmp_path


def test_root_change_adr_edit_delete_and_resolution(repo):
    adr = repo / 'docs/adr/ADR-001-example.md'
    adr.parent.mkdir(parents=True)
    adr.write_text('# Decision\nUse local storage.\n')
    odd = 'odd\tline\nü.txt'
    (repo / odd).write_text('first')
    first = commit(repo)
    adr.write_text('# Decision\nUse SQLite.\n')
    (repo / odd).rename(repo / 'renamed.txt')
    second = commit(repo)
    adr.unlink()
    third = commit(repo)
    history = GitHistory(repo)
    before = git(repo, 'status', '--porcelain')
    changes = history.changes()
    assert len(changes) == 3
    assert [c['commit_id'] for c in changes] == sorted([first, second, third])
    by_id = {c['commit_id']: c for c in changes}
    assert by_id[first]['comparison_parent'] is None
    assert {'path': odd, 'status': 'A'} in by_id[first]['changed_paths']
    assert {'path': odd, 'status': 'D'} in by_id[second]['changed_paths']
    assert {'path': 'renamed.txt', 'status': 'A'} in by_id[second]['changed_paths']
    decisions = history.decisions()
    assert len(decisions) == 3
    for decision in decisions:
        source = history.file(decision['source_commit_id'], decision['path'])
        assert source['blob_id'] == decision['blob_id']
        assert source['content'] == git(repo, 'show', decision['source_commit_id'] + ':' + decision['path'])
    deleted = next(d for d in decisions if d['change_status'] == 'D')
    assert deleted['source_commit_id'] == second
    assert history.file(first, odd)['content'] == b'first'
    assert history.changes() == changes and history.decisions() == decisions
    assert git(repo, 'status', '--porcelain') == before


def test_pinned_revision_dirty_tree_and_invalid_sources(repo):
    (repo / 'one').write_text('one')
    first = commit(repo)
    history = GitHistory(repo)
    pinned = history.changes(first)
    (repo / 'one').write_text('uncommitted')
    assert history.changes() == pinned
    assert history.file(first, 'one')['content'] == b'one'
    commit(repo)
    assert history.changes(first) == pinned
    with pytest.raises(ValueError):
        history.changes('--invalid')
    for path in ['../one', '/one', 'absent']:
        with pytest.raises(ValueError):
            history.file(first, path)
    with pytest.raises(ValueError):
        history.file('HEAD', 'one')


def test_empty_repo_and_non_repo(repo, tmp_path):
    assert GitHistory(repo).changes() == []
    assert GitHistory(repo).decisions() == []
    child = repo / 'child'
    child.mkdir()
    with pytest.raises(ValueError, match='repository root'):
        GitHistory(child)
    with pytest.raises(ValueError):
        GitHistory(repo / 'missing')


def test_merge_uses_first_parent_and_includes_branch_commits(repo):
    (repo / 'base').write_text('base')
    base = commit(repo)
    git(repo, 'checkout', '-qb', 'branch')
    (repo / 'branch').write_text('branch')
    branch = commit(repo)
    git(repo, 'checkout', '-q', 'main')
    (repo / 'main').write_text('main')
    main = commit(repo)
    git(repo, 'merge', '--no-ff', '-qm', 'merge', 'branch')
    merge = git(repo, 'rev-parse', 'HEAD').decode().strip()
    changes = GitHistory(repo).changes()
    assert {r['commit_id'] for r in changes} == {base, main, branch, merge}
    record = next(r for r in changes if r['commit_id'] == merge)
    assert record['parents'] == [main, branch]
    assert record['changed_paths'] == [{'path': 'branch', 'status': 'A'}]


def test_symlink_is_not_a_decision_and_git_environment_cannot_redirect(repo, monkeypatch):
    adr = repo / 'docs/adr/ADR-001-link.md'
    adr.parent.mkdir(parents=True)
    adr.symlink_to('/etc/passwd')
    sha = commit(repo)
    monkeypatch.setenv('GIT_DIR', '/invalid')
    history = GitHistory(repo)
    assert history.decisions() == []
    with pytest.raises(ValueError):
        history.file(sha, 'docs/adr/ADR-001-link.md')


def test_git_sqlite_cli_history_and_source_provenance(repo, monkeypatch):
    import json
    from typer.testing import CliRunner
    from architect.cli.main import app
    from architect.storage.db import ensure_project, create_run
    from architect.recorder.recorder import FlightRecorder
    from architect.recorder.events import ArchitectEvent
    monkeypatch.chdir(repo)
    adr = repo / 'docs/adr/ADR-002-storage.md'
    adr.parent.mkdir(parents=True)
    adr.write_text('# ADR-002\n\n## Decision\n\nUse SQLite.\n')
    sha = commit(repo)
    db = repo / '.architect/architect.db'
    ensure_project(repo, db_path=db)
    run = create_run('codex','NATIVE','observation',db_path=db)
    recorder = FlightRecorder(db)
    recorder.record(ArchitectEvent(run,'approval_requested', status='success'))
    cli = CliRunner()
    args = ['chronicle','--view','changes','--revision',sha,'--json']
    result = cli.invoke(app,args)
    assert result.exit_code == 0 and result.stderr == ''
    assert json.loads(result.stdout) == GitHistory(repo).changes(sha)
    assert cli.invoke(app,args).stdout == result.stdout
    decisions = cli.invoke(app,['chronicle','--view','decisions','--json'])
    assert decisions.exit_code == 0
    decision, = json.loads(decisions.stdout)
    assert decision['kind'] == 'adr_revision'  # Tool approval never becomes a decision.
    assert GitHistory(repo).file(decision['source_commit_id'], decision['path'])['content'] == adr.read_bytes()
    assert decision['blob_id'] == git(repo,'rev-parse',sha+':'+decision['path']).decode().strip()
    assert cli.invoke(app,['chronicle','--view','changes']).exit_code == 0
    assert cli.invoke(app,['chronicle','--view','decisions','--revision','absent','--json']).exit_code == 1


def test_non_utf8_filename_roundtrip(repo):
    raw = os.fsencode(repo) + b'/raw-\xff.txt'
    with open(raw, 'wb') as stream:
        stream.write(b'bytes')
    sha = commit(repo)
    history = GitHistory(repo)
    record, = history.changes()
    path = record['changed_paths'][0]['path']
    assert os.fsencode(path) == b'raw-\xff.txt'
    assert history.file(sha, path)['content'] == b'bytes'


def test_adr_filename_pathspec_characters_are_literal(repo):
    adr = repo / 'docs/adr/ADR-[1]*.md'
    adr.parent.mkdir(parents=True)
    adr.write_text('explicit decision record')
    sha = commit(repo)
    record, = GitHistory(repo).decisions()
    assert record['path'] == 'docs/adr/ADR-[1]*.md'
    assert GitHistory(repo).file(sha, record['path'])['content'] == adr.read_bytes()
