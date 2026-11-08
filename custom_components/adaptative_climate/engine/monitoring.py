"""Monitoring of the temperature readings.

A source regulates with its own sensor. When it does not read the room
temperature, the room does not reach the target. Monitoring compares:

- the room sensor with what each source reads (only with a sensor),
- the sources with each other (two different entities).

Readings are minus the offset of their mode (see Sources). One entity
serving several modes with the same offset is one reading; with
different offsets, one reading per offset (never compared together).

- Reading: one source reading, with the modes it serves; readings
  builds them from the sources.
- find_gaps: pure function, the gaps above the maximum, by key.
- GapTracker: a gap is a problem once it lasted the duration; tracks
  since when each gap is seen, and when the next one becomes a problem.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import combinations
from typing import Any

from homeassistant.components.climate import HVACMode

from .sources import Sources

# Kinds of gap.
SENSOR_GAP = "sensor"
SOURCES_GAP = "sources"

# Identifies a gap across updates: kind, then the readings compared.
type GapKey = tuple[str, ...]


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
                gaps[(SENSOR_GAP, reading.key)] = Gap(SENSOR_GAP, (reading,), sensor, gap)
    for first, second in combinations(readings, 2):
        if first.entity_id == second.entity_id:
            continue
        gap = abs(first.temperature - second.temperature)
        if gap > max_gap:
            gaps[(SOURCES_GAP, first.key, second.key)] = Gap(
                SOURCES_GAP, (first, second), None, gap
            )
    return gaps


class GapTracker:
    """Tell which gaps are problems: those that lasted the duration.

    A gap that goes away starts again from zero when it comes back.
    """

    def __init__(self, duration: timedelta) -> None:
        """Initialize, without gaps."""
        self._duration = duration
        # When each gap was first seen, while it lasts.
        self._since: dict[GapKey, datetime] = {}

    def update(self, now: datetime, gaps: dict[GapKey, Gap]) -> dict[GapKey, Gap]:
        """Return the gaps that are problems, given the gaps seen now."""
        self._since = {key: self._since.get(key, now) for key in gaps}
        return {
            key: gap
            for key, gap in gaps.items()
            if now - self._since[key] >= self._duration
        }

    def next_problem(self, now: datetime) -> timedelta | None:
        """Return when the next gap seen becomes a problem, if any."""
        waits = [
            since + self._duration - now
            for since in self._since.values()
            if now - since < self._duration
        ]
        return min(waits) if waits else None
