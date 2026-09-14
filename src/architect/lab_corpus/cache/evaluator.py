from pathlib import Path
import sys
import tempfile

sys.path.insert(0, sys.argv[1])
from settings import load

with tempfile.TemporaryDirectory() as folder:
    first = Path(folder) / "first"
    second = Path(folder) / "second"
    first.write_text("old", encoding="utf-8")
    second.write_text("other", encoding="utf-8")
    assert load(first) == "old"
    first.write_text("new", encoding="utf-8")
    assert load(first) == "new"
    assert load(second) == "other"
    first.write_text("", encoding="utf-8")
    assert load(first) == ""
