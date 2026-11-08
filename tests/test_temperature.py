"""Tests for the target temperature, kept by the entity and sent to the sources."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache_with_extra_data,
    setup_test_component_platform,
)

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_SUPPORTED_FEATURES, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component

from .conftest import AC, ENTITY_ID, HEATER, FakeClimate, _attr_name


async def _call(hass: HomeAssistant, service: str, **data: Any) -> None:
    """Call a climate service on the Adaptative Climate entity."""
    await hass.services.async_call(
        CLIMATE_DOMAIN, service, {ATTR_ENTITY_ID: ENTITY_ID, **data}, blocking=True
    )
    await hass.async_block_till_done()


async def _mode(hass: HomeAssistant, mode: HVACMode) -> None:
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=mode)


async def _on_source(hass: HomeAssistant, entity_id: str, service: str, **data: Any) -> None:
    """Call a service on a source directly (remote control, app)."""
    await hass.services.async_call(
        CLIMATE_DOMAIN, service, {ATTR_ENTITY_ID: entity_id, **data}, blocking=True
    )
    await hass.async_block_till_done()


def _target(hass: HomeAssistant, entity_id: str = ENTITY_ID) -> float | None:
    return hass.states.get(entity_id).attributes[ATTR_TEMPERATURE]


def _range(hass: HomeAssistant) -> tuple[float | None, float | None]:
    """Return the low and high targets shown (off: heating and cooling setpoints)."""
    attrs = hass.states.get(ENTITY_ID).attributes
    return attrs["target_temp_low"], attrs["target_temp_high"]


def _sent(source: FakeClimate) -> list[float]:
    """Return the temperatures sent to a source."""
    return [
        data[ATTR_TEMPERATURE]
        for name, data in source.calls
        if name == "set_temperature" and ATTR_TEMPERATURE in data
    ]


LOW = "target_temperature_low"
HIGH = "target_temperature_high"


def _saved(hass: HomeAssistant, name: str = "target_temperature") -> float | None:
    """Return a target the entity would save: heating (low), cooling (high), or the other."""
    entity = hass.data[CLIMATE_DOMAIN].get_entity(ENTITY_ID)
    return entity.extra_restore_state_data.as_dict()[name]


@pytest.mark.usefixtures("init_integration")
async def test_initial_target_from_sources(hass: HomeAssistant) -> None:
    """Without a saved target, the first one is taken from a source."""
    # Off: the heating and cooling setpoints, from the heater and the AC.
    assert _target(hass) is None
    assert _range(hass) == (20.0, 24.0)
    assert _saved(hass, LOW) == 20.0
    # The cooling setpoint is the one of the AC.
    assert _saved(hass, HIGH) == 24.0
    # The single target of the other modes comes from the first usable source.
    assert _saved(hass) == 20.0


@pytest.mark.usefixtures("init_integration")
async def test_modes_keep_their_own_target(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """Heat and cool each have a setpoint: switching mode does not carry it over."""
    await _mode(hass, HVACMode.HEAT)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=22.0)

    await _mode(hass, HVACMode.COOL)

    # The AC already shows its cooling setpoint (24): nothing is sent.
    assert _sent(ac) == []
    assert _target(hass) == 24.0
    assert _saved(hass, LOW) == 22.0
    assert _saved(hass, HIGH) == 24.0

    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=26.0)
    assert _sent(ac) == [26.0]

    await _mode(hass, HVACMode.HEAT)
    assert _target(hass) == 22.0
    assert _sent(heater) == [22.0]


@pytest.mark.usefixtures("init_integration")
async def test_source_turned_on_elsewhere_gets_target(
    hass: HomeAssistant, ac: FakeClimate
) -> None:
    """A source turned on outside the integration gets the target of the entity."""
    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=20.0, target_temp_high=22.0
    )

    await _on_source(hass, AC, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)

    assert _sent(ac) == [22.0]
    assert _target(hass) == 22.0


@pytest.mark.usefixtures("init_integration")
async def test_source_already_at_target_not_called(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """Nothing is sent to a source that already has the target."""
    await _mode(hass, HVACMode.HEAT)

    assert _sent(heater) == []


@pytest.mark.usefixtures("init_integration")
async def test_heating_setpoint_pushes_cooling_one(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """The heating setpoint stays 1 degree (default gap) below the cooling one."""
    await _mode(hass, HVACMode.HEAT)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=28.0)

    assert _sent(heater) == [28.0]
    assert _saved(hass, LOW) == 28.0
    assert _saved(hass, HIGH) == 29.0

    await _mode(hass, HVACMode.COOL)
    assert _sent(ac) == [29.0]
    assert _target(hass) == 29.0


@pytest.mark.usefixtures("init_integration")
async def test_cooling_setpoint_pulls_heating_one(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """The cooling setpoint stays 1 degree (default gap) above the heating one."""
    await _mode(hass, HVACMode.COOL)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=18.0)

    assert _sent(ac) == [18.0]
    assert _saved(hass, HIGH) == 18.0
    assert _saved(hass, LOW) == 17.0

    await _mode(hass, HVACMode.HEAT)
    assert _sent(heater) == [17.0]


async def test_target_kept_in_configured_limits(
    hass: HomeAssistant,
    sources: None,
    mock_config_entry: MockConfigEntry,
    ac: FakeClimate,
) -> None:
    """The configured limits apply to the temperature sent too."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, "max_temp": 23.0}
    )
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    await _mode(hass, HVACMode.COOL)

    # The AC showed 24, above the limit: it gets the limit.
    assert _sent(ac) == [23.0]
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=22.0)
    assert _sent(ac) == [23.0, 22.0]


