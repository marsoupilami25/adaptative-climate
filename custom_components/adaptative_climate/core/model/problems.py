"""Problem types, and the diff of the problems told the monitoring (MON-SEND).

Spec §4.2, §4.3, §4.4.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

SENSOR_SOURCES = "sources"
SENSOR_TEMPERATURES = "temperatures"

SOURCE_UNUSABLE = "source_unusable"  # MON-SRC-1
SOURCE_NOT_DISCOVERED = "source_not_discovered"  # MON-SRC-5
SOURCE_OUT_OF_SYNC = "source_out_of_sync"  # MON-SRC-3
SETTING_NOT_APPLIED = "setting_not_applied"  # MON-SRC-4
GAP_SENSOR_SOURCE = "gap_sensor_source"  # MON-TEMP-1
GAP_SOURCES = "gap_sources"  # MON-TEMP-1
SENSOR_WITHOUT_VALUE = "sensor_without_value"  # MON-TEMP-4

#: Minimum delay of a setting not applied (CFG-TIMER-2).
SETTING_NOT_APPLIED_MIN_DELAY = 30.0


@dataclass(frozen=True)
class Problem:
    """A problem `p` (MON-SEND-2): its type and subject identify it."""

    kind: str
    subject: tuple[str, ...]
    sensor: str = field(compare=False)
    delay: float = field(compare=False)
    message: str = field(compare=False, default="")
    info: dict[str, Any] = field(compare=False, default_factory=dict)

    @property
    def key(self) -> str:
        """A text key, unique per problem."""
        return "|".join((self.kind, *self.subject))

    def describe(self) -> dict[str, Any]:
        """As in the `problems` attribute (MON-SENS-2)."""
        return {"type": self.kind, **self.info}


class ProblemTracker:
    """Keeps the problems told the monitoring; gives the difference (MON-SEND-1)."""

    def __init__(self) -> None:
        self._told: dict[Problem, Problem] = {}

    def diff(self, current: Iterable[Problem]) -> tuple[list[Problem], list[Problem]]:
        """Problems that began, problems that ended; then remember the current ones."""
        now = {p: p for p in current}
        ups = [p for p in now if p not in self._told]
        downs = [p for p in self._told if p not in now]
        self._told = now
        return ups, downs
