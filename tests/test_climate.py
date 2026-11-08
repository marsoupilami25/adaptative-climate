"""Tests for the Adaptative Climate entity."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    ATTR_SWING_HORIZONTAL_MODE,
    ATTR_SWING_HORIZONTAL_MODES,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_SWING_HORIZONTAL_MODE,
    SERVICE_SET_SWING_MODE,
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
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er, issue_registry as ir

from custom_components.adaptative_climate.const import DOMAIN

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
    sources: None,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The registry entry and state match the snapshot."""
    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.adaptative_climate.PLATFORMS", [Platform.CLIMATE]):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.usefixtures("init_integration")
async def test_initial_state(hass: HomeAssistant) -> None:
    """With every source off, the entity is off and lists the configured modes."""
    state = hass.states.get(ENTITY_ID)
    assert state.state == HVACMode.OFF
    # heat_cool uses the heat and cool sources.
    assert state.attributes["hvac_modes"] == [
        HVACMode.OFF,
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.HEAT_COOL,
        HVACMode.DRY,
    ]
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.OFF
    assert state.attributes["active_entity_id"] is None
    assert state.attributes["unavailable_modes"] == []
    # Readings come from the first usable source when off.
    assert state.attributes["current_temperature"] == 19.5
    # Off: the widest range of the sources (heater 5-30, AC 16-32).
    assert state.attributes["min_temp"] == 5.0
    assert state.attributes["max_temp"] == 32.0


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
    # The cooling setpoint of the entity is the one the AC already shows.
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

    # Dry has its own target, sent after the mode.
    assert [call for call in ac.calls if call[0] == "set_hvac_mode"] == [
        ("set_hvac_mode", {"hvac_mode": HVACMode.DRY})
    ]
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

    assert [call for call in ac.calls if call[0] == "set_hvac_mode"] == [
        ("set_hvac_mode", {"hvac_mode": HVACMode.DRY})
    ]
    assert _mode(hass) == HVACMode.DRY


