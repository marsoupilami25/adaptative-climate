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

from custom_components.adaptative_climate.const import CONF_MAX_TEMP, DOMAIN

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
async def test_source_turned_on_elsewhere_gives_target(
    hass: HomeAssistant, ac: FakeClimate
) -> None:
    """A source turned on outside the integration gives its target to the entity."""
    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=20.0, target_temp_high=22.0
    )

    # The AC shows its own setpoint (24): the source takeover wins.
    await _on_source(hass, AC, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)

    assert _sent(ac) == []
    assert _target(hass) == 24.0
    assert _saved(hass, HIGH) == 24.0
    assert _saved(hass, LOW) == 20.0


@pytest.mark.usefixtures("init_integration")
async def test_source_turned_on_elsewhere_late_target_taken(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """A source turned on elsewhere that reports its target late gives it too."""
    await _on_source(hass, HEATER, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    await _set_on_device(hass, heater, 23.0)

    assert _sent(heater) == []
    assert _target(hass) == 23.0
    assert _saved(hass, LOW) == 23.0


@pytest.mark.usefixtures("init_integration")
async def test_turned_on_by_entity_sends_target(
    hass: HomeAssistant, ac: FakeClimate
) -> None:
    """A source the entity turns on gets the target of the entity."""
    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=20.0, target_temp_high=22.0
    )

    await _mode(hass, HVACMode.COOL)

    assert _sent(ac) == [22.0]
    assert _target(hass) == 22.0


async def test_mode_shown_late_still_gets_target(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    ac: FakeClimate,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A source showing the asked mode a few seconds later gets the target."""

    async def ignore(hvac_mode: HVACMode) -> None:
        # The device switches later (cloud).
        ac.calls.append(("set_hvac_mode", {ATTR_HVAC_MODE: hvac_mode}))

    real = ac.async_set_hvac_mode
    ac.async_set_hvac_mode = ignore
    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=20.0, target_temp_high=22.0
    )
    await _mode(hass, HVACMode.COOL)

    await _settle(hass, freezer, 5)
    await real(HVACMode.COOL)
    await hass.async_block_till_done()

    assert _sent(ac) == [22.0]
    assert _target(hass) == 22.0


async def test_mode_shown_too_late_counts_as_elsewhere(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    ac: FakeClimate,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A source showing the asked mode long after the request was turned on elsewhere."""

    async def ignore(hvac_mode: HVACMode) -> None:
        # The device takes the call but does not switch.
        ac.calls.append(("set_hvac_mode", {ATTR_HVAC_MODE: hvac_mode}))

    real = ac.async_set_hvac_mode
    ac.async_set_hvac_mode = ignore
    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=20.0, target_temp_high=22.0
    )
    await _mode(hass, HVACMode.COOL)

    await _settle(hass, freezer, 31)
    await real(HVACMode.COOL)
    await hass.async_block_till_done()

    assert _sent(ac) == []
    assert _target(hass) == 24.0


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
async def test_target_on_entity_step(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """The targets are on the step of the entity; each source gets its own step.

    The step of the entity is the largest one the steps of the sources are
    multiples of: the heater has 0.5, the AC 1, so 0.5. The entity shows
    its own target, not the one rounded for the source.
    """
    ac._attr_target_temperature_step = 1.0
    ac.async_write_ha_state()
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).attributes["target_temp_step"] == 0.5

    await _mode(hass, HVACMode.COOL)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=24.5)
    assert _sent(ac)[-1] == 25.0
    assert _target(hass) == 24.5
    assert _saved(hass, HIGH) == 24.5

    # A value off the step is rounded to it.
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=24.3)
    assert _saved(hass, HIGH) == 24.5
    assert _target(hass) == 24.5

    await _mode(hass, HVACMode.HEAT)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=21.3)
    assert _sent(heater)[-1] == 21.5
    assert _target(hass) == 21.5
    assert _saved(hass, LOW) == 21.5


