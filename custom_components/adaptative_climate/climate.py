"""Climate platform for Adaptative Climate."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
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
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_TARGET_ENTITY,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DOMAIN,
)
from .coordinator import AdaptativeClimateConfigEntry, AdaptativeClimateCoordinator

ALLOWED_HVAC_MODES: tuple[HVACMode, ...] = (
    HVACMode.OFF,
    HVACMode.HEAT_COOL,
    HVACMode.DRY,
    HVACMode.FAN_ONLY,
)

# Features this entity implements. Other features of the source entity
# (presets, fan, swing...) are dropped: exposing them without implementing
# them makes Home Assistant fail when the entity is added.
IMPLEMENTED_FEATURES = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    | ClimateEntityFeature.TURN_ON
    | ClimateEntityFeature.TURN_OFF
)

# set_temperature fields forwarded to the source entity. Home Assistant also
# passes entity_id/area_id/... in kwargs; they must never be forwarded.
FORWARDED_TEMPERATURE_FIELDS: tuple[str, ...] = (
    ATTR_TEMPERATURE,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_HVAC_MODE,
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
    """Climate entity wrapping another climate entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AdaptativeClimateCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._entry = coordinator.config_entry
        self._target_entity_id = self._entry.data[CONF_TARGET_ENTITY]
        self._attr_unique_id = self._entry.entry_id
        self._attr_name = self._entry.title

    @property
    def available(self) -> bool:
        """Return if the wrapped climate entity is available."""
        state = self._target_state
        return state is not None and state.state not in {STATE_UNAVAILABLE, STATE_UNKNOWN}

    @property
    def _target_state(self) -> State | None:
        """Return the current state for the wrapped climate entity."""
        return self.coordinator.data

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the source features this entity implements."""
        state = self._target_state
        if state is None:
            return ClimateEntityFeature.TARGET_TEMPERATURE

        raw_features = state.attributes.get(ATTR_SUPPORTED_FEATURES, 0)
        return ClimateEntityFeature(raw_features) & IMPLEMENTED_FEATURES

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement.

        Climate state attributes are always in the system unit, so the
        values read from the source entity are in that unit too.
        """
        return self.hass.config.units.temperature_unit

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._attr_from_target(ATTR_CURRENT_TEMPERATURE)

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        return self._attr_from_target(ATTR_TEMPERATURE)

    @property
    def target_temperature_high(self) -> float | None:
        """Return the high target temperature."""
        return self._attr_from_target(ATTR_TARGET_TEMP_HIGH)

    @property
    def target_temperature_low(self) -> float | None:
        """Return the low target temperature."""
        return self._attr_from_target(ATTR_TARGET_TEMP_LOW)

    @property
    def target_temperature_step(self) -> float | None:
        """Return the temperature step of the wrapped climate entity."""
        return self._attr_from_target(ATTR_TARGET_TEMP_STEP)

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature, never below the source's minimum."""
        configured = self._entry.options.get(
            CONF_MIN_TEMP,
            self._entry.data.get(CONF_MIN_TEMP, DEFAULT_MIN_TEMP),
        )
        source = self._attr_from_target(ATTR_MIN_TEMP)
        return configured if source is None else max(configured, source)

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature, never above the source's maximum."""
        configured = self._entry.options.get(
            CONF_MAX_TEMP,
            self._entry.data.get(CONF_MAX_TEMP, DEFAULT_MAX_TEMP),
        )
        source = self._attr_from_target(ATTR_MAX_TEMP)
        return configured if source is None else min(configured, source)

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return current HVAC mode."""
        state = self._target_state
        if state is None or state.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
            return None

        try:
            hvac_mode = HVACMode(state.state)
        except ValueError:
            return None

        if hvac_mode not in ALLOWED_HVAC_MODES:
            return None

        return hvac_mode

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return available HVAC modes."""
        return list(ALLOWED_HVAC_MODES)

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return current HVAC action."""
        action = self._attr_from_target(ATTR_HVAC_ACTION)
        if action is None:
            return None

        try:
            return HVACAction(action)
        except ValueError:
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return {
            "target_entity_id": self._target_entity_id,
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature on the wrapped climate entity."""
        service_data = {
            key: value
            for key, value in kwargs.items()
            if key in FORWARDED_TEMPERATURE_FIELDS
        }
        hvac_mode = service_data.get(ATTR_HVAC_MODE)
        if hvac_mode is not None and hvac_mode not in self.hvac_modes:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_hvac_mode",
                translation_placeholders={"hvac_mode": str(hvac_mode)},
            )

        # Set last: the call must always go to the source entity.
        service_data[ATTR_ENTITY_ID] = self._target_entity_id
        await self.hass.services.async_call(
            CLIMATE_DOMAIN,
            "set_temperature",
            service_data,
            blocking=True,
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set a new HVAC mode on the wrapped climate entity.

        Home Assistant has already checked that hvac_mode is in hvac_modes.
        """
        await self.hass.services.async_call(
            CLIMATE_DOMAIN,
            "set_hvac_mode",
            {
                ATTR_ENTITY_ID: self._target_entity_id,
                ATTR_HVAC_MODE: hvac_mode,
            },
            blocking=True,
        )

    async def async_turn_on(self) -> None:
        """Turn on the wrapped climate entity."""
        await self.hass.services.async_call(
            CLIMATE_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: self._target_entity_id},
            blocking=True,
        )

    async def async_turn_off(self) -> None:
        """Turn off the wrapped climate entity."""
        await self.hass.services.async_call(
            CLIMATE_DOMAIN,
            "turn_off",
            {ATTR_ENTITY_ID: self._target_entity_id},
            blocking=True,
        )

    def _attr_from_target(self, attr: str) -> Any:
        """Read an attribute from the wrapped climate entity."""
        state = self._target_state
        if state is None:
            return None

        return state.attributes.get(attr)
