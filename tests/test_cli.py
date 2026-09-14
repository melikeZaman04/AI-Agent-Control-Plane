import sqlite3

from typer.testing import CliRunner

from architect.cli.main import app


runner = CliRunner()


def test_init_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    first = runner.invoke(app, ["init"])
    second = runner.invoke(app, ["init"])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "Architect OS initialized" in first.stdout
    assert "ready" in first.stdout
    database = tmp_path / ".architect" / "architect.db"
    assert database.is_file()
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1


def test_run_and_status(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["run", "Flight Recorder CLI test", "--agent", "codex", "--fidelity", "native"],
    )
    status = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "Run ID:" in result.stdout
    assert status.exit_code == 0
    assert "RUNNING: 1" in status.stdout
    database = tmp_path / ".architect" / "architect.db"
    with sqlite3.connect(database) as connection:
        task = connection.execute("SELECT task_description FROM runs").fetchone()[0]
    assert task == "Flight Recorder CLI test"


def test_status_on_new_project_is_empty(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "0" in result.stdout
    assert "run yok" in result.stdout


def test_invalid_fidelity(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app, ["run", "task", "--agent", "codex", "--fidelity", "imaginary"]
    )

    assert result.exit_code != 0
    assert "NATIVE" in result.stderr


def test_missing_required_run_options(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["run", "task"])

    assert result.exit_code != 0
