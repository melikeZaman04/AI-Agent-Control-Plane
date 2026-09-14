import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from architect.cli.main import app
from architect.context import LocalContext, KnowledgeProvider
from architect.storage.db import ensure_project
from test_git_history import git, commit, repo


@pytest.fixture
def context(repo):
    (repo/'module.py').write_text('class Demo:\n    def method(self):\n        return 1\n')
    (repo/'AGENTS.md').write_text('Read the canonical project contract.\n')
    commit(repo)
    return LocalContext(repo)


def test_incremental_index_dirty_changes_deletions_and_head(context, repo):
    first = context.refresh()
    assert first['parsed'] == 2 and first['reused'] == 0
    assert context.refresh()['reused'] == 2
    original = context.repo_map()
    assert original['files']['module.py']['symbols'][1]['name'] == 'method'
    assert context.repo_map() == original
    (repo/'module.py').write_text('def replacement():\n    return 2\n')
    with pytest.raises(ValueError,match='changed'):
        context.read('module.py')
    updated=context.refresh()
    assert updated['parsed']==1 and updated['reused']==1
    assert context.read('module.py')['content'].startswith('def replacement')
    (repo/'module.py').unlink()
    assert context.refresh()['removed']==1
    assert 'module.py' not in context.repo_map()['files']
    git(repo,'add','-u')
    git(repo,'commit','-qm','delete module')
    assert context.refresh()['head'] != first['head']


def test_source_reads_search_budget_and_metadata_only_cache(context, repo):
    provider: KnowledgeProvider = context
    hits=provider.search('method')
    assert hits[0]['path']=='module.py'
    assert provider.read('module.py',start=2,end=2)['content']=='    def method(self):\n'
    cache=context.cache.read_text()
    assert 'return 1' not in cache
    result=context.bootstrap('Demo',max_chars=100)
    assert result==context.bootstrap('Demo',max_chars=100)
    assert result['metrics']['characters']<=100
    assert result['metrics']['token_estimator'].endswith('not model tokenization')
    assert all('sha256' in snippet for snippet in result['snippets'])
    tiny=context.bootstrap('Demo',max_chars=1)
    assert tiny['snippets']==[] and tiny['omitted']
    for path in ('../outside','untracked.py'):
        with pytest.raises(ValueError): provider.read(path)


def test_staged_new_files_binary_symlink_and_syntax_error(context, repo):
    (repo/'new.py').write_text('def unfinished(')
    (repo/'binary').write_bytes(b'\0binary')
    (repo/'link').symlink_to('/etc/passwd')
    (repo/'untracked.py').write_text('def ignored(): pass')
    git(repo,'add','new.py','binary','link')
    result=context.refresh()
    assert {'binary','link'} <= result['skipped'].keys()
    files=context.repo_map()['files']
    assert files['new.py']['parse_error'] is True
    assert 'untracked.py' not in files
    (repo/'module.py').unlink()
    (repo/'module.py').symlink_to('/etc/passwd')
    assert 'module.py' in context.refresh()['skipped']


def test_cache_symlink_rejected(context, repo, tmp_path):
    context.refresh()
    context.cache.unlink()
    external=repo/'external.json'
    external.write_text('{"version":1,"files":{}}')
    context.cache.symlink_to(external)
    with pytest.raises(ValueError,match='symlink'):
        context.refresh()
    assert external.read_text()=='{"version":1,"files":{}}'


def test_cli_real_project(context, repo, monkeypatch):
    monkeypatch.chdir(repo)
    ensure_project(repo)
    cli=CliRunner()
    for args in (['index'],['map'],['search','--query','Demo'],
                 ['read','--path','module.py','--start','1','--end','1'],['bootstrap','--query','method']):
        result=cli.invoke(app,['context',*args])
        assert result.exit_code==0, result.stderr
        json.loads(result.stdout)
    (repo/'module.py').write_text('changed')
    result=cli.invoke(app,['context','read','--path','module.py'])
    assert result.exit_code==1 and result.stdout==''


def test_removed_from_git_index_cannot_be_read_from_stale_cache(context, repo):
    context.refresh()
    git(repo,'rm','--cached','module.py')
    assert (repo/'module.py').is_file()
    with pytest.raises(ValueError,match='tracked'):
        context.read('module.py')
