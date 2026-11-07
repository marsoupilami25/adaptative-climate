"""Climate platform for Adaptative Climate."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_SWING_HORIZONTAL_MODE,
    ATTR_SWING_HORIZONTAL_MODES,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TARGET_TEMP_STEP,
    DOMAIN as CLIMATE_DOMAIN,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    ATTR_TEMPERATURE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DOMAIN,
    entry_settings,
)
from .coordinator import AdaptativeClimateConfigEntry, AdaptativeClimateCoordinator

# Features this entity implements. Other features of the sources
# (presets, humidity...) are dropped: exposing them without implementing
# them makes Home Assistant fail when the entity is added.
SOURCE_FEATURES = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
)

# Features taken from the source of the current mode only, with the
# attribute listing their options: a heater has no fan, an AC has one.
ACTIVE_SOURCE_FEATURES: tuple[tuple[ClimateEntityFeature, str], ...] = (
    (ClimateEntityFeature.FAN_MODE, ATTR_FAN_MODES),
    (ClimateEntityFeature.SWING_MODE, ATTR_SWING_MODES),
    (ClimateEntityFeature.SWING_HORIZONTAL_MODE, ATTR_SWING_HORIZONTAL_MODES),
)

# set_temperature fields forwarded to the source entity. Home Assistant also
# passes entity_id/area_id/... in kwargs; they must never be forwarded.
# hvac_mode is handled separately, since it can change the source.
FORWARDED_TEMPERATURE_FIELDS: tuple[str, ...] = (
    ATTR_TEMPERATURE,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TARGET_TEMP_HIGH,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AdaptativeClimateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Adaptative Climate entities from a config entry."""
    async_add_entities([AdaptativeClimateEntity(entry.runtime_data)])


