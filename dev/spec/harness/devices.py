"""Fake source entities: real `climate` entities of Home Assistant, played by the test.

A `Device` is the appliance behind a source entity. It outlives the Home
Assistant instances (a device keeps running while Home Assistant restarts);
each instance shows it through a `DeviceEntity` of the test integration
`bench`.

The test plays the device:

- `await device.set(...)` changes it on the device side (remote, app): a
  takeover, a capability change, `unavailable` (`available=False`) or
  `unknown` (`hvac_mode=None`);
- the service calls of Home Assistant (`climate.set_hvac_mode`...) are
  recorded in `device.calls`, then obeyed at once (default), after
  `delay` seconds, never (`obey=False`), or fail (`fail`).

Nothing here knows the integration under test.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

#: The attributes a device shows, and that a test can set.
SHOWN = (
    "hvac_mode",
    "hvac_modes",
    "hvac_action",
    "available",
    "current_temperature",
    "temperature",
    "target_temp_low",
    "target_temp_high",
    "min_temp",
    "max_temp",
    "target_temp_step",
    "fan_mode",
    "fan_modes",
    "swing_mode",
    "swing_modes",
    "swing_horizontal_mode",
    "swing_horizontal_modes",
    "single_target",
    "range_target",
    "unit",
)

SERVICES = (
    "set_hvac_mode",
    "set_temperature",
    "set_fan_mode",
    "set_swing_mode",
    "set_swing_horizontal_mode",
)


@dataclass
class Call:
    """A service call received by a device."""

    service: str
    data: dict[str, Any]

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self.data.items())
        return f"{self.service}({args})"


@dataclass
class Device:
    """A climate device behind a fake source entity.

    `profiles` gives, per HVAC mode (and `off`), the attributes the device
    shows while it runs that mode (another range in cool, the low/high
    targets in heat_cool only...): they are applied when it enters the
    mode, by a call or by `set`.
    """

    entity_id: str
    hvac_modes: list[str]
    hvac_mode: str | None = "off"
    hvac_action: str | None = None
    available: bool = True
    present: bool = True
    current_temperature: float | None = 20.0
    temperature: float | None = 20.0
    target_temp_low: float | None = None
    target_temp_high: float | None = None
    min_temp: float | None = 7.0
    max_temp: float | None = 35.0
    target_temp_step: float | None = None
    fan_mode: str | None = None
    fan_modes: list[str] | None = None
    swing_mode: str | None = None
    swing_modes: list[str] | None = None
    swing_horizontal_mode: str | None = None
    swing_horizontal_modes: list[str] | None = None
    #: Shows a single target (TARGET_TEMPERATURE), a low/high pair (TARGET_TEMPERATURE_RANGE).
    single_target: bool = True
    range_target: bool = False
    unit: str = UnitOfTemperature.CELSIUS
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Behavior towards the calls of Home Assistant
    obey: bool = True
    delay: float = 0.0
    fail: set[str] = field(default_factory=set)
    calls: list[Call] = field(default_factory=list)
    # Bound to the current Home Assistant instance by the bench
    hass: HomeAssistant | None = field(default=None, repr=False)
    entity: DeviceEntity | None = field(default=None, repr=False)
    add_entities: AddEntitiesCallback | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if "off" not in self.hvac_modes:
            self.hvac_modes = ["off", *self.hvac_modes]
        if self.hvac_mode in self.profiles:
            self._apply(self.profiles[self.hvac_mode])

    # --- Calls received ---------------------------------------------------------------

    def calls_of(self, service: str) -> list[Call]:
        """The calls of one service, in order."""
        return [call for call in self.calls if call.service == service]

    def modes_asked(self) -> list[str]:
        """The modes asked by `set_hvac_mode`, in order."""
        return [call.data["hvac_mode"] for call in self.calls_of("set_hvac_mode")]

    def clear_calls(self) -> None:
        """Forget the calls received so far."""
        self.calls.clear()

    async def _receive(self, service: str, data: dict[str, Any]) -> None:
        """A service call of Home Assistant reaches the device."""
        self.calls.append(Call(service, dict(data)))
        if service in self.fail:
            raise HomeAssistantError(f"{self.entity_id}: {service} failed (test)")
        if not self.obey:
            return
        if self.delay <= 0:
            self._obey(service, data)
            return
        assert self.hass is not None

        def later(_now: Any) -> None:
            self._obey(service, data)

        async_call_later(self.hass, self.delay, later)

    def _obey(self, service: str, data: dict[str, Any]) -> None:
        if service == "set_hvac_mode":
            self._enter(str(data["hvac_mode"]))
        elif service == "set_temperature":
            for key in ("temperature", "target_temp_low", "target_temp_high"):
                if key in data:
                    setattr(self, key, data[key])
            if "hvac_mode" in data:
                self._enter(str(data["hvac_mode"]))
        else:
            setattr(self, service.removeprefix("set_"), data[service.removeprefix("set_")])
        self.write()

    def _enter(self, mode: str) -> None:
        self.hvac_mode = mode
        if mode in self.profiles:
            self._apply(self.profiles[mode])

    def _apply(self, values: dict[str, Any]) -> None:
        for key, value in values.items():
            if key not in SHOWN:
                raise AttributeError(f"Device has no attribute {key}")
            setattr(self, key, value)

    # --- Changes on the device side -------------------------------------------------------

    async def set(self, **values: Any) -> None:
        """Change the device on its side (remote, app), then let Home Assistant settle.

        `hvac_mode` applies the profile of the mode first, then the other
        values given.
        """
        if "hvac_mode" in values and values["hvac_mode"] is not None:
            self._enter(values.pop("hvac_mode"))
        elif "hvac_mode" in values:
            self.hvac_mode = values.pop("hvac_mode")
        self._apply(values)
        self.write()
        await self._settle()

    async def appear(self) -> None:
        """The source entity appears in Home Assistant (its integration loads late)."""
        self.present = True
        if self.add_entities is not None and self.entity is None:
            self.add_entities([DeviceEntity(self)])
        await self._settle()

    async def remove(self) -> None:
        """The source entity is removed from Home Assistant."""
        self.present = False
        if self.entity is not None:
            entity, self.entity = self.entity, None
            await entity.async_remove()
        await self._settle()

    def write(self) -> None:
        """Show the device as it is now."""
        if self.entity is not None and self.entity.hass is not None:
            self.entity.async_write_ha_state()

    async def _settle(self) -> None:
        if self.hass is not None:
            await self.hass.async_block_till_done()

    # --- What Home Assistant reads -------------------------------------------------------

    def features(self) -> ClimateEntityFeature:
        """The supported features, from what the device shows."""
        features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        if self.single_target:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        if self.range_target:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        if self.fan_modes:
            features |= ClimateEntityFeature.FAN_MODE
        if self.swing_modes:
            features |= ClimateEntityFeature.SWING_MODE
        if self.swing_horizontal_modes:
            features |= ClimateEntityFeature.SWING_HORIZONTAL_MODE
        return features


class DeviceEntity(ClimateEntity):
    """The source entity of a device, in one Home Assistant instance."""

    _attr_should_poll = False
    # Home Assistant before 2025.x: the device declares TURN_ON / TURN_OFF itself
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, device: Device) -> None:
        self.device = device
        self.entity_id = device.entity_id
        self._attr_unique_id = f"bench_{device.entity_id}"
        self._attr_name = device.entity_id.split(".", 1)[1]
        device.entity = self

    @property
    def available(self) -> bool:
        return self.device.available

    @property
    def hvac_mode(self) -> HVACMode | None:
        mode = self.device.hvac_mode
        return HVACMode(mode) if mode is not None else None

    @property
    def hvac_modes(self) -> list[HVACMode]:
        return [HVACMode(mode) for mode in self.device.hvac_modes]

    @property
    def hvac_action(self) -> HVACAction | None:
        action = self.device.hvac_action
        return HVACAction(action) if action is not None else None

    @property
    def supported_features(self) -> ClimateEntityFeature:
        return self.device.features()

    # Temperatures: both names, before and from Home Assistant 2026.11

    @property
    def temperature_unit(self) -> str:
        return self.device.unit

    @property
    def native_temperature_unit(self) -> str:
        return self.device.unit

    @property
    def current_temperature(self) -> float | None:
        return self.device.current_temperature

    @property
    def native_current_temperature(self) -> float | None:
        return self.device.current_temperature

    @property
    def target_temperature(self) -> float | None:
        return self.device.temperature if self.device.single_target else None

    @property
    def native_target_temperature(self) -> float | None:
        return self.target_temperature

    @property
    def target_temperature_low(self) -> float | None:
        return self.device.target_temp_low if self.device.range_target else None

    @property
    def native_target_temperature_low(self) -> float | None:
        return self.target_temperature_low

    @property
    def target_temperature_high(self) -> float | None:
        return self.device.target_temp_high if self.device.range_target else None

    @property
    def native_target_temperature_high(self) -> float | None:
        return self.target_temperature_high

    @property
    def min_temp(self) -> float:
        if self.device.min_temp is None:
            return super().min_temp
        return self.device.min_temp

    @property
    def max_temp(self) -> float:
        if self.device.max_temp is None:
            return super().max_temp
        return self.device.max_temp

    @property
    def target_temperature_step(self) -> float | None:
        return self.device.target_temp_step

    @property
    def fan_mode(self) -> str | None:
        return self.device.fan_mode

    @property
    def fan_modes(self) -> list[str] | None:
        return self.device.fan_modes

    @property
    def swing_mode(self) -> str | None:
        return self.device.swing_mode

    @property
    def swing_modes(self) -> list[str] | None:
        return self.device.swing_modes

    @property
    def swing_horizontal_mode(self) -> str | None:
        return self.device.swing_horizontal_mode

    @property
    def swing_horizontal_modes(self) -> list[str] | None:
        return self.device.swing_horizontal_modes

    async def async_will_remove_from_hass(self) -> None:
        if self.device.entity is self:
            self.device.entity = None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self.device._receive("set_hvac_mode", {"hvac_mode": str(hvac_mode)})

    async def async_set_temperature(self, **kwargs: Any) -> None:
        data = {k: (str(v) if k == "hvac_mode" else v) for k, v in kwargs.items()}
        await self.device._receive("set_temperature", data)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self.device._receive("set_fan_mode", {"fan_mode": fan_mode})

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        await self.device._receive("set_swing_mode", {"swing_mode": swing_mode})

    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode: str) -> None:
        await self.device._receive(
            "set_swing_horizontal_mode", {"swing_horizontal_mode": swing_horizontal_mode}
        )


def bind_devices(
    hass: HomeAssistant, devices: Iterable[Device], add_entities: AddEntitiesCallback
) -> None:
    """At the start of an instance: each present device shows its source entity."""
    for device in devices:
        device.hass = hass
        device.entity = None
        device.add_entities = add_entities
    add_entities([DeviceEntity(device) for device in devices if device.present])