@pytest.mark.usefixtures("init_integration")
async def test_entity_step_from_sources(hass: HomeAssistant, heater: FakeClimate) -> None:
    """A source without step counts as 0.5; 0.5 and 0.2 give 0.1."""
    # The heater has 0.5, the AC none (0.5).
    assert hass.states.get(ENTITY_ID).attributes["target_temp_step"] == 0.5
    heater._attr_target_temperature_step = 0.2
    heater.async_write_ha_state()
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).attributes["target_temp_step"] == 0.1


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
    hass: HomeAssistant,
    ac: FakeClimate,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A source refusing the target is tried again once, then logged; the mode still changes."""
    tries: list[dict[str, Any]] = []

    async def refuse(**kwargs: Any) -> None:
        tries.append(kwargs)
        raise HomeAssistantError("refused")

    ac.async_set_temperature = refuse
    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=20.0, target_temp_high=22.0
    )
    await _mode(hass, HVACMode.COOL)

    assert hass.states.get(ENTITY_ID).state == HVACMode.COOL
    assert len(tries) == 1
    assert "Could not set temperature 22.0 on climate.ac: refused" not in caplog.text
    assert "Could not set temperature 22.0 on climate.ac (refused), trying again" in caplog.text

    await _settle(hass, freezer, 5)
    assert len(tries) == 2
    assert "Could not set temperature 22.0 on climate.ac: refused" in caplog.text

    # Once only.
    await _settle(hass, freezer, 30)
    assert len(tries) == 2


@pytest.mark.usefixtures("init_integration")
async def test_source_script_error_does_not_fail(
    hass: HomeAssistant,
    ac: FakeClimate,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An error that is not a HomeAssistantError (a script schema error) is handled the same way."""
    tries: list[dict[str, Any]] = []

    async def invalid(**kwargs: Any) -> None:
        tries.append(kwargs)
        raise ValueError("expected float at 'value'")

    ac.async_set_temperature = invalid
    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=20.0, target_temp_high=22.0
    )
    await _mode(hass, HVACMode.COOL)

    assert hass.states.get(ENTITY_ID).state == HVACMode.COOL
    assert len(tries) == 1
    await _settle(hass, freezer, 5)
    assert len(tries) == 2
    assert (
        "Could not set temperature 22.0 on climate.ac: ValueError: expected float"
        in caplog.text
    )


@pytest.mark.usefixtures("init_integration")
async def test_send_tried_again_works(
    hass: HomeAssistant,
    heater: FakeClimate,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A send that fails once works on the retry, without a warning."""
    await _mode(hass, HVACMode.HEAT)
    await _settle(hass, freezer, 13)
    set_temperature = heater.async_set_temperature
    failures = [HomeAssistantError("busy")]

    async def flaky(**kwargs: Any) -> None:
        if failures:
            raise failures.pop()
        await set_temperature(**kwargs)

    heater.async_set_temperature = flaky
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=23.0)
    assert heater.target_temperature == 20.0

    await _settle(hass, freezer, 5)

    assert heater.target_temperature == 23.0
    assert not [
        r for r in caplog.records if r.levelname == "WARNING" and "Could not set" in r.message
    ]


@pytest.mark.usefixtures("init_integration")
async def test_send_retry_dropped_after_mode_change(
    hass: HomeAssistant,
    heater: FakeClimate,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The retry is not sent once the entity left the mode."""
    await _mode(hass, HVACMode.HEAT)
    await _settle(hass, freezer, 13)
    tries: list[dict[str, Any]] = []

    async def refuse(**kwargs: Any) -> None:
        tries.append(kwargs)
        raise HomeAssistantError("refused")

    heater.async_set_temperature = refuse
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=23.0)
    await _call(hass, SERVICE_TURN_OFF)

    await _settle(hass, freezer, 5)
    assert len(tries) == 1


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


