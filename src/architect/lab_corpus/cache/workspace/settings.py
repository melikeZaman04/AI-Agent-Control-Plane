from pathlib import Path

_cached = None


def load(path):
    global _cached
    if _cached is None:
        _cached = Path(path).read_text(encoding="utf-8")
    return _cached
