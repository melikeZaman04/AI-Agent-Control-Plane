"""Explicit local RESEARCH suites; native agents retain their execution behavior."""

from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import io
import tarfile
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
from uuid import uuid4

from architect.context import LocalContext
from architect.git_history import GitHistory

MAX_EVALUATION_BYTES = 1024 * 1024


def _integer(value):
    return type(value) is int and value >= 0


def validate_suite(suite):
    if not isinstance(suite, dict) or suite.get('version') != 1:
        raise ValueError('Suite version must be 1')
    cases = suite.get('cases')
    if not isinstance(cases, list) or not cases:
        raise ValueError('Suite requires cases')
    names = set()
    for case in cases:
        if not isinstance(case, dict): raise ValueError('Invalid case')
        for field in ('id','agent','model'):
            if not isinstance(case.get(field), str) or not case[field].strip():
                raise ValueError(f'Case requires {field}')
        if not isinstance(case.get('task',case['id']),str) or not case.get('task',case['id']).strip():
            raise ValueError('task must be a nonempty label')
        if case['id'] in names: raise ValueError('Duplicate case ID')
        names.add(case['id'])
        argv = case.get('argv')
        if not isinstance(argv,list) or not argv or not all(isinstance(arg,str) and '\0' not in arg for arg in argv):
            raise ValueError('argv must be a nonempty string array')
        timeout=case.get('timeout_seconds',30)
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0 < timeout <= 300:
            raise ValueError('timeout_seconds must be finite and in (0,300]')
        repeats=case.get('repeats',1)
        if type(repeats) is not int or not 1 <= repeats <= 100:
            raise ValueError('repeats must be 1..100')
        if type(case.get('expected_exit',0)) is not int:
            raise ValueError('expected_exit must be an integer')
        if 'stdout_contains' in case and not isinstance(case['stdout_contains'],str):
            raise ValueError('stdout_contains must be a string')
        context=case.get('context',{})
        if not isinstance(context,dict) or context.get('strategy','none') not in ('none','bootstrap'):
            raise ValueError('Unknown context strategy')
        if context.get('strategy', 'none') == 'bootstrap' and not any('{context_file}' in arg for arg in argv):
            raise ValueError('bootstrap requires {context_file} in argv to pass the context bundle')
        if not isinstance(context.get('query',''),str) or type(context.get('max_chars',12000)) is not int or context.get('max_chars',12000)<1:
            raise ValueError('Invalid context settings')
    return cases


def _fingerprint(stream):
    stream.seek(0)
    digest=sha256()
    size=0
    while block := stream.read(65536):
        size += len(block)
        digest.update(block)
    stream.seek(0)
    return size, digest.hexdigest()


def _execute(argv, root, timeout):
    """POSIX process-group cleanup; output spools are transient, never receipts."""
    started=time.monotonic()
    timed_out=False
    error=None
    code=None
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            process=subprocess.Popen(argv,cwd=root,stdout=stdout,stderr=stderr,start_new_session=True)
            try:
                code=process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out=True
                try: os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                code=process.wait()
            finally:
                # Also stop descendants left running after their parent exits.
                try: os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError: pass
        except OSError as exc:
            error=type(exc).__name__
        elapsed=time.monotonic()-started
        out_bytes,out_hash=_fingerprint(stdout)
        err_bytes,err_hash=_fingerprint(stderr)
        output=stdout.read(MAX_EVALUATION_BYTES).decode('utf-8',errors='replace')
    return {'exit_code':code,'timed_out':timed_out,'execution_error':error,'elapsed_seconds':elapsed,
            'stdout_bytes':out_bytes,'stdout_sha256':out_hash,'stderr_bytes':err_bytes,'stderr_sha256':err_hash}, output


def _snapshot(archive, destination):
    # Extract only directories and regular files; never follow links or device entries.
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        for member in source.getmembers():
            target=destination/member.name
            if not target.resolve().is_relative_to(destination):
                raise ValueError('Invalid source archive path')
            if member.isdir():
                target.mkdir(parents=True,exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True,exist_ok=True)
                with source.extractfile(member) as stream:
                    target.write_bytes(stream.read())
                target.chmod(member.mode & 0o777)
            else:
                raise ValueError('Benchmark snapshots require regular files/directories')


