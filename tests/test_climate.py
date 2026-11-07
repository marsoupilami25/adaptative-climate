"""Tests for the Adaptative Climate entity."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.climate import (
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    ATTR_TEMPERATURE,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .conftest import AC, ENTITY_ID, HEATER, FakeClimate


async def _call(hass: HomeAssistant, service: str, **data: Any) -> None:
    """Call a climate service on the Adaptative Climate entity."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        service,
        {ATTR_ENTITY_ID: ENTITY_ID, **data},
        blocking=True,
    )
    await hass.async_block_till_done()


def _mode(hass: HomeAssistant, entity_id: str = ENTITY_ID) -> str:
    return hass.states.get(entity_id).state


async def test_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """The registry entry and state match the snapshot."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.usefixtures("init_integration")
async def test_initial_state(hass: HomeAssistant) -> None:
    """With every source off, the entity is off and lists the configured modes."""
    state = hass.states.get(ENTITY_ID)
    assert state.state == HVACMode.OFF
    assert state.attributes["hvac_modes"] == [
        HVACMode.OFF,
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.DRY,
    ]
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.OFF
    assert state.attributes["active_entity_id"] is None
    # Readings come from the first usable source when off.
    assert state.attributes["current_temperature"] == 19.5
    # Configured limits, narrowed by the source limits (heater: 5-30).
    assert state.attributes["min_temp"] == 7.0
    assert state.attributes["max_temp"] == 30.0


@pytest.mark.usefixtures("init_integration")
async def test_follows_source_changed_elsewhere(hass: HomeAssistant) -> None:
    """Turning a source on outside the integration updates the entity."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: AC, ATTR_HVAC_MODE: HVACMode.COOL},
        blocking=True,
    )
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == HVACMode.COOL
    assert state.attributes["active_entity_id"] == AC
    assert state.attributes[ATTR_TEMPERATURE] == 24.0
    assert state.attributes["current_temperature"] == 21.0
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.COOLING


