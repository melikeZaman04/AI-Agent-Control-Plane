"""Explicit LEARN exercises with pinned checks and evidence-backed progress."""

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import tempfile
from uuid import uuid4

from architect.benchmark import _execute

CORPUS = Path(__file__).with_name("lab_corpus")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _files(root):
    """Read regular learner files; hashes identify the exact evaluated snapshot."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Lab workspace must be a regular directory")
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Lab files cannot be symlinks")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = path.read_bytes()
        elif not path.is_dir():
            raise ValueError("Lab files must be regular")
    return result


def _hashes(files):
    return {name: sha256(raw).hexdigest() for name, raw in files.items()}


def _write_json(path, value):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, sort_keys=True, ensure_ascii=True)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def catalog():
    result = []
    for directory in sorted(CORPUS.iterdir()):
        if not directory.is_dir():
            continue
        spec = json.loads((directory / "scenario.json").read_bytes())
        if spec.get("version") != 1 or spec.get("id") != directory.name:
            raise ValueError("Invalid bundled scenario")
        result.append(spec)
    return result


class Labs:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.directory = self.root / ".architect/labs"
        self._guard()

    def _guard(self):
        if (self.root / ".architect").is_symlink() or self.directory.is_symlink():
            raise ValueError("Lab storage cannot be a symlink")

    def _session(self, lab_id):
        self._guard()
        if not re.fullmatch(r"[0-9a-f]{32}", lab_id):
            raise ValueError("Invalid lab ID")
        folder = self.directory / lab_id
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError("Lab session not found")
        for name in ("session.json", "evaluator.py", "attempts", "lock"):
            if (folder / name).is_symlink():
                raise ValueError("Lab state cannot be a symlink")
        return folder

    @contextmanager
    def _locked(self, folder):
        with (folder / "lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def start(self, scenario_id):
        spec = next((s for s in catalog() if s["id"] == scenario_id), None)
        if spec is None:
            raise ValueError("Unknown lab scenario")
        self._guard()
        source = CORPUS / scenario_id
        files = _files(source / "workspace")
        check = (source / "evaluator.py").read_bytes()
        lab_id = uuid4().hex
        folder = self.directory / lab_id
        folder.mkdir(parents=True)
        workspace = folder / "workspace"
        workspace.mkdir()
        for name, raw in files.items():
            target = workspace / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        (folder / "evaluator.py").write_bytes(check)
        (folder / "attempts").mkdir()
        record = {"version": 1, "mode": "LEARN", "lab_id": lab_id,
                  "scenario": spec, "started_at": _now(), "workspace": str(workspace),
                  "corpus_path": str(source),
                  "scenario_sha256": sha256((source / "scenario.json").read_bytes()).hexdigest(),
                  "check_sha256": sha256(check).hexdigest(), "initial_files": _hashes(files)}
        _write_json(folder / "session.json", record)
        return record

    def check(self, lab_id):
        folder = self._session(lab_id)
        with self._locked(folder):
            session = json.loads((folder / "session.json").read_bytes())
            checker = (folder / "evaluator.py").read_bytes()
            if sha256(checker).hexdigest() != session["check_sha256"]:
                raise ValueError("Pinned lab check has changed")
            timeout = session["scenario"]["timeout_seconds"]
            if type(timeout) is not int or not 1 <= timeout <= 30:
                raise ValueError("Invalid lab timeout")
            files = _files(folder / "workspace")
            with tempfile.TemporaryDirectory(prefix="architect-lab-") as temporary:
                scratch = Path(temporary)
                work = scratch / "workspace"
                work.mkdir()
                for name, raw in files.items():
                    target = work / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
                script = scratch / "evaluator.py"
                script.write_bytes(checker)
                measured, _ = _execute(
                    [sys.executable, "-I", "-B", str(script), str(work)], work, timeout)
            previous = sorted((folder / "attempts").glob("*.json"))
            # Each successful write is a new explicit attempt, including repeats.
            sequence = len(previous) + 1
            receipt = {"version": 1, "mode": "LEARN", "lab_id": lab_id,
                       "attempt": sequence, "checked_at": _now(),
                       "scenario_id": session["scenario"]["id"],
                       "scenario_sha256": session["scenario_sha256"],
                       "check_sha256": session["check_sha256"], "files": _hashes(files),
                       **measured,
                       "passed": measured["exit_code"] == 0 and not measured["timed_out"]
                                 and measured["execution_error"] is None}
            destination = folder / "attempts" / f"{sequence:06d}.json"
            if destination.exists():
                raise ValueError("Lab attempt history is inconsistent")
            _write_json(destination, receipt)
            return receipt

    def progress(self, lab_id):
        folder = self._session(lab_id)
        with self._locked(folder):
            session = json.loads((folder / "session.json").read_bytes())
            attempts = []
            for path in sorted((folder / "attempts").glob("*.json")):
                if path.is_symlink():
                    raise ValueError("Lab receipt cannot be a symlink")
                receipt = json.loads(path.read_bytes())
                if receipt["lab_id"] != lab_id or receipt["attempt"] != len(attempts) + 1:
                    raise ValueError("Lab attempt history is inconsistent")
                attempts.append(receipt)
            current_files = _hashes(_files(folder / "workspace"))
            last = attempts[-1] if attempts else None
            return {"lab_id": lab_id, "mode": "LEARN", "scenario": session["scenario"],
                    "workspace": str(folder / "workspace"), "attempts": attempts,
                    "last_result": ("PASSED" if last["passed"] else "FAILED") if last else "NOT_CHECKED",
                    "current_matches_last_check": current_files == last["files"] if last else None,
                    "check_matches_pinned": sha256((folder / "evaluator.py").read_bytes()).hexdigest() == session["check_sha256"],
                    "mastery": None}
