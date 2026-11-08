"""Binary sensor platform for Adaptative Climate: the monitoring.

One problem sensor per entry, on when the readings disagree for too long:
the room sensor and a source, or two sources (see engine.monitoring). The
problems are listed in its attributes, and logged when they start (warning)
and end (info). It is only created when there is
something to compare: a room sensor, or two different source entities.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import entry_settings, monitoring_duration, monitoring_gap
from .coordinator import AdaptativeClimateConfigEntry, AdaptativeClimateCoordinator
from .engine.monitoring import Gap, GapKey, GapTracker, find_gaps, readings
from .engine.sources import Sources
from .engine.timer import Timer

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AdaptativeClimateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the monitoring sensor, when there is something to compare."""
    coordinator = entry.runtime_data
    if coordinator.temperature_sensor or len(coordinator.source_entity_ids) > 1:
        async_add_entities([AdaptativeClimateMonitoring(coordinator)])


class AdaptativeClimateMonitoring(
    CoordinatorEntity[AdaptativeClimateCoordinator], BinarySensorEntity
):
    """On when a gap between readings lasted the monitoring duration."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: AdaptativeClimateCoordinator) -> None:
        """Initialize from the settings of the entry."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        settings = entry_settings(entry)
        self._attr_unique_id = f"{entry.entry_id}_monitoring"
        self._attr_name = f"{entry.title} monitoring"
        self._sources = Sources(coordinator)
        self._max_gap = monitoring_gap(settings)
        self._duration = monitoring_duration(settings)
        self._tracker = GapTracker(self._duration)
        # Checks again when the next gap becomes a problem.
        self._timer = Timer(coordinator.hass)
        self._problems: dict[GapKey, Gap] = {}

    async def async_added_to_hass(self) -> None:
        """Check the readings once added."""
        await super().async_added_to_hass()
        self._check()

    async def async_will_remove_from_hass(self) -> None:
        """Stop the timer."""
        self._timer.cancel()
        await super().async_will_remove_from_hass()

    @callback
    def _check(self) -> None:
        """Compare the readings, and plan the next check."""
        now = dt_util.utcnow()
        gaps = find_gaps(
            self._sources.sensor_temperature(), readings(self._sources), self._max_gap
        )
        problems = self._tracker.update(now, gaps)
        self._log(problems)
        self._problems = problems
        wait = self._tracker.next_problem(now)
        if wait is None:
            self._timer.cancel()
        else:
            self._timer.start(wait, self._recheck)

    def _log(self, problems: dict[GapKey, Gap]) -> None:
        """Log the problems that start and those that end."""
        name = self.coordinator.config_entry.title
        for key, gap in problems.items():
            if key not in self._problems:
                _LOGGER.warning(
                    "%s: temperatures disagree for %d min, above %s: %s",
                    name,
                    self._duration.total_seconds() // 60,
                    self._max_gap,
                    gap.describe(),
                )
        for key, gap in self._problems.items():
            if key not in problems:
                _LOGGER.info(
                    "%s: temperatures agree again: %s",
                    name,
                    " and ".join(reading.entity_id for reading in gap.readings)
                    + (", the room sensor" if gap.sensor is not None else ""),
                )

    @callback
    def _recheck(self) -> None:
        """Check again once a gap lasted the duration."""
        self._check()
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Check the readings on each source or sensor update."""
        self._check()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Return True: the monitoring itself is always available."""
        return True

    @property
    def is_on(self) -> bool:
        """Return True when there is a problem."""
        return bool(self._problems)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the problems and the maximum gap."""
        return {
            "max_gap": self._max_gap,
            "problems": [gap.as_dict() for gap in self._problems.values()],
        }
