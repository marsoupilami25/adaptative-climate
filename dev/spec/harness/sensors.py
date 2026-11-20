"""Fake sensors, played by the test.

- `RoomSensor`: a `sensor` entity (the temperature sensor, `temperature_sensor`).
- `ExternalSensor`: a `number` / `input_number` entity of a device (the
  external sensor entities), whose `set_value` calls are recorded.

Like the devices, they outlive the Home Assistant instances: each instance
shows them again at its start.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_UNAVAILABLE, UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall


@dataclass
class RoomSensor:
    """A sensor entity: its state is a value, `unavailable`, `unknown` or any text."""

    entity_id: str
    value: float | str | None = 20.0
    unit: str | None = UnitOfTemperature.CELSIUS
    device_class: str | None = "temperature"
    present: bool = True
    hass: HomeAssistant | None = field(default=None, repr=False)

    def write(self) -> None:
        """Show the sensor as it is now."""
        if self.hass is None:
            return
        if not self.present:
            self.hass.states.async_remove(self.entity_id)
            return
        attributes: dict[str, Any] = {}
        if self.unit is not None:
            attributes["unit_of_measurement"] = self.unit
        if self.device_class is not None:
            attributes["device_class"] = self.device_class
        state = "unknown" if self.value is None else str(self.value)
        self.hass.states.async_set(self.entity_id, state, attributes)

    async def set(self, *value: float | str | None, **changes: Any) -> None:
        """Change the value (`set(21.5)`, `set(None)` for unknown, `set("unavailable")`),
        or `unit`, `present`..., then let Home Assistant settle."""
        if value:
            (self.value,) = value
        for key, item in changes.items():
            setattr(self, key, item)
        self.write()
        if self.hass is not None:
            await self.hass.async_block_till_done()


@dataclass
class ExternalSensor:
    """A `number` / `input_number` entity of a device, written by Home Assistant."""

    entity_id: str
    value: float = 20.0
    minimum: float = 0.0
    maximum: float = 40.0
    step: float = 0.5
    unit: str | None = UnitOfTemperature.CELSIUS
    available: bool = True
    present: bool = True
    fail: bool = False
    values_written: list[float] = field(default_factory=list)
    hass: HomeAssistant | None = field(default=None, repr=False)

    @property
    def domain(self) -> str:
        return self.entity_id.split(".", 1)[0]

    def write(self) -> None:
        """Show the entity as it is now."""
        if self.hass is None:
            return
        if not self.present:
            self.hass.states.async_remove(self.entity_id)
            return
        if not self.available:
            self.hass.states.async_set(self.entity_id, STATE_UNAVAILABLE, {})
            return
        attributes: dict[str, Any] = {"min": self.minimum, "max": self.maximum, "step": self.step}
        if self.unit is not None:
            attributes["unit_of_measurement"] = self.unit
        self.hass.states.async_set(self.entity_id, str(self.value), attributes)

    def receive(self, call: ServiceCall) -> None:
        """A `set_value` call reaches the entity."""
        value = float(call.data["value"])
        self.values_written.append(value)
        if self.fail:
            raise HomeAssistantError(f"{self.entity_id}: set_value failed (test)")
        self.value = value
        self.write()

    async def set(self, **changes: Any) -> None:
        """Change the entity (`available`, `present`, `minimum`...), then let Home Assistant settle."""
        for key, item in changes.items():
            setattr(self, key, item)
        self.write()
        if self.hass is not None:
            await self.hass.async_block_till_done()