@pytest.mark.usefixtures("init_integration")
async def test_source_in_foreign_mode_is_ignored(
    hass: HomeAssistant,
    heater: FakeClimate,
    ac: FakeClimate,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A source set elsewhere to a mode it does not serve here is ignored.

    The other sources keep running, the mode is shown in foreign_modes and
    logged.
    """
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    assert hass.states.get(ENTITY_ID).attributes["foreign_modes"] == {}
    heater.calls.clear()

    # The AC serves cool and dry, not fan only.
    ac._attr_hvac_mode = HVACMode.FAN_ONLY
    ac.async_write_ha_state()
    await hass.async_block_till_done()

    assert heater.calls == []
    assert _mode(hass, HEATER) == HVACMode.HEAT
    state = hass.states.get(ENTITY_ID)
    assert state.state == HVACMode.HEAT
    assert state.attributes["active_entity_id"] == HEATER
    assert state.attributes["foreign_modes"] == {AC: HVACMode.FAN_ONLY}
    assert "climate.ac runs in the fan_only mode" in caplog.text

    # Turning the entity off turns every running source off, that one too.
    await _call(hass, SERVICE_TURN_OFF)
    assert _mode(hass, HEATER) == HVACMode.OFF
    assert _mode(hass, AC) == HVACMode.OFF
    assert hass.states.get(ENTITY_ID).attributes["foreign_modes"] == {}


@pytest.mark.usefixtures("init_integration")
async def test_source_in_foreign_mode_alone_shows_off(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """The entity is off while its only running source is in a foreign mode."""
    heater._attr_hvac_mode = HVACMode.FAN_ONLY
    heater.async_write_ha_state()
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == HVACMode.OFF
    assert state.attributes["foreign_modes"] == {HEATER: HVACMode.FAN_ONLY}

    # Turning on runs the source in a mode it serves.
    await _call(hass, SERVICE_TURN_ON)
    assert _mode(hass) == HVACMode.HEAT
    assert _mode(hass, HEATER) == HVACMode.HEAT
    assert hass.states.get(ENTITY_ID).attributes["foreign_modes"] == {}


async def test_source_in_foreign_mode_at_startup(
    hass: HomeAssistant,
    sources: None,
    ac: FakeClimate,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A source already in a foreign mode at startup is logged and shown."""
    ac._attr_hvac_mode = HVACMode.FAN_ONLY
    ac.async_write_ha_state()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == HVACMode.OFF
    assert state.attributes["foreign_modes"] == {AC: HVACMode.FAN_ONLY}
    assert "climate.ac runs in the fan_only mode" in caplog.text


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
async def test_set_temperature_range_outside_heat_cool(
    hass: HomeAssistant, ac: FakeClimate
) -> None:
    """Cool gets the high target as its setpoint; the low target is only kept."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)
    ac.calls.clear()

    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=20.0, target_temp_high=25.0
    )

    assert ac.calls == [
        ("set_temperature", {ATTR_TEMPERATURE: 25.0, ATTR_ENTITY_ID: [AC]})
    ]
    attributes = hass.states.get(ENTITY_ID).attributes
    assert attributes[ATTR_TEMPERATURE] == 25.0
    assert attributes[ATTR_TARGET_TEMP_LOW] is None
    assert attributes[ATTR_TARGET_TEMP_HIGH] is None


@pytest.mark.usefixtures("init_integration")
async def test_set_temperature_range_when_off(hass: HomeAssistant) -> None:
    """Low/high targets while off are kept for heat_cool."""
    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=18.0, target_temp_high=25.0
    )

    entity = hass.data[CLIMATE_DOMAIN].get_entity(ENTITY_ID)
    saved = entity.extra_restore_state_data.as_dict()
    assert saved["target_temperature_low"] == 18.0
    assert saved["target_temperature_high"] == 25.0


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


BASE_FEATURES = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    | ClimateEntityFeature.TURN_ON
    | ClimateEntityFeature.TURN_OFF
)
FAN_SWING = (
    ClimateEntityFeature.FAN_MODE
    | ClimateEntityFeature.SWING_MODE
    | ClimateEntityFeature.SWING_HORIZONTAL_MODE
)


def _features(hass: HomeAssistant) -> int:
    return hass.states.get(ENTITY_ID).attributes[ATTR_SUPPORTED_FEATURES]


@pytest.mark.usefixtures("init_integration")
async def test_supported_features(hass: HomeAssistant) -> None:
    """When off, features combine the sources, without fan or swing.

    heat_cool (heat and cool sources) needs the low/high targets.
    """
    assert _features(hass) == BASE_FEATURES
    attributes = hass.states.get(ENTITY_ID).attributes
    assert ATTR_FAN_MODES not in attributes
    assert ATTR_SWING_MODES not in attributes
    assert ATTR_SWING_HORIZONTAL_MODES not in attributes


@pytest.mark.usefixtures("init_integration")
async def test_fan_swing_follow_active_source(hass: HomeAssistant) -> None:
    """Fan and swing are shown only when the active source has them."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    assert _features(hass) == BASE_FEATURES

    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)
    assert _features(hass) == BASE_FEATURES | FAN_SWING
    attributes = hass.states.get(ENTITY_ID).attributes
    assert attributes[ATTR_FAN_MODES] == ["auto", "low", "high"]
    assert attributes[ATTR_FAN_MODE] == "auto"
    assert attributes[ATTR_SWING_MODES] == ["off", "on"]
    assert attributes[ATTR_SWING_MODE] == "off"
    assert attributes[ATTR_SWING_HORIZONTAL_MODES] == ["off", "left", "right"]
    assert attributes[ATTR_SWING_HORIZONTAL_MODE] == "off"

    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    assert _features(hass) == BASE_FEATURES


@pytest.mark.usefixtures("init_integration")
async def test_fan_swing_in_heat_mode(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """A heat source with a fan (heat pump) shows it in heat mode too."""
    heater._attr_supported_features |= ClimateEntityFeature.FAN_MODE
    heater._attr_fan_modes = ["low", "high"]
    heater._attr_fan_mode = "low"

    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)

    assert _features(hass) == BASE_FEATURES | ClimateEntityFeature.FAN_MODE
    assert hass.states.get(ENTITY_ID).attributes[ATTR_FAN_MODES] == ["low", "high"]


