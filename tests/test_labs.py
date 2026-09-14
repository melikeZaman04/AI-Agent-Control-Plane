import json
from pathlib import Path
import sys

import pytest
from typer.testing import CliRunner

from architect.labs import Labs, catalog
from architect.cli.main import app
from architect.storage.db import ensure_project

REPAIRS = {
    "retry": ('ledger.py', '''def credit(state, request_id, amount):
    seen = state.setdefault("seen", set())
    if request_id not in seen:
        state["balance"] = state.get("balance", 0) + amount
        seen.add(request_id)
    return state.get("balance", 0)
'''),
    "cache": ('settings.py', '''from pathlib import Path
def load(path):
    return Path(path).read_text(encoding="utf-8")
'''),
}


@pytest.mark.parametrize("scenario", ["retry", "cache"])
def test_real_failure_repair_repeat_and_stale_progress(tmp_path, scenario):
    labs = Labs(tmp_path)
    session = labs.start(scenario)
    lab_id = session["lab_id"]
    workspace = Path(session["workspace"])
    assert labs.progress(lab_id)["last_result"] == "NOT_CHECKED"
    assert not (workspace / "evaluator.py").exists()
    first = labs.check(lab_id)
    assert first["passed"] is False and first["exit_code"] != 0
    name, repair = REPAIRS[scenario]
    (workspace / name).write_text(repair)
    second = labs.check(lab_id)
    third = labs.check(lab_id)
    assert second["passed"] and third["passed"]
    assert second["files"] == third["files"]
    assert second["check_sha256"] == first["check_sha256"]
    assert second["files"] != first["files"]
    progress = labs.progress(lab_id)
    assert progress == labs.progress(lab_id)
    assert progress["last_result"] == "PASSED"
    assert progress["current_matches_last_check"] is True
    assert progress["mastery"] is None
    assert [a["attempt"] for a in progress["attempts"]] == [1, 2, 3]
    assert "Traceback" not in json.dumps(progress)
    (workspace / name).write_text(repair + "\n# changed\n")
    assert labs.progress(lab_id)["current_matches_last_check"] is False
    assert labs.progress(lab_id)["last_result"] == "PASSED"
    other = labs.start(scenario)
    assert other["workspace"] != str(workspace)
    assert labs.check(other["lab_id"])["passed"] is False


def test_checks_mutate_only_snapshot_and_timeout(tmp_path):
    labs = Labs(tmp_path)
    session = labs.start("retry")
    workspace = Path(session["workspace"])
    (workspace / "ledger.py").write_text(
        'from pathlib import Path\nPath("checker-mutation").touch()\n'
        'def credit(*args): return -1\n')
    assert labs.check(session["lab_id"])["passed"] is False
    assert not (workspace / "checker-mutation").exists()
    (workspace / "ledger.py").write_text('import time\ntime.sleep(10)\n')
    # Shorten the session's bounded timeout, using real subprocess execution.
    metadata = workspace.parent / "session.json"
    record = json.loads(metadata.read_text())
    record["scenario"]["timeout_seconds"] = 1
    metadata.write_text(json.dumps(record))
    result = labs.check(session["lab_id"])
    assert result["timed_out"] and not result["passed"]


def test_invalid_ids_pinned_checks_and_symlinks(tmp_path):
    labs = Labs(tmp_path)
    with pytest.raises(ValueError): labs.start("../retry")
    with pytest.raises(ValueError): labs.progress("../")
    session = labs.start("retry")
    lab_id = session["lab_id"]
    workspace = Path(session["workspace"])
    evaluator = workspace.parent / "evaluator.py"
    evaluator.write_text("raise SystemExit(0)")
    with pytest.raises(ValueError, match="check has changed"): labs.check(lab_id)
    assert not labs.progress(lab_id)["check_matches_pinned"]
    (workspace / "link").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="symlink"): labs.progress(lab_id)


def test_real_cli_catalog_start_check_progress(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_project(tmp_path)
    cli = CliRunner()
    result = cli.invoke(app, ["lab", "list"])
    assert result.exit_code == 0 and len(json.loads(result.stdout)) >= 2
    result = cli.invoke(app, ["lab", "start", "retry"])
    assert result.exit_code == 0, result.stderr
    lab_id = json.loads(result.stdout)["lab_id"]
    result = cli.invoke(app, ["lab", "check", lab_id])
    assert result.exit_code == 0 and json.loads(result.stdout)["passed"] is False
    result = cli.invoke(app, ["lab", "progress", lab_id])
    assert result.exit_code == 0 and json.loads(result.stdout)["last_result"] == "FAILED"
    assert cli.invoke(app, ["lab", "check", "../"]).exit_code == 1
    assert cli.invoke(app, ["lab", "list", "unexpected"]).exit_code == 1
    assert catalog() == catalog()


def test_concurrent_checks_preserve_attempt_order(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    labs = Labs(tmp_path)
    lab_id = labs.start("retry")["lab_id"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        attempts = list(pool.map(lambda _: labs.check(lab_id), range(3)))
    assert sorted(a["attempt"] for a in attempts) == [1, 2, 3]
    progress = labs.progress(lab_id)
    assert [a["attempt"] for a in progress["attempts"]] == [1, 2, 3]
    assert all(not a["passed"] for a in attempts)
