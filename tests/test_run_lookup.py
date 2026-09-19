import pytest
from typer.testing import CliRunner

from architect.cli.main import app
from architect.recorder.events import ArchitectEvent
from architect.recorder.recorder import FlightRecorder
from architect.storage.db import create_run, get_run


RUN_ID = 'd5e1f3d0-924e-443a-9204-f41af33e9f49'


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / '.architect' / 'architect.db'
    create_run('codex', 'NATIVE', 'prefix test', run_id=RUN_ID, db_path=path)
    FlightRecorder(path).record(ArchitectEvent(RUN_ID, 'file_read', target='example.py'))
    return path


@pytest.mark.parametrize('query', [RUN_ID, 'd5e1f3d0'])
def test_full_and_unique_prefix(database, query):
    assert get_run(query, db_path=database)['run_id'] == RUN_ID
    result = CliRunner().invoke(app, ['inspect', query])
    assert result.exit_code == 0
    assert RUN_ID in result.stdout
    assert 'example.py' in result.stdout


@pytest.mark.parametrize('query', ['deadbeef', '%', '_', ''])
def test_unknown_literal_prefix(database, query):
    assert get_run(query, db_path=database) is None
    result = CliRunner().invoke(app, ['inspect', query])
    assert result.exit_code == 1
    assert 'Unknown run' in result.stdout


def test_ambiguous_prefix(database):
    create_run('codex', 'NATIVE', 'second',
               run_id='d5e1f3d0-0000-4000-8000-000000000000', db_path=database)
    with pytest.raises(ValueError, match='Ambiguous run ID prefix'):
        get_run('d5e1f3d0', db_path=database)
    result = CliRunner().invoke(app, ['inspect', 'd5e1f3d0'])
    assert result.exit_code == 1
    assert 'Ambiguous run ID prefix. Use more characters.' in result.stderr
    assert result.stdout == ''
    assert get_run(RUN_ID, db_path=database)['run_id'] == RUN_ID


def test_exact_match_takes_precedence(database):
    create_run('codex', 'NATIVE', 'custom ID', run_id='d5e1f3d0', db_path=database)
    assert get_run('d5e1f3d0', db_path=database)['run_id'] == 'd5e1f3d0'