@pytest.mark.usefixtures("init_integration")
async def test_fan_swing_hidden_without_options(
    hass: HomeAssistant, ac: FakeClimate
) -> None:
    """A source with the feature but no option to choose does not show it."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)

    ac._attr_fan_modes = []
    ac._attr_swing_modes = None
    ac._attr_swing_horizontal_modes = []
    ac.async_write_ha_state()
    await hass.async_block_till_done()

    assert _features(hass) == BASE_FEATURES


@pytest.mark.usefixtures("init_integration")
async def test_set_fan_and_swing_forward_to_active_source(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """Fan and swing changes go to the active source only."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)
    ac.calls.clear()

    await _call(hass, SERVICE_SET_FAN_MODE, fan_mode="high")
    await _call(hass, SERVICE_SET_SWING_MODE, swing_mode="on")
    await _call(
        hass, SERVICE_SET_SWING_HORIZONTAL_MODE, swing_horizontal_mode="left"
    )

    assert ac.calls == [
        ("set_fan_mode", {"fan_mode": "high"}),
        ("set_swing_mode", {"swing_mode": "on"}),
        ("set_swing_horizontal_mode", {"swing_horizontal_mode": "left"}),
    ]
    assert heater.calls == []
    attributes = hass.states.get(ENTITY_ID).attributes
    assert attributes[ATTR_FAN_MODE] == "high"
    assert attributes[ATTR_SWING_MODE] == "on"
    assert attributes[ATTR_SWING_HORIZONTAL_MODE] == "left"


