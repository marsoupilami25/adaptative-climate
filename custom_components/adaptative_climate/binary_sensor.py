"""Binary sensor platform for Adaptative Climate: monitoring, target gap, source unavailable.

The source unavailable sensor, one per entry, is on while a source of the
selected mode is unavailable: the source of the mode the entity runs in
or waits for, or one of the heat and cool sources of the combined
HEAT_COOL. Off while the entity is off. The sources are listed in its
attributes.

The target gap sensor, one per entry, is on while the entity shows a target
otherwise than it keeps it (see TargetSync.gaps): each target is kept in
the widest range of its sources, and the active source cannot reach it. It
gets it, and the entity shows it, in its own range. The gaps are listed in
its attributes.

One problem sensor per entry, on while there is a problem (see
engine.monitoring):

- sensor / sources: the room sensor and a source, or two sources, read
  temperatures too far apart for the monitoring duration;
- target: the active source shows another target than the one sent to
  it for the monitoring duration (TARGET_MIN_DURATION at least: a source
  may take that long to show it);
- exclusivity: a source does not turn off while another one runs
  (reported at once: it was already tried twice).

The problems are listed in its attributes. When one starts it is logged
(warning) and an EVENT_PROBLEM event is fired; when it ends, logged (info)
and fired again.
"""

from __future__ import annotations

from datetime import timedelta
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

from .const import EVENT_PROBLEM, entry_settings, monitoring_duration, monitoring_gap
from .coordinator import AdaptativeClimateConfigEntry, AdaptativeClimateCoordinator
from .engine.model import REQUEST_TIME
from .engine.monitoring import (
    EXCLUSIVITY_PROBLEM,
    TARGET_PROBLEM,
    Problem,
    ProblemKey,
    ProblemTracker,
    StuckSource,
    find_gaps,
    readings,
)
from .engine.sources import Sources
from .engine.timer import Timer

_LOGGER = logging.getLogger(__name__)

# A target the source does not show is a problem after this at least.
TARGET_MIN_DURATION = REQUEST_TIME


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AdaptativeClimateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the monitoring, target gap and source unavailable sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            AdaptativeClimateMonitoring(coordinator),
            AdaptativeClimateTargetGap(coordinator),
            AdaptativeClimateSourceUnavailable(coordinator),
        ]
    )


class AdaptativeClimateMonitoring(
    CoordinatorEntity[AdaptativeClimateCoordinator], BinarySensorEntity
):
    """On while a problem lasted its duration."""

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
        duration = monitoring_duration(settings)
        self._tracker = ProblemTracker(
            duration,
            {
                TARGET_PROBLEM: max(duration, TARGET_MIN_DURATION),
                EXCLUSIVITY_PROBLEM: timedelta(),
            },
        )
        # Checks again when the next problem seen is reported.
        self._timer = Timer(coordinator.hass)
        self._problems: dict[ProblemKey, Problem] = {}

    async def async_added_to_hass(self) -> None:
        """Check once added, and on each change of the target mismatches."""
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_problem_listener(self._recheck))
        self._check()

    async def async_will_remove_from_hass(self) -> None:
        """Stop the timer."""
        self._timer.cancel()
        await super().async_will_remove_from_hass()

    def _seen(self) -> dict[ProblemKey, Problem]:
        """Return every problem seen now, before its duration."""
        coordinator = self.coordinator
        seen: dict[ProblemKey, Problem] = dict(
            find_gaps(
                self._sources.sensor_temperature(), readings(self._sources), self._max_gap
            )
        )
        for mismatch in coordinator.target_mismatches:
            seen[mismatch.key] = mismatch
        for entity_id, (running, error) in coordinator.stuck_sources.items():
            state = self._sources.state(entity_id)
            stuck = StuckSource(
                entity_id, state.state if state is not None else "", running, error
            )
            seen[stuck.key] = stuck
        return seen

    @callback
    def _check(self) -> None:
        """Find the problems, and plan the next check."""
        now = dt_util.utcnow()
        problems = self._tracker.update(now, self._seen())
        self._report(problems)
        self._problems = problems
        wait = self._tracker.next_problem(now)
        if wait is None:
            self._timer.cancel()
        else:
            self._timer.start(wait, self._recheck)

    def _report(self, problems: dict[ProblemKey, Problem]) -> None:
        """Log and fire the problems that start and those that end."""
        name = self.coordinator.config_entry.title
        for key, problem in problems.items():
            if key not in self._problems:
                message = problem.started(self._tracker.duration(key[0]), self._max_gap)
                _LOGGER.warning("%s: %s", name, message)
                self._fire("started", problem, message)
        for key, problem in self._problems.items():
            if key not in problems:
                message = problem.ended()
                _LOGGER.info("%s: %s", name, message)
                self._fire("ended", problem, message)

    def _fire(self, status: str, problem: Problem, message: str) -> None:
        """Fire the event of a problem that starts or ends."""
        entry = self.coordinator.config_entry
        self.hass.bus.async_fire(
            EVENT_PROBLEM,
            {
                "entry_id": entry.entry_id,
                "name": entry.title,
                "entity_id": self.entity_id,
                "status": status,
                "message": message,
                "problem": problem.as_dict(),
            },
        )

    @callback
    def _recheck(self) -> None:
        """Check again: a problem lasted its duration, or the mismatches changed."""
        self._check()
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Check on each source or sensor update."""
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
            "problems": [problem.as_dict() for problem in self._problems.values()],
        }


class AdaptativeClimateTargetGap(
    CoordinatorEntity[AdaptativeClimateCoordinator], BinarySensorEntity
):
    """On while the entity shows a target otherwise than it keeps it."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:thermometer-alert"

    def __init__(self, coordinator: AdaptativeClimateCoordinator) -> None:
        """Initialize from the entry."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_target_gap"
        self._attr_name = f"{entry.title} target gap"

    async def async_added_to_hass(self) -> None:
        """Follow the target gaps given by the climate entity."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_gap_listener(self.async_write_ha_state)
        )

    @property
    def available(self) -> bool:
        """Return True: the gaps are known even when a source is not."""
        return True

    @property
    def is_on(self) -> bool:
        """Return True when a target is shown otherwise than kept."""
        return bool(self.coordinator.target_gaps)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the targets shown otherwise than kept."""
        return {"gaps": [gap.as_dict() for gap in self.coordinator.target_gaps]}


class AdaptativeClimateSourceUnavailable(
    CoordinatorEntity[AdaptativeClimateCoordinator], BinarySensorEntity
):
    """On while a source of the selected mode is unavailable."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:lan-disconnect"

    def __init__(self, coordinator: AdaptativeClimateCoordinator) -> None:
        """Initialize from the entry."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_source_unavailable"
        self._attr_name = f"{entry.title} source unavailable"

    async def async_added_to_hass(self) -> None:
        """Follow the unavailable sources given by the climate entity."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_missing_listener(self.async_write_ha_state)
        )

    @property
    def available(self) -> bool:
        """Return True: it reports the sources that are not."""
        return True

    @property
    def is_on(self) -> bool:
        """Return True when a source of the selected mode is unavailable."""
        return bool(self.coordinator.missing_sources)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the unavailable sources of the selected mode."""
        return {"entity_ids": list(self.coordinator.missing_sources)}
