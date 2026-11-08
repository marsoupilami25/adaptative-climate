"""Tests for the fan and swing settings remembered per mode, and their sync."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
    setup_test_component_platform,
)

from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_SWING_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_SWING_MODE,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID, CONF_NAME
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component

from custom_components.adaptative_climate.const import (
    CONF_COOL_ENTITY,
    CONF_DRY_ENTITY,
    CONF_HEAT_ENTITY,
    CONF_SYNC_MODES,
    DOMAIN,
)

from .conftest import AC, ENTITY_ID, HEATER, FakeClimate

HEAT_PUMP = "climate.heat_pump"

AC_FEATURES = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.FAN_MODE
    | ClimateEntityFeature.SWING_MODE
)


def _heat_pump() -> FakeClimate:
    """Heat source with a fan: other case than the AC, and a Turbo speed."""
    return FakeClimate(
        HEAT_PUMP,
        [HVACMode.OFF, HVACMode.HEAT],
        features=AC_FEATURES,
        target_temperature=20.0,
        fan_modes=["Auto", "Low", "Medium", "High", "Turbo"],
        fan_mode="Auto",
        swing_modes=["Off", "On"],
        swing_mode="Off",
    )


def _ac() -> FakeClimate:
    """AC serving the cool and dry modes."""
    return FakeClimate(
        AC,
        [HVACMode.OFF, HVACMode.COOL, HVACMode.DRY],
        features=AC_FEATURES,
        target_temperature=24.0,
        fan_modes=["auto", "low", "medium", "high"],
        fan_mode="auto",
        swing_modes=["off", "on"],
        swing_mode="off",
    )


def _heater() -> FakeClimate:
    """Radiator: no fan, no swing."""
    return FakeClimate(HEATER, [HVACMode.OFF, HVACMode.HEAT], target_temperature=20.0)


async def _setup(
    hass: HomeAssistant,
    sources: list[FakeClimate],
    heat: str,
    sync: list[str] | None = None,
) -> MockConfigEntry:
    """Set up the sources and an entity: heat on `heat`, cool and dry on the AC."""
    setup_test_component_platform(hass, CLIMATE_DOMAIN, sources)
    assert await async_setup_component(
        hass, CLIMATE_DOMAIN, {CLIMATE_DOMAIN: {"platform": "test"}}
    )
    await hass.async_block_till_done()

    data: dict[str, Any] = {
        CONF_NAME: "Living room",
        CONF_HEAT_ENTITY: heat,
        CONF_COOL_ENTITY: AC,
        CONF_DRY_ENTITY: AC,
    }
    if sync is not None:
        data[CONF_SYNC_MODES] = sync
    entry = MockConfigEntry(domain=DOMAIN, title="Living room", data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _call(hass: HomeAssistant, service: str, **data: Any) -> None:
    """Call a climate service on the Adaptative Climate entity."""
    await hass.services.async_call(
        CLIMATE_DOMAIN, service, {ATTR_ENTITY_ID: ENTITY_ID, **data}, blocking=True
    )
    await hass.async_block_till_done()


async def _mode(hass: HomeAssistant, mode: HVACMode) -> None:
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=mode)


def _fan_calls(source: FakeClimate) -> list[str]:
    """Return the fan modes sent to a source."""
    return [data[ATTR_FAN_MODE] for name, data in source.calls if name == "set_fan_mode"]


def _memory(hass: HomeAssistant) -> dict[str, dict[str, str]]:
    """Return the settings the entity would save."""
    entity = hass.data[CLIMATE_DOMAIN].get_entity(ENTITY_ID)
    return entity.extra_restore_state_data.as_dict()["memory"]


async def _set_on_source(hass: HomeAssistant, source: FakeClimate, **attrs: Any) -> None:
    """Change settings on the source directly (remote control, app)."""
    for key, value in attrs.items():
        setattr(source, f"_attr_{key}", value)
    source.async_write_ha_state()
    await hass.async_block_till_done()


async def test_each_mode_keeps_its_settings(hass: HomeAssistant) -> None:
    """Without sync, cool and dry on the same AC keep their own fan speed."""
    ac = _ac()
    await _setup(hass, [_heat_pump(), ac], HEAT_PUMP)

    await _mode(hass, HVACMode.COOL)
    await _call(hass, SERVICE_SET_FAN_MODE, fan_mode="high")
    await _mode(hass, HVACMode.DRY)
    # First time in dry: the AC setting is kept as the dry setting.
    assert _memory(hass)["dry"][ATTR_FAN_MODE] == "high"
    await _call(hass, SERVICE_SET_FAN_MODE, fan_mode="low")
    ac.calls.clear()

    await _mode(hass, HVACMode.COOL)
    assert _fan_calls(ac) == ["high"]
    await _mode(hass, HVACMode.DRY)
    assert _fan_calls(ac) == ["high", "low"]
    assert hass.states.get(ENTITY_ID).attributes[ATTR_FAN_MODE] == "low"


async def test_change_on_source_is_remembered(hass: HomeAssistant) -> None:
    """A change made on the source itself is remembered too."""
    ac = _ac()
    pump = _heat_pump()
    await _setup(hass, [pump, ac], HEAT_PUMP)

    await _mode(hass, HVACMode.COOL)
    await _set_on_source(hass, ac, fan_mode="medium", swing_mode="on")
    await _mode(hass, HVACMode.HEAT)
    await _set_on_source(hass, ac, fan_mode="auto", swing_mode="off")
    ac.calls.clear()

    await _mode(hass, HVACMode.COOL)

    assert ac.calls[1:] == [
        ("set_fan_mode", {"fan_mode": "medium"}),
        ("set_swing_mode", {"swing_mode": "on"}),
    ]


async def test_entering_a_mode_does_not_overwrite_memory(hass: HomeAssistant) -> None:
    """The source settings found on entering a remembered mode are replaced."""
    ac = _ac()
    await _setup(hass, [_heat_pump(), ac], HEAT_PUMP)

    await _mode(hass, HVACMode.COOL)
    await _call(hass, SERVICE_SET_FAN_MODE, fan_mode="low")
    await _mode(hass, HVACMode.OFF)
    await _set_on_source(hass, ac, fan_mode="high")

    await _mode(hass, HVACMode.COOL)

    assert _memory(hass)["cool"][ATTR_FAN_MODE] == "low"
    assert hass.states.get(ENTITY_ID).attributes[ATTR_FAN_MODE] == "low"


async def test_value_already_set_is_not_sent(hass: HomeAssistant) -> None:
    """Nothing is sent when the source already has the value, whatever the case."""
    ac = _ac()
    await _setup(hass, [_heat_pump(), ac], HEAT_PUMP)
    await _mode(hass, HVACMode.COOL)
    await _call(hass, SERVICE_SET_FAN_MODE, fan_mode="low")
    await _mode(hass, HVACMode.OFF)
    await _set_on_source(hass, ac, fan_mode="LOW")
    ac.calls.clear()

    await _mode(hass, HVACMode.COOL)

    assert _fan_calls(ac) == []


async def test_sync_shares_settings_with_source_case(hass: HomeAssistant) -> None:
    """Synchronized modes share one value, sent as each source spells it."""
    ac = _ac()
    pump = _heat_pump()
    await _setup(hass, [pump, ac], HEAT_PUMP, sync=["heat", "cool"])

    await _mode(hass, HVACMode.COOL)
    await _call(hass, SERVICE_SET_FAN_MODE, fan_mode="high")
    await _mode(hass, HVACMode.HEAT)
    assert _fan_calls(pump) == ["High"]

    await _call(hass, SERVICE_SET_FAN_MODE, fan_mode="Medium")
    await _mode(hass, HVACMode.COOL)
    assert _fan_calls(ac) == ["high", "medium"]
    assert _memory(hass) == {
        "sync": {ATTR_FAN_MODE: "Medium", ATTR_SWING_MODE: "off"}
    }


async def test_sync_value_not_common_is_temporary(hass: HomeAssistant) -> None:
    """A value only one synchronized source offers is used, not remembered."""
    ac = _ac()
    pump = _heat_pump()
    await _setup(hass, [pump, ac], HEAT_PUMP, sync=["heat", "cool"])

    await _mode(hass, HVACMode.COOL)
    await _call(hass, SERVICE_SET_FAN_MODE, fan_mode="high")
    await _mode(hass, HVACMode.HEAT)
    # The heat pump offers every option, Turbo included.
    attributes = hass.states.get(ENTITY_ID).attributes
    assert attributes[ATTR_FAN_MODES] == ["Auto", "Low", "Medium", "High", "Turbo"]

    await _call(hass, SERVICE_SET_FAN_MODE, fan_mode="Turbo")
    assert hass.states.get(ENTITY_ID).attributes[ATTR_FAN_MODE] == "Turbo"
    assert _memory(hass)["sync"][ATTR_FAN_MODE] == "high"

    await _mode(hass, HVACMode.COOL)
    await _mode(hass, HVACMode.HEAT)
    assert _fan_calls(pump) == ["High", "Turbo", "High"]


async def test_sync_first_value_not_common(hass: HomeAssistant) -> None:
    """A first value that is not common leaves the shared memory empty."""
    ac = _ac()
    pump = _heat_pump()
    pump._attr_fan_mode = "Turbo"
    await _setup(hass, [pump, ac], HEAT_PUMP, sync=["heat", "cool"])

    await _mode(hass, HVACMode.HEAT)
    assert ATTR_FAN_MODE not in _memory(hass)["sync"]

    await _mode(hass, HVACMode.COOL)
    assert _fan_calls(ac) == []
    # The AC fan is common: it becomes the shared value.
    assert _memory(hass)["sync"][ATTR_FAN_MODE] == "auto"


async def test_unsynchronized_mode_keeps_its_own(hass: HomeAssistant) -> None:
    """A mode outside the sync keeps its own settings, Turbo included."""
    ac = _ac()
    pump = _heat_pump()
    await _setup(hass, [pump, ac], HEAT_PUMP, sync=["cool", "dry"])

    await _mode(hass, HVACMode.HEAT)
    await _call(hass, SERVICE_SET_FAN_MODE, fan_mode="Turbo")
    await _mode(hass, HVACMode.COOL)
    await _call(hass, SERVICE_SET_FAN_MODE, fan_mode="low")
    await _mode(hass, HVACMode.DRY)
    await _mode(hass, HVACMode.HEAT)

    assert _memory(hass)["heat"][ATTR_FAN_MODE] == "Turbo"
    assert _memory(hass)["sync"][ATTR_FAN_MODE] == "low"
    assert hass.states.get(ENTITY_ID).attributes[ATTR_FAN_MODE] == "Turbo"


async def test_sync_ignores_source_without_the_setting(hass: HomeAssistant) -> None:
    """A radiator without fan does not prevent syncing the fan of the others."""
    ac = _ac()
    await _setup(hass, [_heater(), ac], HEATER, sync=["heat", "cool", "dry"])

    await _mode(hass, HVACMode.COOL)
    await _call(hass, SERVICE_SET_FAN_MODE, fan_mode="high")
    await _mode(hass, HVACMode.HEAT)
    await _mode(hass, HVACMode.DRY)

    assert _memory(hass)["sync"][ATTR_FAN_MODE] == "high"
    assert [call for call in ac.calls if call[0] == "set_hvac_mode"][-1] == (
        "set_hvac_mode",
        {"hvac_mode": HVACMode.DRY},
    )


async def test_settings_restored_after_restart(hass: HomeAssistant) -> None:
    """The remembered settings survive a restart."""
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(ENTITY_ID, HVACMode.OFF),
                {"memory": {"cool": {ATTR_FAN_MODE: "medium", "bad": "x"}, "heat": 3}},
            ),
        ),
    )
    ac = _ac()
    await _setup(hass, [_heat_pump(), ac], HEAT_PUMP)

    await _mode(hass, HVACMode.COOL)

    assert _fan_calls(ac) == ["medium"]
    assert _memory(hass) == {"cool": {ATTR_FAN_MODE: "medium", ATTR_SWING_MODE: "off"}}


async def test_shared_value_no_longer_common_is_forgotten(hass: HomeAssistant) -> None:
    """After a config change, a shared value that is no longer common is dropped."""
    mock_restore_cache_with_extra_data(
        hass,
        ((State(ENTITY_ID, HVACMode.OFF), {"memory": {"sync": {ATTR_FAN_MODE: "Turbo"}}}),),
    )
    pump = _heat_pump()
    await _setup(hass, [pump, _ac()], HEAT_PUMP, sync=["heat", "cool"])

    await _mode(hass, HVACMode.HEAT)

    assert _fan_calls(pump) == []
    # Forgotten, then filled again with the current (common) value.
    assert _memory(hass)["sync"][ATTR_FAN_MODE] == "Auto"


async def test_memory_of_removed_modes_not_saved(hass: HomeAssistant) -> None:
    """Only the memories of the configured modes are saved."""
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(ENTITY_ID, HVACMode.OFF),
                {"memory": {"fan_only": {ATTR_FAN_MODE: "low"}, "sync": {ATTR_FAN_MODE: "low"}}},
            ),
        ),
    )
    await _setup(hass, [_heat_pump(), _ac()], HEAT_PUMP)

    assert _memory(hass) == {}


async def test_source_error_does_not_fail_mode_change(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """A source refusing a setting is logged; the mode change still happens."""
    ac = _ac()
    await _setup(hass, [_heat_pump(), ac], HEAT_PUMP)
    await _mode(hass, HVACMode.COOL)
    await _call(hass, SERVICE_SET_FAN_MODE, fan_mode="low")
    await _call(hass, SERVICE_SET_SWING_MODE, swing_mode="on")
    await _mode(hass, HVACMode.OFF)
    await _set_on_source(hass, ac, fan_mode="high", swing_mode="off")

    async def refuse(fan_mode: str) -> None:
        raise HomeAssistantError("refused")

    ac.async_set_fan_mode = refuse
    await _mode(hass, HVACMode.COOL)

    assert hass.states.get(ENTITY_ID).state == HVACMode.COOL
    assert "Could not restore fan_mode low on climate.ac: refused" in caplog.text
    # The other settings are still sent.
    assert hass.states.get(ENTITY_ID).attributes[ATTR_SWING_MODE] == "on"