@pytest.mark.usefixtures("init_integration")
async def test_target_rounded_to_source_step(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """A target is kept rounded to the step of its source."""
    await _mode(hass, HVACMode.COOL)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=21.3)
    # The AC has no step.
    assert _sent(ac)[-1] == 21.3

    # The heater has a 0.5 step.
    await _mode(hass, HVACMode.HEAT)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=21.3)
    assert _sent(heater) == [21.5]
    assert _target(hass) == 21.5
    assert _saved(hass, LOW) == 21.5


@pytest.mark.usefixtures("init_integration")
async def test_change_on_active_source_taken(
    hass: HomeAssistant, heater: FakeClimate, freezer: FrozenDateTimeFactory
) -> None:
    """A target changed on the active source becomes the target of the entity."""
    await _mode(hass, HVACMode.COOL)
    await _settle(hass, freezer, 13)
    await _on_source(hass, AC, SERVICE_SET_TEMPERATURE, temperature=25.0)

    assert _target(hass) == 25.0
    assert _saved(hass, HIGH) == 25.0

    # It is the cooling setpoint: heat keeps its own.
    await _mode(hass, HVACMode.HEAT)
    assert _sent(heater) == []
    assert _target(hass) == 20.0


@pytest.mark.usefixtures("init_integration")
async def test_change_on_source_while_off_ignored(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """While the entity is off, the targets of the sources are not taken."""
    await _on_source(hass, HEATER, SERVICE_SET_TEMPERATURE, temperature=26.0)

    assert _saved(hass) == 20.0
    await _mode(hass, HVACMode.HEAT)
    assert _sent(heater)[-1] == 20.0


@pytest.mark.usefixtures("init_integration")
async def test_set_temperature_when_off(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """A target set while off is kept and sent when the entity turns on."""
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=23.0)

    assert heater.calls == []
    assert _range(hass) == (23.0, 24.0)

    await _call(hass, SERVICE_TURN_ON)
    assert _sent(heater) == [23.0]


@pytest.mark.usefixtures("init_integration")
async def test_set_temperature_with_mode_off(hass: HomeAssistant) -> None:
    """With mode off, the target is kept for the next time."""
    await _mode(hass, HVACMode.HEAT)

    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=23.0, hvac_mode=HVACMode.OFF)

    assert hass.states.get(ENTITY_ID).state == HVACMode.OFF
    # Off, the target is the one of the mode turn_on goes to (heat).
    assert _saved(hass, LOW) == 23.0


@pytest.mark.usefixtures("init_integration")
async def test_set_temperature_with_current_mode(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """The current mode given with the temperature does not switch again."""
    await _mode(hass, HVACMode.HEAT)
    heater.calls.clear()

    await _call(
        hass, SERVICE_SET_TEMPERATURE, temperature=22.0, hvac_mode=HVACMode.HEAT
    )

    assert heater.calls == [
        ("set_temperature", {ATTR_TEMPERATURE: 22.0, ATTR_ENTITY_ID: [HEATER]})
    ]


@pytest.mark.usefixtures("init_integration")
async def test_source_without_target_keeps_it(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """A source without target (fan only) gets nothing; the next time it gets it."""
    await _mode(hass, HVACMode.COOL)
    attributes = dict(hass.states.get(AC).attributes)
    hass.states.async_set(
        AC,
        HVACMode.COOL,
        {**attributes, ATTR_SUPPORTED_FEATURES: ClimateEntityFeature.FAN_MODE},
    )
    await hass.async_block_till_done()
    ac.calls.clear()

    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=22.0)

    assert ac.calls == []
    assert _target(hass) == 22.0
    await _call(hass, SERVICE_TURN_OFF)
    hass.states.async_set(AC, HVACMode.OFF, attributes)
    await hass.async_block_till_done()
    await _mode(hass, HVACMode.COOL)
    assert _sent(ac) == [22.0]


@pytest.mark.usefixtures("init_integration")
async def test_target_sent_once_source_switched(
    hass: HomeAssistant, ac: FakeClimate
) -> None:
    """The target is sent only once the source shows the new mode."""

    async def slow_set_hvac_mode(hvac_mode: HVACMode) -> None:
        # The device answers later: the state does not change yet.
        ac.calls.append(("set_hvac_mode", {"hvac_mode": hvac_mode}))

    ac.async_set_hvac_mode = slow_set_hvac_mode
    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=20.0, target_temp_high=22.0
    )
    await _mode(hass, HVACMode.COOL)
    assert _sent(ac) == []

    # The device now reports cool, with a target of its own.
    ac._attr_hvac_mode = HVACMode.COOL
    ac.async_write_ha_state()
    await hass.async_block_till_done()

    assert _sent(ac) == [22.0]
    assert _saved(hass, HIGH) == 22.0


