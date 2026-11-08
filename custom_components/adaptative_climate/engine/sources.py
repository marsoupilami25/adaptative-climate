"""Access to the source climate entities.

Sources is the only way the engine reads or commands a source. It keeps
no state: it reads what the coordinator received at its last update.

- Reading: state, attr, features. A source missing, unknown or
  unavailable is not usable and reads as None everywhere.
- running_mode: the mode whose source runs in that same mode, else OFF.
  When several do, the one turned on last wins.
- foreign_modes: the sources running in a mode they do not serve (set
  elsewhere), which the entity ignores.
- Offsets: each mode source may have a temperature offset (how much
  warmer than the room it reads). Values of the entity are those of the
  room; a source gets them plus its offset (fit), and its targets and
  readings minus its offset are those of the room (from_source,
  source_temperature). The offset belongs to the mode, not to the entity:
  one entity serving two modes may have two offsets.
- Ranges: range (widest of some sources, Home Assistant defaults
  otherwise), limited_range (the range of mode sources minus their offset,
  narrowed by the configured limits), fit (a value as the source of a mode
  gets it: plus its offset, rounded to its step, in its range).
- pair: the low/high targets of the first mode source that has both.
- room_temperature: the sensor when configured and valid (converted to
  the system unit), else the current temperature of a fallback mode
  source.
- phase_temperatures: what the combined HEAT_COOL follows: the sensor,
  else the readings of the heat and cool sources.
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

from ..const import CONF_MAX_TEMP, CONF_MIN_TEMP, entry_settings, mode_offsets
from ..coordinator import AdaptativeClimateCoordinator, foreign_mode
from .model import PHASES
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
        # Temperature offset of each mode source.
        self._offsets = mode_offsets(entry_settings(coordinator.config_entry))

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

    def foreign_modes(self) -> dict[str, str]:
        """Return the sources running in a mode they do not serve, with that mode.

        Set elsewhere (remote, app): the entity ignores them.
        """
        return {
            entity_id: mode
            for entity_id in self.entity_ids
            if (
                mode := foreign_mode(
                    self.state(entity_id), self._coordinator.served_modes[entity_id]
                )
            )
            is not None
        }

    def offset(self, mode: HVACMode | None) -> float:
        """Return the temperature offset of the source of a mode (0 for None)."""
        return self._offsets.get(mode, 0.0) if mode is not None else 0.0

    def from_source(self, value: Any, mode: HVACMode | None) -> float | None:
        """Return a temperature of the source of a mode as one of the room."""
        return float(value) - self.offset(mode) if is_number(value) else None

    def pair(self, modes: list[HVACMode]) -> tuple[float, float] | None:
        """Return the low/high targets of the first mode source that has both.

        As targets of the room (minus the offset).
        """
        for mode in modes:
            entity_id = self.mode_sources.get(mode)
            low = self.attr(entity_id, ATTR_TARGET_TEMP_LOW)
            high = self.attr(entity_id, ATTR_TARGET_TEMP_HIGH)
            if is_number(low) and is_number(high) and low <= high:
                offset = self.offset(mode)
                return float(low) - offset, float(high) - offset
        return None

    def range(self, modes: list[HVACMode]) -> tuple[float, float]:
        """Return the widest temperature range of the given mode sources.

        Each one minus its offset: a range of the room. Home Assistant
        defaults when no source gives one.
        """
        bounds: dict[str, list[float]] = {ATTR_MIN_TEMP: [], ATTR_MAX_TEMP: []}
        for mode in modes:
            for attr, values in bounds.items():
                value = self.attr(self.mode_sources.get(mode), attr)
                if is_number(value):
                    values.append(float(value) - self.offset(mode))
        unit = self._hass.config.units.temperature_unit
        mins, maxs = bounds[ATTR_MIN_TEMP], bounds[ATTR_MAX_TEMP]
        low = min(mins) if mins else TemperatureConverter.convert(
            DEFAULT_MIN_TEMP, UnitOfTemperature.CELSIUS, unit
        )
        high = max(maxs) if maxs else TemperatureConverter.convert(
            DEFAULT_MAX_TEMP, UnitOfTemperature.CELSIUS, unit
        )
        return low, high

    def limited_range(self, modes: list[HVACMode]) -> tuple[float, float]:
        """Return the range of the given mode sources, narrowed by the configured limits.

        A range of the room (see range). A limit can only narrow the range. A
        limit outside the source range is ignored, so the minimum always stays
        below the maximum.
        """
        low, high = self.range(modes)
        settings = entry_settings(self._coordinator.config_entry)
        limit_min = settings.get(CONF_MIN_TEMP)
        limit_max = settings.get(CONF_MAX_TEMP)
        if limit_min is not None and limit_min < high:
            low = max(low, limit_min)
        if limit_max is not None and limit_max > low:
            high = min(high, limit_max)
        return low, high

    def fit(self, value: float, mode: HVACMode) -> float:
        """Return a value of the room as the source of a mode gets it.

        Plus its offset, rounded to its step, in its range (narrowed by the
        configured limits, which apply to the room).
        """
        entity_id = self.mode_sources[mode]
        offset = self.offset(mode)
        low, high = self.limited_range([mode])
        value += offset
        step = self.attr(entity_id, ATTR_TARGET_TEMP_STEP)
        if isinstance(step, (int, float)) and step > 0:
            value = round(math.floor(value / step + 0.5) * step, 6)
        return min(max(value, low + offset), high + offset)

    def sensor_temperature(self) -> float | None:
        """Return the temperature of the room sensor, in the system unit."""
        sensor = self._coordinator.temperature_sensor
        state = (self._coordinator.data or {}).get(sensor) if sensor else None
        if state is None:
            return None
        try:
            value = float(state.state)
        except ValueError:
            return None
        if not math.isfinite(value):
            return None
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        wanted = self._hass.config.units.temperature_unit
        if unit in TemperatureConverter.VALID_UNITS and unit != wanted:
            value = TemperatureConverter.convert(value, unit, wanted)
        return value

    def source_temperature(self, mode: HVACMode | None) -> float | None:
        """Return the room temperature read by the source of a mode, minus its offset."""
        entity_id = self.mode_sources.get(mode) if mode is not None else None
        return self.from_source(self.attr(entity_id, ATTR_CURRENT_TEMPERATURE), mode)

    def room_temperature(self, fallback: HVACMode | None) -> float | None:
        """Return the room temperature: the sensor, else the source of the fallback mode."""
        value = self.sensor_temperature()
        return value if value is not None else self.source_temperature(fallback)

    def phase_temperatures(self) -> list[float]:
        """Return the room temperatures the combined HEAT_COOL follows.

        The sensor, else what the heat and cool sources read (the ones that
        do, minus their offset): each reads near its own sensor, they may not
        agree.
        """
        value = self.sensor_temperature()
        if value is not None:
            return [value]
        return [
            value
            for mode in PHASES
            if (value := self.source_temperature(mode)) is not None
        ]

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
