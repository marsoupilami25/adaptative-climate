"""Fixtures for Adaptative Climate tests."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    setup_test_component_platform,
)
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.climate import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    DOMAIN as CLIMATE_DOMAIN,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, CONF_NAME, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.adaptative_climate.const import (
    CONF_COOL_ENTITY,
    CONF_DRY_ENTITY,
    CONF_HEAT_ENTITY,
    DOMAIN,
)

HEATER = "climate.heater"
AC = "climate.ac"
ENTITY_ID = "climate.living_room"

# Home Assistant 2026.11 renamed the temperature attributes to "native_*".
NATIVE_PREFIX = "native_" if hasattr(ClimateEntity, "native_temperature_unit") else ""
TEMPERATURE_ATTRS = {
    "temperature_unit",
    "current_temperature",
    "target_temperature",
    "target_temperature_high",
    "target_temperature_low",
}


def _attr_name(key: str) -> str:
    """Return the entity attribute name for key on this HA version."""
    if key in TEMPERATURE_ATTRS:
        return f"_attr_{NATIVE_PREFIX}{key}"
    return f"_attr_{key}"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load the integration from custom_components."""


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Serialize Home Assistant objects without ids and timestamps."""
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


class FakeClimate(ClimateEntity):
    """Source climate entity that applies service calls to its own state."""

    _attr_should_poll = False

    def __init__(
        self,
        entity_id: str,
        hvac_modes: list[HVACMode],
        *,
        features: ClimateEntityFeature = ClimateEntityFeature.TARGET_TEMPERATURE,
        **attrs: Any,
    ) -> None:
        """Initialize the fake source."""
        self.entity_id = entity_id
        self._attr_name = entity_id.split(".")[1]
        self._attr_hvac_modes = hvac_modes
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_supported_features = features
        setattr(self, _attr_name("temperature_unit"), UnitOfTemperature.CELSIUS)
        for key, value in attrs.items():
            setattr(self, _attr_name(key), value)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Change the mode."""
        self.calls.append(("set_hvac_mode", {"hvac_mode": hvac_mode}))
        self._attr_hvac_mode = hvac_mode
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Change the target temperature."""
        self.calls.append(("set_temperature", kwargs))
        for attr, key in (
            (ATTR_TEMPERATURE, "target_temperature"),
            (ATTR_TARGET_TEMP_LOW, "target_temperature_low"),
            (ATTR_TARGET_TEMP_HIGH, "target_temperature_high"),
        ):
            if attr in kwargs:
                setattr(self, _attr_name(key), kwargs[attr])
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Change the fan mode."""
        self.calls.append(("set_fan_mode", {"fan_mode": fan_mode}))
        self._attr_fan_mode = fan_mode
        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Change the swing mode."""
        self.calls.append(("set_swing_mode", {"swing_mode": swing_mode}))
        self._attr_swing_mode = swing_mode
        self.async_write_ha_state()

    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode: str) -> None:
        """Change the horizontal swing mode."""
        self.calls.append(
            (
                "set_swing_horizontal_mode",
                {"swing_horizontal_mode": swing_horizontal_mode},
            )
        )
        self._attr_swing_horizontal_mode = swing_horizontal_mode
        self.async_write_ha_state()


@pytest.fixture
def heater() -> FakeClimate:
    """Heat-only source, without fan or swing."""
    return FakeClimate(
        HEATER,
        [HVACMode.OFF, HVACMode.HEAT],
        current_temperature=19.5,
        target_temperature=20.0,
        target_temperature_step=0.5,
        hvac_action=HVACAction.HEATING,
        min_temp=5.0,
        max_temp=30.0,
    )


@pytest.fixture
def ac() -> FakeClimate:
    """Air conditioner serving the cool and dry modes."""
    return FakeClimate(
        AC,
        [HVACMode.OFF, HVACMode.COOL, HVACMode.DRY],
        features=ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
        | ClimateEntityFeature.SWING_HORIZONTAL_MODE,
        current_temperature=21.0,
        target_temperature=24.0,
        target_temperature_low=20.0,
        target_temperature_high=26.0,
        hvac_action=HVACAction.COOLING,
        fan_modes=["auto", "low", "high"],
        fan_mode="auto",
        swing_modes=["off", "on"],
        swing_mode="off",
        swing_horizontal_modes=["off", "left", "right"],
        swing_horizontal_mode="off",
        min_temp=16.0,
        max_temp=32.0,
    )


@pytest.fixture
async def sources(hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate) -> None:
    """Add the source climate entities to Home Assistant."""
    setup_test_component_platform(hass, CLIMATE_DOMAIN, [heater, ac])
    assert await async_setup_component(
        hass, CLIMATE_DOMAIN, {CLIMATE_DOMAIN: {"platform": "test"}}
    )
    await hass.async_block_till_done()


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Config entry using the heater for heat and the AC for cool and dry."""
    return MockConfigEntry(
        domain=DOMAIN,
        # Fixed so snapshots (unique_id, config_entry_id) are stable.
        entry_id="01JTESTENTRY000000000000000",
        title="Living room",
        data={
            CONF_NAME: "Living room",
            CONF_HEAT_ENTITY: HEATER,
            CONF_COOL_ENTITY: AC,
            CONF_DRY_ENTITY: AC,
        },
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, sources: None, mock_config_entry: MockConfigEntry
) -> MockConfigEntry:
    """Set up the integration with its sources."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