async def test_fan_only_has_no_target(
    hass: HomeAssistant,
    sources: None,
    mock_config_entry: MockConfigEntry,
    ac: FakeClimate,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Fan only shows no target, sends none and takes none from its source.

    A target set in fan only is kept for the next mode.
    """
    ac._attr_hvac_modes = [*ac.hvac_modes, HVACMode.FAN_ONLY]
    ac.async_write_ha_state()
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, "fan_only_entity": AC}
    )
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    await _mode(hass, HVACMode.DRY)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=23.0)
    await _mode(hass, HVACMode.FAN_ONLY)
    ac.calls.clear()

    assert _target(hass) is None
    assert _range(hass) == (None, None)

    # Past the settle time, a target changed on the source is ignored.
    freezer.tick(timedelta(seconds=13))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    await _on_source(hass, AC, SERVICE_SET_TEMPERATURE, temperature=27.0)
    ac.calls.clear()
    assert _target(hass) is None

    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=21.0)
    assert ac.calls == []
    assert _target(hass) is None

    await _mode(hass, HVACMode.DRY)
    print('CALLS', ac.calls, hass.states.get(AC))
    assert _sent(ac) == [21.0]



@pytest.mark.usefixtures("init_integration")
async def test_dry_without_target(
    hass: HomeAssistant, ac: FakeClimate, freezer: FrozenDateTimeFactory
) -> None:
    """Dry on a source without target works like fan only.

    No target is shown, sent or taken; one set in dry is kept for the next
    mode. A source with a target gets it in dry, as in auto.
    """
    features = ac.supported_features
    ac._attr_supported_features = features & ~ClimateEntityFeature.TARGET_TEMPERATURE
    ac.async_write_ha_state()
    await hass.async_block_till_done()
    await _mode(hass, HVACMode.DRY)
    ac.calls.clear()

    assert _target(hass) is None
    assert _range(hass) == (None, None)

    # Past the settle time, a target changed on the source is ignored.
    freezer.tick(timedelta(seconds=13))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    setattr(ac, _attr_name("target_temperature"), 28.0)
    ac.async_write_ha_state()
    await hass.async_block_till_done()
    assert _target(hass) is None

    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=21.0)
    assert ac.calls == []
    assert _target(hass) is None
    assert _saved(hass) == 21.0

    # With a target, dry gets the single target.
    await _call(hass, SERVICE_TURN_OFF)
    ac._attr_supported_features = features
    ac.async_write_ha_state()
    await hass.async_block_till_done()
    await _mode(hass, HVACMode.DRY)
    assert _sent(ac) == [21.0]
    assert _target(hass) == 21.0


async def _setup_auto(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, ac: FakeClimate
) -> None:
    """Set up the entity with the AC also serving auto."""
    ac._attr_hvac_modes = [*ac.hvac_modes, HVACMode.AUTO]
    ac.async_write_ha_state()
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, "auto_entity": AC}
    )
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()


def _sent_range(source: FakeClimate) -> list[tuple[float, float]]:
    """Return the low/high targets sent to a source."""
    return [
        (data["target_temp_low"], data["target_temp_high"])
        for name, data in source.calls
        if name == "set_temperature" and "target_temp_low" in data
    ]


async def test_auto_with_range(
    hass: HomeAssistant,
    sources: None,
    mock_config_entry: MockConfigEntry,
    heater: FakeClimate,
    ac: FakeClimate,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Auto on a source with low/high works like heat_cool.

    Its low/high are the heating and cooling setpoints of heat and cool.
    """
    await _setup_auto(hass, mock_config_entry, ac)
    await _call(hass, SERVICE_SET_TEMPERATURE, target_temp_low=19.0, target_temp_high=25.0)

    await _mode(hass, HVACMode.AUTO)
    assert _sent_range(ac) == [(19.0, 25.0)]
    assert _target(hass) is None
    assert _range(hass) == (19.0, 25.0)

    # A change made on the source past the settle time is taken.
    freezer.tick(timedelta(seconds=13))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    await _on_source(
        hass, AC, SERVICE_SET_TEMPERATURE, target_temp_low=18.0, target_temp_high=25.0
    )
    assert _range(hass) == (18.0, 25.0)

    # The same low target in heat.
    await _mode(hass, HVACMode.HEAT)
    assert _sent(heater)[-1] == 18.0
    assert _target(hass) == 18.0

    # And the same high target in cool.
    await _mode(hass, HVACMode.COOL)
    assert _sent(ac)[-1] == 25.0


async def test_auto_with_single_target(
    hass: HomeAssistant,
    sources: None,
    mock_config_entry: MockConfigEntry,
    ac: FakeClimate,
) -> None:
    """Auto on a source with the single target only works like dry, same target."""
    ac._attr_supported_features = (
        ac.supported_features & ~ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    )
    await _setup_auto(hass, mock_config_entry, ac)

    await _mode(hass, HVACMode.DRY)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=23.0)
    await _mode(hass, HVACMode.AUTO)
    assert _target(hass) == 23.0
    assert _range(hass) == (None, None)
    assert _sent(ac)[-1] == 23.0
    assert _sent_range(ac) == []