async def test_target_restored_after_restart(
    hass: HomeAssistant, sources: None, mock_config_entry: MockConfigEntry, heater: FakeClimate
) -> None:
    """The target survives a restart and is sent to the source turned on."""
    mock_restore_cache_with_extra_data(
        hass, ((State(ENTITY_ID, HVACMode.OFF), {"target_temperature_low": 18.5}),)
    )
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert _range(hass)[0] == 18.5
    await _mode(hass, HVACMode.HEAT)
    assert _sent(heater) == [18.5]


@pytest.mark.parametrize("saved", ["21", True, None])
async def test_bad_saved_target_ignored(
    hass: HomeAssistant, sources: None, mock_config_entry: MockConfigEntry, saved: Any
) -> None:
    """A saved target that is not a number is replaced by the one of a source."""
    mock_restore_cache_with_extra_data(
        hass, ((State(ENTITY_ID, HVACMode.OFF), {"target_temperature": saved}),)
    )
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert _saved(hass) == 20.0


@pytest.mark.usefixtures("init_integration")
async def test_source_error_does_not_fail_mode_change(
    hass: HomeAssistant, ac: FakeClimate, caplog: pytest.LogCaptureFixture
) -> None:
    """A source refusing the target is logged; the mode change still happens."""

    async def refuse(**kwargs: Any) -> None:
        raise HomeAssistantError("refused")

    ac.async_set_temperature = refuse
    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=20.0, target_temp_high=22.0
    )
    await _mode(hass, HVACMode.COOL)

    assert hass.states.get(ENTITY_ID).state == HVACMode.COOL
    assert "Could not set temperature 22.0 on climate.ac: refused" in caplog.text


@pytest.mark.usefixtures("init_integration")
async def test_turn_off_keeps_target(hass: HomeAssistant) -> None:
    """Turning off keeps the target shown."""
    await _mode(hass, HVACMode.COOL)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=25.0)

    await _call(hass, SERVICE_TURN_OFF)

    assert _range(hass)[1] == 25.0


