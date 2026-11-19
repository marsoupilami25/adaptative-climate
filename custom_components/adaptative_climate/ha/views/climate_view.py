"""The climate entity, a view of the AC entity of the core (ARCHITECTURE ARCH-8, ENT-HA-1)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from ...const import DOMAIN
from ...core.entity.entity import ClimateView
from ...core.model.events import U_SET_MODE, U_SET_SETTINGS, Event
from ...core.model.values import FAN_MODE, OFF, SWING_HORIZONTAL_MODE, SWING_MODE
from ..entry.host import EntryHost


def device_info(host: EntryHost) -> DeviceInfo:
    """One device per entry, named after it (spec §2.1)."""
    return DeviceInfo(
        identifiers={(DOMAIN, host.model.entry_id)},
        name=host.model.name,
        entry_type=DeviceEntryType.SERVICE,
    )


class AdaptativeClimateEntity(ClimateEntity):
    """`climate.<name>`: shows the state of the core, forwards the user requests."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _unrecorded_attributes = frozenset({"saved_settings"})

    def __init__(self, host: EntryHost) -> None:
        self._host = host
        self._attr_unique_id = f"{host.model.entry_id}_climate"
        self._attr_device_info = device_info(host)
        self._view: ClimateView = host.entity.view()
        self._written: str | None = None

    async def async_added_to_hass(self) -> None:
        """Registered as a view of the host."""
        self._host.views.append(self)

    async def async_will_remove_from_hass(self) -> None:
        """No longer a view."""
        if self in self._host.views:
            self._host.views.remove(self)

    def refresh(self) -> None:
        """Written once per stimulus, after it, when it changed (ARCH-8)."""
        view = self._host.entity.view()
        signature = repr(view)
        if signature == self._written or self.hass is None:
            return
        self._view = view
        self._written = signature
        self.async_write_ha_state()

    # --- State ----------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """Not unavailable, except in INIT and NO_SOURCE."""
        return self._view.available

    @property
    def hvac_mode(self) -> HVACMode | None:
        """The current mode; None in WAITING(m)."""
        mode = self._view.hvac_mode
        return HVACMode(mode) if mode else None

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """off and the configured modes (ENT-HVAC-1)."""
        return [HVACMode(m) for m in self._view.hvac_modes]

    @property
    def hvac_action(self) -> HVACAction | None:
        """The action of the active source, off in OFF, None in WAITING(m)."""
        action = self._view.hvac_action
        if action is None:
            return None
        try:
            return HVACAction(action)
        except ValueError:
            return None

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """ENT-FEAT-3, ENT-FAN-2."""
        return ClimateEntityFeature(self._view.features)

    # Temperatures: both names, before and from Home Assistant 2026.11 (ENT-HA-1)

    @property
    def temperature_unit(self) -> str:
        """The unit of Home Assistant."""
        return self._host.model.unit

    @property
    def native_temperature_unit(self) -> str:
        """The unit of Home Assistant."""
        return self._host.model.unit

    @property
    def current_temperature(self) -> float | None:
        """The reference temperature."""
        return self._view.current_temperature

    @property
    def native_current_temperature(self) -> float | None:
        """The reference temperature."""
        return self._view.current_temperature

    @property
    def target_temperature(self) -> float | None:
        """The single target shown."""
        return self._view.temperature

    @property
    def native_target_temperature(self) -> float | None:
        """The single target shown."""
        return self._view.temperature

    @property
    def target_temperature_low(self) -> float | None:
        """The low target shown."""
        return self._view.target_temp_low

    @property
    def native_target_temperature_low(self) -> float | None:
        """The low target shown."""
        return self._view.target_temp_low

    @property
    def target_temperature_high(self) -> float | None:
        """The high target shown."""
        return self._view.target_temp_high

    @property
    def native_target_temperature_high(self) -> float | None:
        """The high target shown."""
        return self._view.target_temp_high

    @property
    def min_temp(self) -> float:
        """The range shown (ENT-RANGE-2)."""
        return self._view.min_temp

    @property
    def max_temp(self) -> float:
        """The range shown (ENT-RANGE-2)."""
        return self._view.max_temp

    @property
    def target_temperature_step(self) -> float:
        """The step of the entity (ENT-STEP-1)."""
        return self._view.step

    # Fan and swing

    @property
    def fan_mode(self) -> str | None:
        """The fan value shown."""
        return self._view.values.get(FAN_MODE)

    @property
    def fan_modes(self) -> list[str]:
        """The fan options shown."""
        return self._view.options.get(FAN_MODE, [])

    @property
    def swing_mode(self) -> str | None:
        """The swing value shown."""
        return self._view.values.get(SWING_MODE)

    @property
    def swing_modes(self) -> list[str]:
        """The swing options shown."""
        return self._view.options.get(SWING_MODE, [])

    @property
    def swing_horizontal_mode(self) -> str | None:
        """The horizontal swing value shown."""
        return self._view.values.get(SWING_HORIZONTAL_MODE)

    @property
    def swing_horizontal_modes(self) -> list[str]:
        """The horizontal swing options shown."""
        return self._view.options.get(SWING_HORIZONTAL_MODE, [])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Extra attributes (spec §2.2)."""
        return self._view.attributes

    # --- User requests -------------------------------------------------------------------

    def _request(self, event: Event) -> None:
        refusal = self._host.user_request(event)
        if refusal is not None:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key=refusal)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """U=>AC_set_mode(m)."""
        self._request(Event(U_SET_MODE, "U", str(hvac_mode)))

    async def async_turn_on(self) -> None:
        """turn_on: the last used mode, only in OFF (ENT-STATE-8)."""
        self._request(Event(U_SET_MODE, "U", None))

    async def async_turn_off(self) -> None:
        """turn_off: U=>AC_set_mode(off)."""
        self._request(Event(U_SET_MODE, "U", OFF))

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """U=>AC_set_settings with temperature targets, and maybe a mode (ENT-TGT-7)."""
        request: dict[str, Any] = {}
        for name in (ATTR_TEMPERATURE, ATTR_TARGET_TEMP_LOW, ATTR_TARGET_TEMP_HIGH):
            if kwargs.get(name) is not None:
                request[name] = float(kwargs[name])
        if kwargs.get(ATTR_HVAC_MODE) is not None:
            request["hvac_mode"] = str(kwargs[ATTR_HVAC_MODE])
        self._request(Event(U_SET_SETTINGS, "U", request))

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """U=>AC_set_settings(fan_mode)."""
        self._request(Event(U_SET_SETTINGS, "U", {FAN_MODE: fan_mode}))

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """U=>AC_set_settings(swing_mode)."""
        self._request(Event(U_SET_SETTINGS, "U", {SWING_MODE: swing_mode}))

    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode: str) -> None:
        """U=>AC_set_settings(swing_horizontal_mode)."""
        self._request(
            Event(U_SET_SETTINGS, "U", {SWING_HORIZONTAL_MODE: swing_horizontal_mode})
        )
