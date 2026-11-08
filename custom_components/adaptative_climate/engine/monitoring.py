"""Monitoring: what the entity and its sources disagree on.

Temperature readings. A source regulates with its own sensor. When it
does not read the room temperature, the room does not reach the target.
Monitoring compares:

- the room sensor with what each source reads (only with a sensor),
- the sources with each other (two different entities).

Readings are minus the offset of their mode (see Sources). One entity
serving several modes with the same offset is one reading; with
different offsets, one reading per offset (never compared together).

Targets (TargetMismatch): the active source shows another target than
the one sent to it, without it being a change made on it (which the
entity takes). Found by TargetSync.mismatches.

Exclusivity (StuckSource): a source does not turn off while another one
runs (see AdaptativeClimateCoordinator.async_enforce_exclusive).

- Reading: one source reading, with the modes it serves; readings
  builds them from the sources.
- find_gaps: pure function, the gaps above the maximum, by key.
- Problem: what every kind of problem gives (key, attributes, log texts).
- ProblemTracker: a problem is reported once it lasted the duration of
  its kind; tracks since when each one is seen, and when the next one is
  reported.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import combinations
from typing import Any, ClassVar, Protocol

from homeassistant.components.climate import HVACMode

from .sources import Sources

# Kinds of problem.
SENSOR_GAP = "sensor"
SOURCES_GAP = "sources"
TARGET_PROBLEM = "target"
EXCLUSIVITY_PROBLEM = "exclusivity"

# Identifies a problem across updates: its kind first, then what it is about.
type ProblemKey = tuple[str, ...]
type GapKey = ProblemKey


class Problem(Protocol):
    """What the monitoring needs from a problem."""

    @property
    def kind(self) -> str:
        """Return the kind of problem (SENSOR_GAP, TARGET_PROBLEM...)."""

    @property
    def key(self) -> ProblemKey:
        """Return what identifies the problem across updates."""

    def as_dict(self) -> dict[str, Any]:
        """Return the problem as a state attribute and event data."""

    def started(self, duration: timedelta, max_gap: float) -> str:
        """Return the log text when the problem starts."""

    def ended(self) -> str:
        """Return the log text when the problem ends."""


@dataclass(frozen=True)
class Reading:
    """What a source reads, minus the offset of its modes."""

    entity_id: str
    modes: tuple[HVACMode, ...]
    temperature: float

    @property
    def key(self) -> str:
        """Return the reading as part of a gap key."""
        return f"{self.entity_id}:{','.join(self.modes)}"

    def as_dict(self) -> dict[str, Any]:
        """Return the reading as a state attribute."""
        return {
            "entity_id": self.entity_id,
            "modes": [str(mode) for mode in self.modes],
            "temperature": self.temperature,
        }


@dataclass(frozen=True)
class Gap:
    """A gap above the maximum between two temperatures."""

    kind: str
    readings: tuple[Reading, ...]
    # The room sensor (sensor gaps only).
    sensor: float | None
    gap: float

    @property
    def key(self) -> ProblemKey:
        """Return the kind, then the readings compared."""
        return (self.kind, *(reading.key for reading in self.readings))

    def started(self, duration: timedelta, max_gap: float) -> str:
        """Return the log text when the gap becomes a problem."""
        return (
            f"temperatures disagree for {duration.total_seconds() // 60:.0f} min, "
            f"above {max_gap}: {self.describe()}"
        )

    def ended(self) -> str:
        """Return the log text when the readings agree again."""
        return "temperatures agree again: " + " and ".join(
            reading.entity_id for reading in self.readings
        ) + (", the room sensor" if self.sensor is not None else "")

    def describe(self) -> str:
        """Return the gap in words, for the logs."""
        sources = " and ".join(
            f"{reading.entity_id} ({', '.join(reading.modes)}) reads {reading.temperature}"
            for reading in self.readings
        )
        if self.sensor is not None:
            return f"{sources}, the room sensor {self.sensor}: gap {self.gap:.1f}"
        return f"{sources}: gap {self.gap:.1f}"

    def as_dict(self) -> dict[str, Any]:
        """Return the gap as a state attribute."""
        data: dict[str, Any] = {
            "type": self.kind,
            "gap": round(self.gap, 2),
            "sources": [reading.as_dict() for reading in self.readings],
        }
        if self.sensor is not None:
            data["sensor_temperature"] = self.sensor
        return data


def readings(sources: Sources) -> list[Reading]:
    """Return what the usable sources read, minus the offset of their modes.

    One reading per entity and offset, with the modes that share it, in mode
    order.
    """
    found: dict[tuple[str, float], tuple[list[HVACMode], float]] = {}
    for mode, entity_id in sources.mode_sources.items():
        temperature = sources.source_temperature(mode)
        if temperature is None:
            continue
        modes, _ = found.setdefault((entity_id, sources.offset(mode)), ([], temperature))
        modes.append(mode)
    return [
        Reading(entity_id, tuple(modes), temperature)
        for (entity_id, _), (modes, temperature) in found.items()
    ]


def find_gaps(
    sensor: float | None, readings: list[Reading], max_gap: float
) -> dict[GapKey, Gap]:
    """Return the gaps above max_gap, by key.

    The sensor against each reading, then each pair of readings of two
    different entities.
    """
    gaps: dict[GapKey, Gap] = {}
    if sensor is not None:
        for reading in readings:
            gap = abs(reading.temperature - sensor)
            if gap > max_gap:
                found = Gap(SENSOR_GAP, (reading,), sensor, gap)
                gaps[found.key] = found
    for first, second in combinations(readings, 2):
        if first.entity_id == second.entity_id:
            continue
        gap = abs(first.temperature - second.temperature)
        if gap > max_gap:
            found = Gap(SOURCES_GAP, (first, second), None, gap)
            gaps[found.key] = found
    return gaps


@dataclass(frozen=True)
class TargetMismatch:
    """The active source shows another target than the one sent to it."""

    kind: ClassVar[str] = TARGET_PROBLEM
    entity_id: str
    # Mode the source runs in.
    mode: HVACMode
    # Target attribute of the source (temperature, target_temp_low...).
    attr: str
    # As the source gets it: plus its offset, rounded, in its range.
    expected: float
    actual: float

    @property
    def key(self) -> ProblemKey:
        """Return the kind, the source and the attribute (not the values)."""
        return (self.kind, self.entity_id, self.attr)

    def as_dict(self) -> dict[str, Any]:
        """Return the mismatch as a state attribute."""
        return {
            "type": self.kind,
            "entity_id": self.entity_id,
            "mode": str(self.mode),
            "attribute": self.attr,
            "expected": self.expected,
            "actual": self.actual,
        }

    def started(self, duration: timedelta, max_gap: float) -> str:
        """Return the log text when the mismatch becomes a problem."""
        return (
            f"{self.entity_id} ({self.mode}) shows {self.attr} {self.actual} instead of "
            f"{self.expected} for {duration.total_seconds() // 60:.0f} min"
        )

    def ended(self) -> str:
        """Return the log text when the source shows the target again."""
        return f"{self.entity_id} shows the {self.attr} sent to it again"


@dataclass(frozen=True)
class StuckSource:
    """A source does not turn off while another one runs."""

    kind: ClassVar[str] = EXCLUSIVITY_PROBLEM
    entity_id: str
    # Mode it runs in.
    mode: str
    # The source that runs and should be the only one.
    running: str
    error: str

    @property
    def key(self) -> ProblemKey:
        """Return the kind and the source."""
        return (self.kind, self.entity_id)

    def as_dict(self) -> dict[str, Any]:
        """Return the stuck source as a state attribute."""
        return {
            "type": self.kind,
            "entity_id": self.entity_id,
            "mode": self.mode,
            "running": self.running,
            "error": self.error,
        }

    def started(self, duration: timedelta, max_gap: float) -> str:
        """Return the log text when the source is found stuck."""
        return (
            f"{self.entity_id} ({self.mode}) does not turn off while {self.running} "
            f"runs ({self.error}); tried again every minute"
        )

    def ended(self) -> str:
        """Return the log text when the source no longer runs with another one."""
        return f"{self.entity_id} no longer runs along with another source"


class ProblemTracker:
    """Tell which problems are reported: those that lasted their duration.

    Each kind has its duration (default otherwise). A problem that goes away
    starts again from zero when it comes back.
    """

    def __init__(
        self, duration: timedelta, durations: Mapping[str, timedelta] | None = None
    ) -> None:
        """Initialize, without problems: duration by kind, else duration."""
        self._duration = duration
        self._durations = dict(durations or {})
        # When each problem was first seen, while it lasts.
        self._since: dict[ProblemKey, datetime] = {}

    def duration(self, kind: str) -> timedelta:
        """Return how long a problem of a kind lasts before it is reported."""
        return self._durations.get(kind, self._duration)

    def update[P: Problem](self, now: datetime, seen: dict[ProblemKey, P]) -> dict[ProblemKey, P]:
        """Return the problems reported, given the problems seen now."""
        self._since = {key: self._since.get(key, now) for key in seen}
        return {
            key: problem
            for key, problem in seen.items()
            if now - self._since[key] >= self.duration(key[0])
        }

    def next_problem(self, now: datetime) -> timedelta | None:
        """Return when the next problem seen is reported, if any."""
        waits = [
            since + self.duration(key[0]) - now
            for key, since in self._since.items()
            if now - since < self.duration(key[0])
        ]
        return min(waits) if waits else None