async def test_auto_with_unused_range(
    hass: HomeAssistant,
    sources: None,
    mock_config_entry: MockConfigEntry,
    ac: FakeClimate,
) -> None:
    """A source with the low/high feature but no low/high value works with its single target.

    Like a template climate with set_temperature and no low/high templates:
    its card shows the single target.
    """
    ac._attr_target_temperature_low = None
    ac._attr_target_temperature_high = None
    await _setup_auto(hass, mock_config_entry, ac)

    await _mode(hass, HVACMode.DRY)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=23.0)
    await _mode(hass, HVACMode.AUTO)
    assert _target(hass) == 23.0
    assert _range(hass) == (None, None)
    assert _sent(ac)[-1] == 23.0
    assert _sent_range(ac) == []


async def test_auto_without_target(
    hass: HomeAssistant,
    sources: None,
    mock_config_entry: MockConfigEntry,
    ac: FakeClimate,
) -> None:
    """Auto on a source without target works like fan only."""
    ac._attr_supported_features = ClimateEntityFeature.FAN_MODE
    await _setup_auto(hass, mock_config_entry, ac)

    await _mode(hass, HVACMode.AUTO)
    ac.calls.clear()
    assert _target(hass) is None
    assert _range(hass) == (None, None)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=22.0)
    assert ac.calls == []


# Resync


async def _silent_once(hass: HomeAssistant, source: FakeClimate) -> list[dict[str, Any]]:
    """Make the next target call to a source get lost (taken, not shown)."""
    set_temperature = source.async_set_temperature
    lost: list[dict[str, Any]] = []

    async def lose(**kwargs: Any) -> None:
        if not lost:
            lost.append(kwargs)
            return
        await set_temperature(**kwargs)

    source.async_set_temperature = lose
    return lost


@pytest.mark.usefixtures("init_integration")
async def test_resync_sends_lost_target(
    hass: HomeAssistant, heater: FakeClimate, freezer: FrozenDateTimeFactory
) -> None:
    """A target the source does not show is sent again after 30 minutes."""
    await _mode(hass, HVACMode.HEAT)
    await _settle(hass, freezer, 13)
    lost = await _silent_once(hass, heater)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=23.0)
    assert [call[ATTR_TEMPERATURE] for call in lost] == [23.0]
    assert heater.target_temperature == 20.0

    await _settle(hass, freezer, 29 * 60)
    assert heater.target_temperature == 20.0
    await _settle(hass, freezer, 60)
    assert heater.target_temperature == 23.0

    # Then nothing more: the source shows it.
    heater.calls.clear()
    await _settle(hass, freezer, 30 * 60)
    assert _sent(heater) == []


@pytest.mark.usefixtures("init_integration")
async def test_resync_sends_nothing_when_shown(
    hass: HomeAssistant, heater: FakeClimate, freezer: FrozenDateTimeFactory
) -> None:
    """A source showing the targets, or one off, gets nothing."""
    await _mode(hass, HVACMode.HEAT)
    await _settle(hass, freezer, 13)
    heater.calls.clear()

    await _settle(hass, freezer, 30 * 60)
    assert _sent(heater) == []

    await _call(hass, SERVICE_TURN_OFF)
    await _set_on_device(hass, heater, 25.0)
    await _settle(hass, freezer, 30 * 60)
    assert _sent(heater) == []


