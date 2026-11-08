"""Room temperature written to the external sensor of the sources.

Some sources can regulate with an external temperature (a TRV with an
"external temperature" number entity, a thermostat following a probe).
Each mode can name that entity (number or input_number): it gets the
temperature of the room sensor, so the source regulates with the room
temperature. Its offset is then ignored (see const.mode_offsets).

- ExternalSensorWriter: follows the coordinator. A new room temperature
  is written at once, at most every EXTERNAL_SENSOR_MIN_INTERVAL (a later
  change waits, then the latest value is written: battery devices), and
  again every EXTERNAL_SENSOR_RESEND even when it did not change (some
  devices forget it). Nothing is written while the room sensor is
  unavailable.
- The value is converted to the unit of the target entity and rounded to
  its step. A target that is unavailable, or a value out of its range, is
  skipped (logged); errors are logged without failing.
"""

from __future__ import annotations

from datetime import datetime
import logging

import voluptuous as vol

from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter

from ..const import (
    DOMAIN,
    EXTERNAL_SENSOR_MIN_INTERVAL,
    EXTERNAL_SENSOR_RESEND,
    entry_settings,
    external_sensors,
)
from ..coordinator import AdaptativeClimateCoordinator
from .sources import Sources
from .timer import Timer
from .util import is_number, same_temperature

_LOGGER = logging.getLogger(__name__)


class ExternalSensorWriter:
    """Write the room temperature to the external sensor of the sources."""

    def __init__(self, coordinator: AdaptativeClimateCoordinator, sources: Sources) -> None:
        """Initialize from the settings of the entry."""
        self._coordinator = coordinator
        self._hass = coordinator.hass
        self._sources = sources
        # Each target once (several modes may share one).
        self.targets: list[str] = list(
            dict.fromkeys(external_sensors(entry_settings(coordinator.config_entry)).values())
        )
        # Last value written, and when.
        self._last: tuple[float, datetime] | None = None
        # Writes a change once the minimum interval passed.
        self._wait = Timer(self._hass)
        # Writes the value again, even unchanged.
        self._resend = Timer(self._hass)
        self._unsub: CALLBACK_TYPE | None = None

    @callback
    def start(self) -> None:
        """Write the room temperature now, then follow it."""
        self._unsub = self._coordinator.async_add_listener(self._on_update)
        self._on_update()

    @callback
    def stop(self) -> None:
        """Stop following the room temperature."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        self._wait.cancel()
        self._resend.cancel()

    @callback
    def _on_update(self) -> None:
        """Write a new room temperature, at most every minimum interval."""
        value = self._sources.sensor_temperature()
        if value is None or self._wait.active:
            return
        if self._last is not None:
            last_value, last_time = self._last
            if same_temperature(value, last_value):
                return
            wait = last_time + EXTERNAL_SENSOR_MIN_INTERVAL - dt_util.utcnow()
            if wait.total_seconds() > 0:
                self._wait.start(wait, self._write)
                return
        self._write()

    @callback
    def _write(self) -> None:
        """Write the current room temperature to every target."""
        value = self._sources.sensor_temperature()
        if value is None:
            return
        self._last = (value, dt_util.utcnow())
        self._resend.start(EXTERNAL_SENSOR_RESEND, self._write)
        self._coordinator.config_entry.async_create_background_task(
            self._hass,
            self._async_write(value),
            f"{DOMAIN} external sensor {value}",
        )

    async def _async_write(self, value: float) -> None:
        """Write a value to every target, as each one takes it."""
        for entity_id in self.targets:
            target_value = self._fit(entity_id, value)
            if target_value is None:
                continue
            try:
                await self._hass.services.async_call(
                    entity_id.split(".", 1)[0],
                    "set_value",
                    {ATTR_ENTITY_ID: entity_id, "value": target_value},
                    blocking=True,
                )
            except (HomeAssistantError, vol.Invalid) as err:
                _LOGGER.warning(
                    "Could not write the room temperature %s to %s: %s",
                    target_value,
                    entity_id,
                    err,
                )

    def _fit(self, entity_id: str, value: float) -> float | None:
        """Return a value as a target takes it: its unit, its step, its range.

        None when the target is unavailable or the value is out of its range.
        """
        state = self._hass.states.get(entity_id)
        if state is None or state.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
            _LOGGER.debug("External sensor %s unavailable, not written", entity_id)
            return None
        attrs = state.attributes
        unit = attrs.get(ATTR_UNIT_OF_MEASUREMENT)
        system = self._hass.config.units.temperature_unit
        if unit in TemperatureConverter.VALID_UNITS and unit != system:
            value = TemperatureConverter.convert(value, system, unit)
        step = attrs.get("step")
        if is_number(step) and step > 0:
            value = round(round(value / step) * step, 6)
        low, high = attrs.get("min"), attrs.get("max")
        if (is_number(low) and value < low) or (is_number(high) and value > high):
            _LOGGER.warning(
                "Room temperature %s out of the range of %s (%s-%s), not written",
                value,
                entity_id,
                low,
                high,
            )
            return None
        return value