@pytest.mark.usefixtures("init_integration")
async def test_switch_mode_turns_previous_source_off(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """Two sources never run at once."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    assert _mode(hass) == HVACMode.HEAT
    assert _mode(hass, HEATER) == HVACMode.HEAT

    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)
    assert _mode(hass) == HVACMode.COOL
    assert _mode(hass, HEATER) == HVACMode.OFF
    assert _mode(hass, AC) == HVACMode.COOL


@pytest.mark.usefixtures("init_integration")
async def test_source_turned_on_elsewhere_takes_over(hass: HomeAssistant) -> None:
    """Modes are exclusive: a source turned on elsewhere turns the others off."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: AC, ATTR_HVAC_MODE: HVACMode.COOL},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert _mode(hass) == HVACMode.COOL
    assert _mode(hass, HEATER) == HVACMode.OFF
    assert _mode(hass, AC) == HVACMode.COOL
    assert hass.states.get(ENTITY_ID).attributes["active_entity_id"] == AC


@pytest.mark.usefixtures("init_integration")
async def test_sources_turned_on_together_keep_the_last(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """When two sources turn on at once, the last one wins, not neither."""
    heater._attr_hvac_mode = HVACMode.HEAT
    heater.async_write_ha_state()
    ac._attr_hvac_mode = HVACMode.COOL
    ac.async_write_ha_state()
    await hass.async_block_till_done()

    assert _mode(hass) == HVACMode.COOL
    assert _mode(hass, HEATER) == HVACMode.OFF
    assert _mode(hass, AC) == HVACMode.COOL


@pytest.mark.usefixtures("init_integration")
async def test_shared_source_mode_change_elsewhere(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """A shared source changing mode elsewhere is followed and not turned off."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)
    ac.calls.clear()

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: AC, ATTR_HVAC_MODE: HVACMode.DRY},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert ac.calls == [("set_hvac_mode", {"hvac_mode": HVACMode.DRY})]
    assert heater.calls == []
    assert _mode(hass) == HVACMode.DRY


@pytest.mark.usefixtures("init_integration")
async def test_switch_mode_on_shared_source(
    hass: HomeAssistant, ac: FakeClimate
) -> None:
    """A source serving two modes is not turned off between them."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)
    ac.calls.clear()

    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.DRY)

    assert ac.calls == [("set_hvac_mode", {"hvac_mode": HVACMode.DRY})]
    assert _mode(hass) == HVACMode.DRY


@pytest.mark.usefixtures("init_integration")
async def test_set_temperature_forwards_to_active_source(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """Only temperature fields are sent, and only to the active source."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    heater.calls.clear()

    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=21.5)

    # The call targets the source, never this entity.
    assert heater.calls == [
        ("set_temperature", {ATTR_TEMPERATURE: 21.5, ATTR_ENTITY_ID: [HEATER]})
    ]
    assert ac.calls == []
    assert hass.states.get(ENTITY_ID).attributes[ATTR_TEMPERATURE] == 21.5


@pytest.mark.usefixtures("init_integration")
async def test_set_temperature_range(hass: HomeAssistant, ac: FakeClimate) -> None:
    """Low/high targets are forwarded as well."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)
    ac.calls.clear()

    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=20.0, target_temp_high=25.0
    )

    assert ac.calls == [
        (
            "set_temperature",
            {
                ATTR_TARGET_TEMP_LOW: 20.0,
                ATTR_TARGET_TEMP_HIGH: 25.0,
                ATTR_ENTITY_ID: [AC],
            },
        )
    ]


@pytest.mark.usefixtures("init_integration")
async def test_set_temperature_when_off(hass: HomeAssistant) -> None:
    """Setting a temperature while off is refused with a clear message."""
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, SERVICE_SET_TEMPERATURE, temperature=21.0)
    assert err.value.translation_key == "no_active_mode"


@pytest.mark.usefixtures("init_integration")
async def test_set_temperature_with_mode(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """A mode given with the temperature switches source first."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)

    await _call(
        hass, SERVICE_SET_TEMPERATURE, temperature=23.0, hvac_mode=HVACMode.COOL
    )

    assert _mode(hass, HEATER) == HVACMode.OFF
    assert ac.calls == [
        ("set_hvac_mode", {"hvac_mode": HVACMode.COOL}),
        ("set_temperature", {ATTR_TEMPERATURE: 23.0, ATTR_ENTITY_ID: [AC]}),
    ]
    assert hass.states.get(ENTITY_ID).attributes[ATTR_TEMPERATURE] == 23.0


@pytest.mark.usefixtures("init_integration")
async def test_set_temperature_with_mode_off(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """Mode off turns off and ignores the temperature."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    heater.calls.clear()

    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=23.0, hvac_mode=HVACMode.OFF)

    assert heater.calls == [("set_hvac_mode", {"hvac_mode": HVACMode.OFF})]
    assert _mode(hass) == HVACMode.OFF


@pytest.mark.usefixtures("init_integration")
async def test_set_temperature_with_unsupported_mode(hass: HomeAssistant) -> None:
    """A mode without a source is refused."""
    with pytest.raises(ServiceValidationError):
        await _call(
            hass, SERVICE_SET_TEMPERATURE, temperature=23.0, hvac_mode=HVACMode.AUTO
        )


@pytest.mark.usefixtures("init_integration")
async def test_turn_on_restores_last_mode(hass: HomeAssistant) -> None:
    """Turn on uses the last mode, turn off stops the active source."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)
    await _call(hass, SERVICE_TURN_OFF)
    assert _mode(hass) == HVACMode.OFF
    assert _mode(hass, AC) == HVACMode.OFF

    await _call(hass, SERVICE_TURN_ON)
    assert _mode(hass) == HVACMode.COOL


async def _setup_with_both_sources_on(
    hass: HomeAssistant,
    heater: FakeClimate,
    ac: FakeClimate,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Turn both sources on, then load the integration.

    Sources already running at startup are left alone, so both stay on.
    """
    for source, mode in ((heater, HVACMode.HEAT), (ac, HVACMode.COOL)):
        source._attr_hvac_mode = mode
        source.async_write_ha_state()
    await hass.async_block_till_done()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert _mode(hass, HEATER) == HVACMode.HEAT
    assert _mode(hass, AC) == HVACMode.COOL


@pytest.mark.usefixtures("sources")
async def test_turn_off_stops_every_running_source(
    hass: HomeAssistant,
    heater: FakeClimate,
    ac: FakeClimate,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Turn off stops all running sources, not only the active one."""
    await _setup_with_both_sources_on(hass, heater, ac, mock_config_entry)

    await _call(hass, SERVICE_TURN_OFF)

    assert _mode(hass) == HVACMode.OFF
    assert _mode(hass, HEATER) == HVACMode.OFF
    assert _mode(hass, AC) == HVACMode.OFF


@pytest.mark.usefixtures("sources")
async def test_switch_mode_stops_every_other_source(
    hass: HomeAssistant,
    heater: FakeClimate,
    ac: FakeClimate,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Switching mode stops all other running sources, not only the active one."""
    await _setup_with_both_sources_on(hass, heater, ac, mock_config_entry)

    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.DRY)

    assert _mode(hass) == HVACMode.DRY
    assert _mode(hass, HEATER) == HVACMode.OFF
    assert _mode(hass, AC) == HVACMode.DRY


@pytest.mark.usefixtures("init_integration")
async def test_turn_on_defaults_to_first_mode(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """Without a previous mode, turn on uses the first configured mode."""
    await _call(hass, SERVICE_TURN_ON)
    assert _mode(hass) == HVACMode.HEAT

    # Already on: nothing more is sent.
    heater.calls.clear()
    await _call(hass, SERVICE_TURN_ON)
    assert heater.calls == []


@pytest.mark.usefixtures("init_integration")
async def test_supported_features(hass: HomeAssistant) -> None:
    """Features combine the sources, without the ones not implemented."""
    features = hass.states.get(ENTITY_ID).attributes[ATTR_SUPPORTED_FEATURES]
    assert features == (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )


@pytest.mark.usefixtures("init_integration")
async def test_unavailable_when_no_source_usable(hass: HomeAssistant) -> None:
    """The entity is unavailable only when every source is."""
    hass.states.async_set(HEATER, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    assert _mode(hass) == HVACMode.OFF
    # The AC now provides the readings.
    assert hass.states.get(ENTITY_ID).attributes["current_temperature"] == 21.0

    hass.states.async_set(AC, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    assert _mode(hass) == STATE_UNAVAILABLE


@pytest.mark.usefixtures("init_integration")
async def test_unknown_hvac_action(hass: HomeAssistant) -> None:
    """An action the climate integration does not know is reported as None."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    hass.states.async_set(HEATER, HVACMode.HEAT, {ATTR_HVAC_ACTION: "boosting"})
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).attributes.get(ATTR_HVAC_ACTION) is None