def run_suite(root: str | Path, suite_path: str | Path) -> dict:
    root=Path(root).resolve()
    path=Path(suite_path).resolve()
    raw=path.read_bytes()
    suite=json.loads(raw)
    cases=validate_suite(suite)  # Every case is validated before any command runs.
    history=GitHistory(root)
    head=history._head('HEAD')
    if head is None: raise ValueError('Benchmark requires a committed source snapshot')
    if history._git('diff','--no-ext-diff','--name-only','-z',head,'--'):
        raise ValueError('Benchmark requires clean tracked sources')
    archive=history._git('archive','--format=tar',head)
    directory=root/'.architect/benchmarks'
    if (root/'.architect').is_symlink() or directory.is_symlink():
        raise ValueError('Benchmark result directory cannot be a symlink')
    results=[]
    report={'version':1,'benchmark_id':str(uuid4()),'mode':'RESEARCH','project_root':str(root),
            'suite_path':str(path),'suite_sha256':sha256(raw).hexdigest(),
            'head':head,'source_archive_sha256':sha256(archive).hexdigest(),'started_at':datetime.now(timezone.utc).isoformat(), 'results':results}
    for case in cases:
        context=case.get('context',{})
        strategy=context.get('strategy','none')
        for repetition in range(case.get('repeats',1)):
            bundle=(LocalContext(root).bootstrap(context.get('query',''), max_chars=context.get('max_chars',12000))
                    if strategy=='bootstrap' else {'snippets':[],'metrics':{'characters':0,'estimated_tokens':0}})
            encoded=json.dumps(bundle,sort_keys=True,ensure_ascii=True).encode()
            with tempfile.TemporaryDirectory(prefix='architect-benchmark-') as folder:
                workspace=Path(folder)/'workspace'
                workspace.mkdir()
                _snapshot(archive,workspace)
                for snippet in bundle['snippets']:
                    snapshot_file=workspace/snippet['path']
                    if not snapshot_file.is_file() or sha256(snapshot_file.read_bytes()).hexdigest()!=snippet['sha256']:
                        raise ValueError('Context differs from the pinned benchmark source')
                context_file=Path(folder)/'context.json'
                context_file.write_bytes(encoded)
                argv=[arg.replace('{context_file}',str(context_file)) for arg in case['argv']]
                measured,output=_execute(argv,workspace,case.get('timeout_seconds',30))
            bounded=measured['stdout_bytes']<=MAX_EVALUATION_BYTES
            passed=(not measured['timed_out'] and measured['execution_error'] is None
                    and measured['exit_code']==case.get('expected_exit',0)
                    and ('stdout_contains' not in case or (bounded and case['stdout_contains'] in output)))
            usage=None
            if bounded:
                try:
                    envelope=json.loads(output)
                    candidate=envelope.get('usage') if isinstance(envelope,dict) else None
                    if isinstance(candidate,dict) and all(_integer(candidate.get(key)) for key in ('input_tokens','output_tokens')):
                        usage={key:candidate[key] for key in ('input_tokens','output_tokens')}
                except ValueError: pass
            results.append({**measured,'case_id':case['id'],'task':case.get('task',case['id']),'agent':case['agent'],'model':case['model'],
                            'context_strategy':strategy,'repetition':repetition,'passed':passed,
                            'context_sha256':sha256(encoded).hexdigest(),
                            'context_sources':[{'path':s['path'],'sha256':s['sha256'],'start':s['start'],'end':s['end']} for s in bundle['snippets']],
                            'context_characters':bundle['metrics']['characters'],
                            'context_estimated_tokens':bundle['metrics']['estimated_tokens'],
                            'usage':usage,'usage_source':'command_reported' if usage is not None else None})
    directory=root/'.architect/benchmarks'
    if (root/'.architect').is_symlink() or directory.is_symlink():
        raise ValueError('Benchmark result directory cannot be a symlink')
    directory.mkdir(parents=True,exist_ok=True)
    destination=directory/(report['benchmark_id']+'.json')
    with tempfile.NamedTemporaryFile(mode='w',dir=directory,delete=False) as stream:
        temporary=Path(stream.name)
        json.dump(report,stream,sort_keys=True,ensure_ascii=True)
    try: temporary.replace(destination)
    finally: temporary.unlink(missing_ok=True)
    return report


def compare(reports: list[dict]) -> list[dict]:
    groups=defaultdict(list)
    seen=set()
    for report in reports:
        if report.get('version')!=1 or report.get('mode')!='RESEARCH':
            raise ValueError('Unsupported benchmark report')
        identity=report['benchmark_id']
        if identity in seen:
            raise ValueError('Duplicate benchmark receipt')
        seen.add(identity)
        for result in report['results']:
            groups[(report['suite_sha256'],report['source_archive_sha256'],result['task'],result['case_id'],result['agent'],result['model'],result['context_strategy'])].append(result)
    comparison=[]
    for (suite,source,task,case_id,agent,model,strategy),items in sorted(groups.items()):
        measured=[r['usage'] for r in items if r['usage'] is not None]
        comparison.append({'suite_sha256':suite,'source_archive_sha256':source,'task':task,'case_id':case_id,'agent':agent,'model':model,'context_strategy':strategy,
                           'trials':len(items),'passed':sum(r['passed'] for r in items),
                           'success_rate':sum(r['passed'] for r in items)/len(items),
                           'mean_seconds':sum(r['elapsed_seconds'] for r in items)/len(items),
                           'mean_context_characters':sum(r['context_characters'] for r in items)/len(items),
                           'usage_reported_trials':len(measured),
                           'mean_reported_input_tokens':sum(u['input_tokens'] for u in measured)/len(measured) if measured else None,
                           'mean_reported_output_tokens':sum(u['output_tokens'] for u in measured)/len(measured) if measured else None})
    return comparison
