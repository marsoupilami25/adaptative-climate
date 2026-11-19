"""Temperature sensor and external sensor ports (ARCHITECTURE §6)."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.util.unit_conversion import TemperatureConverter

from ...core.model.events import XS_CALL_FAILED, Event
from ...core.model.ports import ExternalSensorAttributes
from ...core.model.values import as_number

if TYPE_CHECKING:
    from ..entry.host import EntryHost

_LOGGER = logging.getLogger(__package__)

TEMPERATURE_UNITS = (UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.KELVIN)


def usable(state: State | None) -> bool:
    """Exists, and is not unavailable / unknown."""
    return state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)


def read_temperature(hass: HomeAssistant, state: State | None) -> float | None:
    """temperature@T: converted to the unit of Home Assistant, None when not valid (CFG-SENS-6)."""
    if not usable(state):
        return None
    try:
        value = float(state.state)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    target = hass.config.units.temperature_unit
    if unit is None:
        return value  # a sensor without unit is read in the unit of Home Assistant
    if unit not in TEMPERATURE_UNITS:
        return None
    return round(TemperatureConverter.convert(value, unit, target), 2)


class TemperatureSensorAdapter:
    """The temperature sensor."""

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self._hass = hass
        self.entity_id = entity_id

    def temperature(self) -> float | None:
        """temperature@T."""
        return read_temperature(self._hass, self._hass.states.get(self.entity_id))


class ExternalSensorAdapter:
    """An external sensor entity (number / input_number)."""

    def __init__(self, host: EntryHost, entity_id: str) -> None:
        self._host = host
        self.entity_id = entity_id

    def attributes(self) -> ExternalSensorAttributes | None:
        """attributes@XS; None when not usable."""
        state = self._host.hass.states.get(self.entity_id)
        if not usable(state):
            return None
        attributes = state.attributes
        return ExternalSensorAttributes(
            unit=attributes.get(ATTR_UNIT_OF_MEASUREMENT),
            step=as_number(attributes.get("step")),
            minimum=as_number(attributes.get("min")),
            maximum=as_number(attributes.get("max")),
        )

    def set_value(self, value: float) -> None:
        """AC=>XS_set_value(v): launched after the stimulus, not awaited."""
        self._host.launch(self._set(value))

    async def _set(self, value: float) -> None:
        domain = self.entity_id.split(".", 1)[0]
        try:
            await self._host.hass.services.async_call(
                domain, "set_value", {ATTR_ENTITY_ID: self.entity_id, "value": value}, blocking=True
            )
        except Exception as err:  # noqa: BLE001 - any error comes back as an event
            _LOGGER.debug("%s set_value(%s) failed: %s", self.entity_id, value, err)
            self._host.submit("AC", Event(XS_CALL_FAILED, self.entity_id))