@pytest.mark.usefixtures("init_integration")
async def test_set_fan_mode_when_off(hass: HomeAssistant) -> None:
    """Setting a fan mode while off is refused with a clear message."""
    entity = hass.data[CLIMATE_DOMAIN].get_entity(ENTITY_ID)
    with pytest.raises(ServiceValidationError) as err:
        await entity.async_set_fan_mode("auto")
    assert err.value.translation_key == "no_active_mode"


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
async def test_unavailable_source_mode_still_listed(hass: HomeAssistant) -> None:
    """A mode whose source is unavailable stays listed and is reported."""
    hass.states.async_set(AC, STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert HVACMode.COOL in state.attributes["hvac_modes"]
    # heat_cool needs the AC too.
    assert state.attributes["unavailable_modes"] == [
        HVACMode.COOL,
        HVACMode.HEAT_COOL,
        HVACMode.DRY,
    ]


@pytest.mark.usefixtures("init_integration")
async def test_switch_to_unavailable_source_refused(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """Choosing a mode whose source is unavailable is refused, and the
    running source is left on."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    hass.states.async_set(AC, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    heater.calls.clear()

    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)
    assert err.value.translation_key == "source_unavailable"
    assert err.value.translation_placeholders == {
        "hvac_mode": HVACMode.COOL,
        "entity_id": AC,
    }

    assert heater.calls == []
    assert _mode(hass) == HVACMode.HEAT
    assert _mode(hass, HEATER) == HVACMode.HEAT


@pytest.mark.usefixtures("init_integration")
async def test_unknown_hvac_action(hass: HomeAssistant) -> None:
    """An action the climate integration does not know is reported as None."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    hass.states.async_set(HEATER, HVACMode.HEAT, {ATTR_HVAC_ACTION: "boosting"})
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).attributes.get(ATTR_HVAC_ACTION) is None


def _range(hass: HomeAssistant) -> tuple[float, float]:
    """Return the min and max temperatures of the entity."""
    attributes = hass.states.get(ENTITY_ID).attributes
    return attributes["min_temp"], attributes["max_temp"]


@pytest.mark.usefixtures("init_integration")
async def test_range_follows_active_source(hass: HomeAssistant) -> None:
    """Without limits, the range is the one of the source of the current mode."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    assert _range(hass) == (5.0, 30.0)

    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)
    assert _range(hass) == (16.0, 32.0)

    # Off: the widest range of the sources.
    await _call(hass, SERVICE_TURN_OFF)
    assert _range(hass) == (5.0, 32.0)


@pytest.mark.usefixtures("init_integration")
async def test_range_without_source_limits(hass: HomeAssistant) -> None:
    """A source without min/max falls back to the Home Assistant defaults."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    hass.states.async_set(HEATER, HVACMode.HEAT, {})
    await hass.async_block_till_done()

    assert _range(hass) == (7.0, 35.0)


@pytest.mark.parametrize(
    ("limits", "heat_range", "cool_range"),
    [
        # Limits only narrow the range of the source.
        pytest.param(
            {"min_temp": 10.0, "max_temp": 28.0}, (10.0, 28.0), (16.0, 28.0), id="narrow"
        ),
        pytest.param({"max_temp": 23.0}, (5.0, 23.0), (16.0, 23.0), id="max_only"),
        # A limit outside the source range is ignored: min stays below max.
        pytest.param(
            {"min_temp": 31.0}, (5.0, 30.0), (31.0, 32.0), id="min_above_source_max"
        ),
        pytest.param(
            {"max_temp": 12.0}, (5.0, 12.0), (16.0, 32.0), id="max_below_source_min"
        ),
    ],
)
async def test_range_with_limits(
    hass: HomeAssistant,
    sources: None,
    mock_config_entry: MockConfigEntry,
    limits: dict[str, float],
    heat_range: tuple[float, float],
    cool_range: tuple[float, float],
) -> None:
    """Configured limits narrow the range of the active source."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, **limits}
    )
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    assert _range(hass) == heat_range

    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)
    assert _range(hass) == cool_range


def _set_ac_modes(hass: HomeAssistant, modes: list[HVACMode], state: str = HVACMode.OFF) -> None:
    """Show the AC as usable with the given HVAC modes."""
    hass.states.async_set(AC, state, {ATTR_HVAC_MODES: modes})


@pytest.mark.usefixtures("init_integration")
async def test_source_without_mode_raises_issue(
    hass: HomeAssistant, issue_registry: ir.IssueRegistry
) -> None:
    """A source that becomes usable without a mode it serves raises a Repairs
    issue, removed once it offers the mode again."""
    issue_id = "01JTESTENTRY000000000000000_dry_not_supported"
    # Unavailable (still starting): not judged.
    hass.states.async_set(AC, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None

    _set_ac_modes(hass, [HVACMode.OFF, HVACMode.COOL])
    await hass.async_block_till_done()

    issue = issue_registry.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_key == "mode_not_supported"
    assert issue.translation_placeholders == {
        "name": "Living room",
        "hvac_mode": HVACMode.DRY,
        "entity_id": AC,
    }
    state = hass.states.get(ENTITY_ID)
    # Still listed, but reported as not usable.
    assert HVACMode.DRY in state.attributes["hvac_modes"]
    assert state.attributes["unavailable_modes"] == [HVACMode.DRY]

    _set_ac_modes(hass, [HVACMode.OFF, HVACMode.COOL, HVACMode.DRY])
    await hass.async_block_till_done()
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None
    assert hass.states.get(ENTITY_ID).attributes["unavailable_modes"] == []


async def test_source_without_mode_at_startup(
    hass: HomeAssistant,
    sources: None,
    mock_config_entry: MockConfigEntry,
    ac: FakeClimate,
    issue_registry: ir.IssueRegistry,
) -> None:
    """A usable source missing a mode at startup raises the issue, which is
    removed when the entry unloads."""
    ac._attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL]
    ac.async_write_ha_state()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    issue_id = "01JTESTENTRY000000000000000_dry_not_supported"
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is not None

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None


@pytest.mark.usefixtures("init_integration")
async def test_switch_to_mode_source_lacks_refused(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """Choosing a mode its source does not offer is refused, and the running
    source is left on."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    _set_ac_modes(hass, [HVACMode.OFF, HVACMode.COOL])
    await hass.async_block_till_done()
    heater.calls.clear()

    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.DRY)
    assert err.value.translation_key == "source_mode_not_supported"
    assert err.value.translation_placeholders == {
        "hvac_mode": HVACMode.DRY,
        "entity_id": AC,
    }

    assert heater.calls == []
    assert _mode(hass) == HVACMode.HEAT
    assert _mode(hass, HEATER) == HVACMode.HEAT