@pytest.mark.usefixtures("sources")
async def test_resync_keeps_target_taken_outside_limits(
    hass: HomeAssistant,
    heater: FakeClimate,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A target set on the source above the limit is not sent back to the limit."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Living room",
        data={**mock_config_entry.data, CONF_MAX_TEMP: 25},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _mode(hass, HVACMode.HEAT)
    await _settle(hass, freezer, 13)

    await _set_on_device(hass, heater, 28.0)
    heater.calls.clear()
    await _settle(hass, freezer, 30 * 60)

    assert _sent(heater) == []
    assert heater.target_temperature == 28.0


# Active source unavailable for a while


async def _lose(hass: HomeAssistant, entity_id: str) -> None:
    """Make a source unavailable."""
    hass.states.async_set(entity_id, "unavailable")
    await hass.async_block_till_done()


async def _back(hass: HomeAssistant, source: FakeClimate, mode: HVACMode, target: float) -> None:
    """Bring a source back, in a mode, showing its own target."""
    source._attr_hvac_mode = mode
    setattr(source, _attr_name("target_temperature"), target)
    source.async_write_ha_state()
    await hass.async_block_till_done()


@pytest.mark.usefixtures("init_integration")
async def test_source_back_in_its_mode_gets_targets(
    hass: HomeAssistant, heater: FakeClimate, freezer: FrozenDateTimeFactory
) -> None:
    """The active source back from unavailable gets the target of the entity."""
    await _mode(hass, HVACMode.HEAT)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=22.0)
    await _settle(hass, freezer, 13)
    await _lose(hass, HEATER)
    assert hass.states.get(ENTITY_ID).state == HVACMode.OFF

    await _back(hass, heater, HVACMode.HEAT, 16.0)

    assert hass.states.get(ENTITY_ID).state == HVACMode.HEAT
    assert heater.target_temperature == 22.0
    assert _saved(hass, LOW) == 22.0


@pytest.mark.usefixtures("init_integration")
async def test_source_back_off_then_on_elsewhere_gives_target(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """Back off, it was changed meanwhile: turned on later, it gives its target."""
    await _mode(hass, HVACMode.HEAT)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=22.0)
    await _lose(hass, HEATER)

    await _back(hass, heater, HVACMode.OFF, 22.0)
    await _back(hass, heater, HVACMode.HEAT, 18.0)

    assert heater.target_temperature == 18.0
    assert _saved(hass, LOW) == 18.0


@pytest.mark.usefixtures("init_integration")
async def test_source_back_after_user_mode_change(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """A mode asked by the user meanwhile: the source back on is not the return."""
    await _mode(hass, HVACMode.HEAT)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=22.0)
    await _lose(hass, HEATER)
    await _call(hass, SERVICE_TURN_OFF)

    await _back(hass, heater, HVACMode.HEAT, 18.0)

    assert heater.target_temperature == 18.0
    assert _saved(hass, LOW) == 18.0


async def test_off_single_target_modes(
    hass: HomeAssistant,
    sources: None,
    mock_config_entry: MockConfigEntry,
    ac: FakeClimate,
) -> None:
    """Modes that all use a single target show a single target, even off.

    The AC has low/high targets, but cool and dry do not use them.
    """
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, data={"name": "Living room", "cool_entity": AC, "dry_entity": AC}
    )
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    features = ClimateEntityFeature(hass.states.get(ENTITY_ID).attributes[ATTR_SUPPORTED_FEATURES])
    assert ClimateEntityFeature.TARGET_TEMPERATURE_RANGE not in features
    assert hass.states.get(ENTITY_ID).state == HVACMode.OFF
    # Off: the target of the mode turn_on goes to (cool: the cooling setpoint).
    assert _target(hass) == 24.0
    assert "target_temp_low" not in hass.states.get(ENTITY_ID).attributes
