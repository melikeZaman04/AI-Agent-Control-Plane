from typing import Protocol
from collections.abc import Mapping
from architect.recorder.events import ArchitectEvent


class Observer(Protocol):
    def normalize(self, payload: Mapping, *, run_id: str) -> list[ArchitectEvent]:
        """Translate evidence only; persistence belongs to FlightRecorder."""
        ...
