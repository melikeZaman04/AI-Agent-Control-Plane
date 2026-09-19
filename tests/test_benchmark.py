import json
from pathlib import Path
import sys

import pytest
from typer.testing import CliRunner

from architect.benchmark import run_suite, compare
from architect.cli.main import app
from architect.storage.db import ensure_project
from test_git_history import git, commit, repo


def suite_file(repo, cases):
    path=repo/'suite.json'
    path.write_text(json.dumps({'version':1,'cases':cases}))
    return path


def case(**overrides):
    return {'id':'sample','task':'same-task','agent':'fixture','model':'local-fixture',
            'argv':[sys.executable,'-c','print("OK")'], 'stdout_contains':'OK', **overrides}


@pytest.fixture
def source(repo):
    (repo/'AGENTS.md').write_text('Read source evidence.\n')
    (repo/'source.py').write_text('def fixture(): return 1\n')
    commit(repo)
    return repo


def test_repeatable_isolated_runs_context_usage_and_receipt_privacy(source):
    script='''from pathlib import Path
import json, sys
bundle = json.load(open(sys.argv[1]))
assert bundle['snippets']
assert not Path("mutation").exists()
Path("mutation").write_text("trial")
print(json.dumps({"result":"OK PRIVATE", "usage":{"input_tokens":11,"output_tokens":3}}))'''
    path=suite_file(source,[case(argv=[sys.executable,'-c',script,'{context_file}'],repeats=2,
                                 context={'strategy':'bootstrap','query':'fixture'})])
    report=run_suite(source,path)
    assert all(r['passed'] for r in report['results'])
    assert not (source/'mutation').exists()
    first,second=report['results']
    assert first['stdout_sha256']==second['stdout_sha256']
    assert first['context_sha256']==second['context_sha256']
    assert first['context_characters']>0 and first['usage']=={'input_tokens':11,'output_tokens':3}
    assert first['usage_source']=='command_reported'
    encoded=json.dumps(report)
    assert 'PRIVATE' not in encoded and script not in encoded
    receipt=source/'.architect/benchmarks'/f"{report['benchmark_id']}.json"
    assert json.loads(receipt.read_text())==report
    comparison,=compare([report])
    assert comparison['trials']==2 and comparison['success_rate']==1
    assert comparison['mean_reported_input_tokens']==11


def test_expected_failures_timeouts_and_launch_errors(source):
    report=run_suite(source,suite_file(source,[
        case(id='failed',argv=[sys.executable,'-c','raise SystemExit(2)']),
        case(id='timeout',argv=[sys.executable,'-c','import time; time.sleep(10)'],timeout_seconds=.05),
        case(id='missing',argv=['/definitely/missing/executable']),
    ]))
    assert [r['passed'] for r in report['results']]==[False,False,False]
    assert report['results'][1]['timed_out'] is True
    assert report['results'][2]['execution_error']=='FileNotFoundError'
    assert all(r['usage'] is None for r in report['results'])


def test_full_validation_precedes_any_command(source):
    command=case(argv=[sys.executable,'-c',f'from pathlib import Path; Path({str(source/"MUTATED")!r}).touch()'])
    bad=case(id='bad',timeout_seconds=-1)
    with pytest.raises(ValueError): run_suite(source,suite_file(source,[command,bad]))
    assert not (source/'MUTATED').exists()


def test_dirty_sources_rejected_and_context_file_placeholder(source):
    path=suite_file(source,[case(argv=[sys.executable,'-c',
        'import json,sys; assert "snippets" in json.load(open(sys.argv[1])); print("OK")','{context_file}'])])
    assert run_suite(source,path)['results'][0]['passed'] is True
    (source/'source.py').write_text('dirty')
    with pytest.raises(ValueError,match='clean tracked'):
        run_suite(source,path)


def test_models_strategies_are_separate_comparison_groups(source):
    report=run_suite(source,suite_file(source,[case(id='a',model='model-a'),
        case(id='b',model='model-b',context={'strategy':'bootstrap','query':'fixture'},
             argv=[sys.executable,'-c',
                   'import json,sys; assert json.load(open(sys.argv[1]))["snippets"]; print("OK")',
                   '{context_file}'])]))
    result=compare([report])
    assert {(r['model'],r['context_strategy']) for r in result}=={('model-a','none'),('model-b','bootstrap')}
    assert all(r['usage_reported_trials']==0 and r['mean_reported_input_tokens'] is None for r in result)


def test_cli_uses_real_receipts(source, monkeypatch):
    monkeypatch.chdir(source)
    ensure_project(source)
    path=suite_file(source,[case()])
    cli=CliRunner()
    result=cli.invoke(app,['benchmark','run',str(path)])
    assert result.exit_code==0, result.stderr
    report=json.loads(result.stdout)
    receipt=source/'.architect/benchmarks'/f"{report['benchmark_id']}.json"
    result=cli.invoke(app,['benchmark','compare',str(receipt)])
    assert result.exit_code==0 and json.loads(result.stdout)[0]['passed']==1


def test_distinct_cases_never_pool_and_duplicate_receipts_rejected(source):
    report=run_suite(source,suite_file(source,[case(id='pass'),
        case(id='fail',stdout_contains='ABSENT')]))
    rows=compare([report])
    assert {r['case_id']:r['success_rate'] for r in rows}=={'pass':1,'fail':0}
    with pytest.raises(ValueError,match='Duplicate'):
        compare([report,report])