async def test_initial_target_without_source_target(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """When no source has a target, the first one is the middle of the range."""
    sources = [
        FakeClimate(HEATER, [HVACMode.OFF, HVACMode.HEAT], min_temp=10.0, max_temp=30.0),
        FakeClimate(AC, [HVACMode.OFF, HVACMode.COOL, HVACMode.DRY], min_temp=16.0),
    ]
    setup_test_component_platform(hass, CLIMATE_DOMAIN, sources)
    assert await async_setup_component(
        hass, CLIMATE_DOMAIN, {CLIMATE_DOMAIN: {"platform": "test"}}
    )
    await hass.async_block_till_done()
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # The widest range, 10-35 (the AC has no max: default 35).
    assert _saved(hass) == 22.5
    # Heat and cool are 1 degree around it, for the heat/cool window.
    assert _saved(hass, LOW) == 21.5
    assert _saved(hass, HIGH) == 23.5
    assert _range(hass) == (21.5, 23.5)


async def _settle(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float) -> None:
    """Let time pass and run the timers due."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def _set_on_device(hass: HomeAssistant, source: FakeClimate, value: float) -> None:
    """Show a new target on a source, as the device reports it."""
    setattr(source, _attr_name("target_temperature"), value)
    source.async_write_ha_state()
    await hass.async_block_till_done()


@pytest.mark.usefixtures("init_integration")
async def test_late_source_target_ignored_then_replaced(
    hass: HomeAssistant, heater: FakeClimate, freezer: FrozenDateTimeFactory
) -> None:
    """A target shown late by a source entering its mode is ignored, then replaced."""
    # The heater is already at the target (20): nothing is sent, nothing confirms.
    await _mode(hass, HVACMode.HEAT)
    assert _sent(heater) == []

    # A few seconds later, the device reports its target for heat.
    await _settle(hass, freezer, 5)
    await _set_on_device(hass, heater, 26.0)
    assert _target(hass) == 20.0  # The entity shows its own target.
    assert _sent(heater) == []

    # At the end of the settle time, the target is sent again.
    await _settle(hass, freezer, 7)
    assert _sent(heater) == [20.0]
    assert _target(hass, HEATER) == 20.0
    assert _saved(hass, LOW) == 20.0

    # From now on, the source is followed.
    await _set_on_device(hass, heater, 24.0)
    assert _target(hass) == 24.0
    assert _saved(hass, LOW) == 24.0


@pytest.mark.usefixtures("init_integration")
async def test_every_target_ignored_during_settle(
    hass: HomeAssistant, heater: FakeClimate, freezer: FrozenDateTimeFactory
) -> None:
    """Until the settle time ends, even a change made on the source is ignored."""
    await _mode(hass, HVACMode.HEAT)
    await _on_source(hass, HEATER, SERVICE_SET_TEMPERATURE, temperature=25.0)
    await _on_source(hass, HEATER, SERVICE_SET_TEMPERATURE, temperature=20.0)
    # Back to the target: not a confirmation, nothing was sent.
    await _on_source(hass, HEATER, SERVICE_SET_TEMPERATURE, temperature=23.0)
    assert _target(hass) == 20.0

    await _settle(hass, freezer, 12)
    assert _target(hass, HEATER) == 20.0
    assert _saved(hass, LOW) == 20.0


@pytest.mark.usefixtures("init_integration")
async def test_confirmed_target_ends_settle(
    hass: HomeAssistant, ac: FakeClimate, freezer: FrozenDateTimeFactory
) -> None:
    """A source showing the target sent to it is followed right away."""
    # The AC was at 24: it gets 22 and shows it, which confirms the mode.
    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=20.0, target_temp_high=22.0
    )
    await _mode(hass, HVACMode.COOL)
    assert _sent(ac) == [22.0]

    await _settle(hass, freezer, 2)
    await _on_source(hass, AC, SERVICE_SET_TEMPERATURE, temperature=25.0)

    assert _target(hass) == 25.0
    assert _saved(hass, HIGH) == 25.0
    # No settle timer is left to send the old target back.
    await _settle(hass, freezer, 12)
    assert _target(hass, AC) == 25.0


@pytest.mark.usefixtures("init_integration")
async def test_nothing_resent_when_source_silent(
    hass: HomeAssistant, ac: FakeClimate, freezer: FrozenDateTimeFactory
) -> None:
    """A source that shows no other target during the settle time gets nothing more."""

    async def ignore(**kwargs: Any) -> None:
        # The device takes the call but reports nothing back.
        ac.calls.append(("set_temperature", kwargs))

    ac.async_set_temperature = ignore
    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=20.0, target_temp_high=22.0
    )
    await _mode(hass, HVACMode.COOL)
    assert _sent(ac) == [22.0]

    await _settle(hass, freezer, 12)

    assert _sent(ac) == [22.0]
    # The settle time is over: the source is followed again.
    await _set_on_device(hass, ac, 26.0)
    assert _saved(hass, HIGH) == 26.0


@pytest.mark.usefixtures("init_integration")
async def test_settle_stopped_when_turned_off(
    hass: HomeAssistant, heater: FakeClimate, freezer: FrozenDateTimeFactory
) -> None:
    """Turning off during the settle time sends nothing at its end."""
    await _mode(hass, HVACMode.HEAT)
    await _call(hass, SERVICE_TURN_OFF)
    await _on_source(hass, HEATER, SERVICE_SET_TEMPERATURE, temperature=26.0)

    await _settle(hass, freezer, 12)

    assert _sent(heater) == [26.0]  # Only the call made on the source itself.


async def test_change_on_source_outside_limits(
    hass: HomeAssistant,
    sources: None,
    mock_config_entry: MockConfigEntry,
    ac: FakeClimate,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A target set on the source above the limit wins: the user took over there."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, "max_temp": 23.0}
    )
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    await _mode(hass, HVACMode.COOL)
    freezer.tick(timedelta(seconds=13))
    ac.calls.clear()

    await _on_source(hass, AC, SERVICE_SET_TEMPERATURE, temperature=28.0)

    assert _sent(ac) == [28.0]  # Only the call made on the source itself.
    assert _target(hass, AC) == 28.0
    assert _target(hass) == 28.0
    assert _saved(hass, HIGH) == 28.0