class AdaptativeClimateEntity(
    CoordinatorEntity[AdaptativeClimateCoordinator],
    ClimateEntity,
):
    """Climate entity driving one source climate entity per mode.

    The current mode is read from the sources: the entity is in a mode when
    the source of that mode is in the HVAC mode of the same name. Otherwise
    it is off.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: AdaptativeClimateCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._entry = coordinator.config_entry
        self._mode_sources = coordinator.mode_sources
        self._attr_unique_id = self._entry.entry_id
        self._attr_name = self._entry.title
        # Mode restored by turn_on. Kept in memory only.
        self._last_on_mode: HVACMode | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Remember the last mode the entity was on, then update state."""
        mode = self._current_mode()
        if mode is not HVACMode.OFF:
            self._last_on_mode = mode
        super()._handle_coordinator_update()

    # Source helpers

    def _state(self, entity_id: str | None) -> State | None:
        """Return the state of a source entity, if it is usable."""
        if entity_id is None or not self.coordinator.data:
            return None
        state = self.coordinator.data.get(entity_id)
        if state is None or state.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
            return None
        return state

    def _current_mode(self) -> HVACMode:
        """Return the mode whose source runs in that mode, else OFF.

        When several do, the source turned on last wins (it is about to turn
        the others off), then the first mode in order.
        """
        running = [
            (mode, entity_id)
            for mode, entity_id in self._mode_sources.items()
            if (state := self._state(entity_id)) is not None and state.state == mode
        ]
        for mode, entity_id in running:
            if entity_id == self.coordinator.last_on_source:
                return mode
        return running[0][0] if running else HVACMode.OFF

    @property
    def _active_source(self) -> str | None:
        """Return the source of the current mode (None when off)."""
        return self._mode_sources.get(self._current_mode())

    @property
    def _display_source(self) -> str | None:
        """Return the source used for readings: the active one, else the first usable one."""
        active = self._active_source
        if active is not None:
            return active
        for entity_id in self.coordinator.source_entity_ids:
            if self._state(entity_id) is not None:
                return entity_id
        return None

    def _attr_from(self, entity_id: str | None, attr: str) -> Any:
        """Read an attribute from a source entity."""
        state = self._state(entity_id)
        return None if state is None else state.attributes.get(attr)

    def _attr_from_display(self, attr: str) -> Any:
        """Read an attribute from the display source."""
        return self._attr_from(self._display_source, attr)

    # Entity properties

    @property
    def available(self) -> bool:
        """Return True when at least one source is usable."""
        return self._display_source is not None

    def _source_features(self, entity_id: str | None) -> ClimateEntityFeature:
        """Return the supported features of a source entity."""
        return ClimateEntityFeature(
            self._attr_from(entity_id, ATTR_SUPPORTED_FEATURES) or 0
        )

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the features of the sources this entity implements.

        Temperature features are combined over every source, so they do not
        change with the mode. Fan and swing (vertical and horizontal) come
        from the source of the current mode, when it lists at least one option.
        """
        features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        for entity_id in self.coordinator.source_entity_ids:
            features |= self._source_features(entity_id) & SOURCE_FEATURES

        active = self._active_source
        active_features = self._source_features(active)
        for feature, options_attr in ACTIVE_SOURCE_FEATURES:
            if feature in active_features and self._attr_from(active, options_attr):
                features |= feature
        return features

    @property
    def native_temperature_unit(self) -> str:
        """Return the unit of measurement.

        Climate state attributes are always in the system unit, so the
        values read from the sources are in that unit too.
        """
        return self.hass.config.units.temperature_unit

    @property
    def native_current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._attr_from_display(ATTR_CURRENT_TEMPERATURE)

    @property
    def native_target_temperature(self) -> float | None:
        """Return the target temperature."""
        return self._attr_from(self._active_source, ATTR_TEMPERATURE)

    @property
    def native_target_temperature_high(self) -> float | None:
        """Return the high target temperature."""
        return self._attr_from(self._active_source, ATTR_TARGET_TEMP_HIGH)

    @property
    def native_target_temperature_low(self) -> float | None:
        """Return the low target temperature."""
        return self._attr_from(self._active_source, ATTR_TARGET_TEMP_LOW)

    if not hasattr(ClimateEntity, "native_temperature_unit"):
        # Home Assistant < 2026.11 only reads the names without "native_".
        temperature_unit = native_temperature_unit
        current_temperature = native_current_temperature
        target_temperature = native_target_temperature
        target_temperature_high = native_target_temperature_high
        target_temperature_low = native_target_temperature_low

    @property
    def target_temperature_step(self) -> float | None:
        """Return the temperature step of the display source."""
        return self._attr_from_display(ATTR_TARGET_TEMP_STEP)

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature, never below the source's minimum."""
        configured = entry_settings(self._entry).get(CONF_MIN_TEMP, DEFAULT_MIN_TEMP)
        source = self._attr_from_display(ATTR_MIN_TEMP)
        return configured if source is None else max(configured, source)

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature, never above the source's maximum."""
        configured = entry_settings(self._entry).get(CONF_MAX_TEMP, DEFAULT_MAX_TEMP)
        source = self._attr_from_display(ATTR_MAX_TEMP)
        return configured if source is None else min(configured, source)

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current mode."""
        return self._current_mode()

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return OFF plus every mode that has a source configured."""
        return [HVACMode.OFF, *self._mode_sources]

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current action of the active source."""
        if self._current_mode() is HVACMode.OFF:
            return HVACAction.OFF

        action = self._attr_from(self._active_source, ATTR_HVAC_ACTION)
        if action is None:
            return None
        try:
            return HVACAction(action)
        except ValueError:
            return None

    @property
    def fan_mode(self) -> str | None:
        """Return the fan mode of the active source."""
        return self._attr_from(self._active_source, ATTR_FAN_MODE)

    @property
    def fan_modes(self) -> list[str] | None:
        """Return the fan modes of the active source."""
        return self._attr_from(self._active_source, ATTR_FAN_MODES)

    @property
    def swing_mode(self) -> str | None:
        """Return the swing mode of the active source."""
        return self._attr_from(self._active_source, ATTR_SWING_MODE)

    @property
    def swing_modes(self) -> list[str] | None:
        """Return the swing modes of the active source."""
        return self._attr_from(self._active_source, ATTR_SWING_MODES)

    @property
    def swing_horizontal_mode(self) -> str | None:
        """Return the horizontal swing mode of the active source."""
        return self._attr_from(self._active_source, ATTR_SWING_HORIZONTAL_MODE)

    @property
    def swing_horizontal_modes(self) -> list[str] | None:
        """Return the horizontal swing modes of the active source."""
        return self._attr_from(self._active_source, ATTR_SWING_HORIZONTAL_MODES)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return {
            "active_entity_id": self._active_source,
            "mode_entity_ids": {
                str(mode): entity_id for mode, entity_id in self._mode_sources.items()
            },
            # Modes still listed, but whose source cannot be used right now.
            "unavailable_modes": [
                str(mode)
                for mode, entity_id in self._mode_sources.items()
                if self._state(entity_id) is None
            ],
        }

    # Commands

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature on the source of the current mode."""
        hvac_mode = kwargs.get(ATTR_HVAC_MODE)
        if hvac_mode is not None:
            if hvac_mode not in self.hvac_modes:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="unsupported_hvac_mode",
                    translation_placeholders={"hvac_mode": str(hvac_mode)},
                )
            await self.async_set_hvac_mode(HVACMode(hvac_mode))
            if hvac_mode == HVACMode.OFF:
                return
            source = self._mode_sources[HVACMode(hvac_mode)]
        else:
            source = self._require_active_source()

        service_data = {
            key: value
            for key, value in kwargs.items()
            if key in FORWARDED_TEMPERATURE_FIELDS
        }
        if not service_data:
            return

        # Set last: the call must always go to the source entity.
        service_data[ATTR_ENTITY_ID] = source
        await self.hass.services.async_call(
            CLIMATE_DOMAIN,
            "set_temperature",
            service_data,
            blocking=True,
        )

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode of the active source.

        Home Assistant has already checked that fan_mode is in fan_modes.
        """
        await self._async_source_call("set_fan_mode", {ATTR_FAN_MODE: fan_mode})

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set the swing mode of the active source.

        Home Assistant has already checked that swing_mode is in swing_modes.
        """
        await self._async_source_call("set_swing_mode", {ATTR_SWING_MODE: swing_mode})

    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode: str) -> None:
        """Set the horizontal swing mode of the active source.

        Home Assistant has already checked that swing_horizontal_mode is in
        swing_horizontal_modes.
        """
        await self._async_source_call(
            "set_swing_horizontal_mode",
            {ATTR_SWING_HORIZONTAL_MODE: swing_horizontal_mode},
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Switch to a mode.

        Every other source that is not off is turned off first, so two
        sources never run at once, even when several were turned on elsewhere.
        Home Assistant has already checked that hvac_mode is in hvac_modes.
        A mode whose source is unavailable is refused before anything is
        turned off: Home Assistant would skip the call to that source silently.
        """
        target = self._mode_sources.get(hvac_mode)
        if target is not None and self._state(target) is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="source_unavailable",
                translation_placeholders={
                    "hvac_mode": str(hvac_mode),
                    "entity_id": target,
                },
            )
        await self.coordinator.async_turn_off_other_sources(target)

        if target is not None:
            await self._async_source_set_hvac_mode(target, hvac_mode)
            self._last_on_mode = hvac_mode

    async def async_turn_on(self) -> None:
        """Turn on in the last used mode, else the first configured mode."""
        if self._current_mode() is not HVACMode.OFF:
            return

        mode = self._last_on_mode
        if mode not in self._mode_sources:
            mode = next(iter(self._mode_sources), None)
        if mode is not None:
            await self.async_set_hvac_mode(mode)

    async def async_turn_off(self) -> None:
        """Turn off every source that is on."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    def _require_active_source(self) -> str:
        """Return the active source, or refuse the command when off."""
        source = self._active_source
        if source is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_active_mode",
            )
        return source

    async def _async_source_call(self, service: str, data: dict[str, Any]) -> None:
        """Call a climate service on the active source."""
        await self.hass.services.async_call(
            CLIMATE_DOMAIN,
            service,
            {**data, ATTR_ENTITY_ID: self._require_active_source()},
            blocking=True,
        )

    async def _async_source_set_hvac_mode(
        self, entity_id: str, hvac_mode: HVACMode
    ) -> None:
        """Set the HVAC mode of a source entity."""
        await self.hass.services.async_call(
            CLIMATE_DOMAIN,
            "set_hvac_mode",
            {ATTR_ENTITY_ID: entity_id, ATTR_HVAC_MODE: hvac_mode},
            blocking=True,
        )
