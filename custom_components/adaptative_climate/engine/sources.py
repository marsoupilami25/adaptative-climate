"""Access to the source climate entities.

Sources is the only way the engine reads or commands a source. It keeps
no state: it reads what the coordinator received at its last update.

- Reading: state, attr, features. A source missing, unknown or
  unavailable is not usable and reads as None everywhere.
- running_mode: the mode whose source runs in that same mode, else OFF.
  When several do, the one turned on last wins.
- Ranges: range (widest of some sources, Home Assistant defaults
  otherwise), limited_range (narrowed by the configured limits), fit (a
  value as a source gets it: rounded to its step, in its range).
- pair: the low/high targets of the first source that has both.
- room_temperature: the sensor when configured and valid (converted to
  the system unit), else the current temperature of a fallback source.
- async_call: a blocking climate service call on a source. Errors are
  left to the caller.

Sources does not know the mode of the entity: it is the lowest layer.
What depends on the current mode is in ModeTracker.
"""

from __future__ import annotations

import math
from typing import Any

from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TARGET_TEMP_STEP,
    DOMAIN as CLIMATE_DOMAIN,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import DEFAULT_MAX_TEMP, DEFAULT_MIN_TEMP
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import State
from homeassistant.util.unit_conversion import TemperatureConverter

from ..const import CONF_MAX_TEMP, CONF_MIN_TEMP, entry_settings
from ..coordinator import AdaptativeClimateCoordinator
from .util import is_number


class Sources:
    """Read and command the source climate entities.

    Readings come from the coordinator data: a source missing, unknown or
    unavailable is not usable, and reads as None.
    """

    def __init__(self, coordinator: AdaptativeClimateCoordinator) -> None:
        """Initialize from the coordinator."""
        self._coordinator = coordinator
        self._hass = coordinator.hass
        # Source of each configured mode, in display order.
        self.mode_sources = coordinator.mode_sources
        # Each source once, in mode order.
        self.entity_ids = coordinator.source_entity_ids

    def state(self, entity_id: str | None) -> State | None:
        """Return the state of a source entity, if it is usable."""
        data = self._coordinator.data
        if entity_id is None or not data:
            return None
        state = data.get(entity_id)
        if state is None or state.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
            return None
        return state

    def attr(self, entity_id: str | None, attr: str) -> Any:
        """Read an attribute from a source entity."""
        state = self.state(entity_id)
        return None if state is None else state.attributes.get(attr)

    def features(self, entity_id: str | None) -> ClimateEntityFeature:
        """Return the supported features of a source entity."""
        return ClimateEntityFeature(self.attr(entity_id, ATTR_SUPPORTED_FEATURES) or 0)

    def running_mode(self) -> HVACMode:
        """Return the mode whose source runs in that mode, else OFF.

        When several do, the source turned on last wins (it is about to turn
        the others off), then the first mode in order.
        """
        running = [
            (mode, entity_id)
            for mode, entity_id in self.mode_sources.items()
            if (state := self.state(entity_id)) is not None and state.state == mode
        ]
        for mode, entity_id in running:
            if entity_id == self._coordinator.last_on_source:
                return mode
        return running[0][0] if running else HVACMode.OFF

    def pair(self, entity_ids: list[str]) -> tuple[float, float] | None:
        """Return the low/high targets of the first source that has both."""
        for entity_id in entity_ids:
            low = self.attr(entity_id, ATTR_TARGET_TEMP_LOW)
            high = self.attr(entity_id, ATTR_TARGET_TEMP_HIGH)
            if is_number(low) and is_number(high) and low <= high:
                return float(low), float(high)
        return None

    def range(self, entity_ids: list[str]) -> tuple[float, float]:
        """Return the widest temperature range of the given sources.

        Home Assistant defaults when no source gives one.
        """
        mins = [
            value
            for entity_id in entity_ids
            if (value := self.attr(entity_id, ATTR_MIN_TEMP)) is not None
        ]
        maxs = [
            value
            for entity_id in entity_ids
            if (value := self.attr(entity_id, ATTR_MAX_TEMP)) is not None
        ]
        unit = self._hass.config.units.temperature_unit
        low = min(mins) if mins else TemperatureConverter.convert(
            DEFAULT_MIN_TEMP, UnitOfTemperature.CELSIUS, unit
        )
        high = max(maxs) if maxs else TemperatureConverter.convert(
            DEFAULT_MAX_TEMP, UnitOfTemperature.CELSIUS, unit
        )
        return low, high

    def limited_range(self, entity_ids: list[str]) -> tuple[float, float]:
        """Return the range of the given sources, narrowed by the configured limits.

        A limit can only narrow the range. A limit outside the source range
        is ignored, so the minimum always stays below the maximum.
        """
        low, high = self.range(entity_ids)
        settings = entry_settings(self._coordinator.config_entry)
        limit_min = settings.get(CONF_MIN_TEMP)
        limit_max = settings.get(CONF_MAX_TEMP)
        if limit_min is not None and limit_min < high:
            low = max(low, limit_min)
        if limit_max is not None and limit_max > low:
            high = min(high, limit_max)
        return low, high

    def fit(self, value: float, entity_id: str) -> float:
        """Return a value as a source gets it: rounded to its step, in its range."""
        low, high = self.limited_range([entity_id])
        step = self.attr(entity_id, ATTR_TARGET_TEMP_STEP)
        if isinstance(step, (int, float)) and step > 0:
            value = round(math.floor(value / step + 0.5) * step, 6)
        return min(max(value, low), high)

    def room_temperature(self, fallback: str | None) -> float | None:
        """Return the room temperature: the sensor, else the fallback source."""
        sensor = self._coordinator.temperature_sensor
        state = (self._coordinator.data or {}).get(sensor) if sensor else None
        if state is not None:
            try:
                value = float(state.state)
            except ValueError:
                pass
            else:
                if math.isfinite(value):
                    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
                    wanted = self._hass.config.units.temperature_unit
                    if unit in TemperatureConverter.VALID_UNITS and unit != wanted:
                        value = TemperatureConverter.convert(value, unit, wanted)
                    return value
        value = self.attr(fallback, ATTR_CURRENT_TEMPERATURE)
        return float(value) if is_number(value) else None

    async def async_call(
        self, service: str, entity_id: str, data: dict[str, Any]
    ) -> None:
        """Call a climate service on a source entity."""
        await self._hass.services.async_call(
            CLIMATE_DOMAIN,
            service,
            {**data, ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )
