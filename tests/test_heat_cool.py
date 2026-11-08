"""Tests for the heat_cool mode: with its own source, or with the heat and cool sources."""

from __future__ import annotations

import asyncio
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
    ATTR_FAN_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    ATTR_TEMPERATURE,
    CONF_NAME,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.setup import async_setup_component

from custom_components.adaptative_climate.const import (
    CONF_COOL_ENTITY,
    CONF_HEAT_COOL_ENTITY,
    CONF_HEAT_ENTITY,
    CONF_MIN_GAP,
    CONF_MIN_PHASE_DURATION,
    CONF_TEMPERATURE_SENSOR,
    DOMAIN,
)

from .conftest import AC, ENTITY_ID, HEATER, FakeClimate, _attr_name

HEAT_PUMP = "climate.heat_pump"
SENSOR = "sensor.room"


async def _call(hass: HomeAssistant, service: str, **data: Any) -> None:
    """Call a climate service on the Adaptative Climate entity."""
    await hass.services.async_call(
        CLIMATE_DOMAIN, service, {ATTR_ENTITY_ID: ENTITY_ID, **data}, blocking=True
    )
    await hass.async_block_till_done()


async def _on_source(hass: HomeAssistant, entity_id: str, service: str, **data: Any) -> None:
    """Call a service on a source directly (remote control, app)."""
    await hass.services.async_call(
        CLIMATE_DOMAIN, service, {ATTR_ENTITY_ID: entity_id, **data}, blocking=True
    )
    await hass.async_block_till_done()


async def _wait(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float) -> None:
    """Let time pass and run the timers due."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def _set_room(hass: HomeAssistant, value: str, unit: str = "°C") -> None:
    """Show a room temperature on the sensor."""
    hass.states.async_set(
        SENSOR, value, {"unit_of_measurement": unit, "device_class": "temperature"}
    )
    await hass.async_block_till_done()


def _attrs(hass: HomeAssistant) -> dict[str, Any]:
    return hass.states.get(ENTITY_ID).attributes


def _state(hass: HomeAssistant, entity_id: str = ENTITY_ID) -> str:
    return hass.states.get(entity_id).state


def _sent(source: FakeClimate) -> list[dict[str, Any]]:
    """Return the targets sent to a source."""
    return [
        {key: value for key, value in data.items() if key != ATTR_ENTITY_ID}
        for name, data in source.calls
        if name == "set_temperature"
    ]


def _saved(hass: HomeAssistant) -> dict[str, Any]:
    """Return what the entity would save."""
    entity = hass.data[CLIMATE_DOMAIN].get_entity(ENTITY_ID)
    return entity.extra_restore_state_data.as_dict()


# Combined heat_cool: the heater and the AC, with a room sensor.


@pytest.fixture
def combined_entry() -> MockConfigEntry:
    """Heat and cool sources, no heat_cool source, a room sensor.

    The phase switches at once (no minimum phase duration): see the tests
    of the minimum phase duration for the default.
    """
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id="01JTESTENTRY000000000000000",
        title="Living room",
        data={
            CONF_NAME: "Living room",
            CONF_HEAT_ENTITY: HEATER,
            CONF_COOL_ENTITY: AC,
            CONF_TEMPERATURE_SENSOR: SENSOR,
            CONF_MIN_PHASE_DURATION: 0,
        },
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture
async def combined(
    hass: HomeAssistant, sources: None, combined_entry: MockConfigEntry
) -> None:
    """Set up the combined heat_cool, room at 18 °C, targets 19-25 °C."""
    await _set_room(hass, "18")
    await _setup(hass, combined_entry)
    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=19.0, target_temp_high=25.0
    )


@pytest.mark.usefixtures("combined")
async def test_combined_listed(hass: HomeAssistant) -> None:
    """heat_cool is offered with the low/high targets, shown by the sensor."""
    attrs = _attrs(hass)
    assert attrs["hvac_modes"] == [
        HVACMode.OFF,
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.HEAT_COOL,
    ]
    assert ClimateEntityFeature.TARGET_TEMPERATURE_RANGE in ClimateEntityFeature(
        attrs[ATTR_SUPPORTED_FEATURES]
    )
    assert attrs["current_temperature"] == 18.0


async def test_combined_initial_targets(
    hass: HomeAssistant, sources: None, combined_entry: MockConfigEntry
) -> None:
    """The first low/high targets are the setpoints of the heater and the AC."""
    await _setup(hass, combined_entry)

    saved = _saved(hass)
    assert saved["target_temperature_low"] == 20.0
    assert saved["target_temperature_high"] == 24.0


@pytest.mark.usefixtures("combined")
async def test_combined_below_low_heats(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """Below the low target, the heater heats to the low target."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)

    assert _state(hass) == HVACMode.HEAT_COOL
    assert _state(hass, HEATER) == HVACMode.HEAT
    assert _state(hass, AC) == HVACMode.OFF
    assert _sent(heater) == [{ATTR_TEMPERATURE: 19.0}]
    attrs = _attrs(hass)
    assert attrs["active_entity_id"] == HEATER
    assert attrs[ATTR_TEMPERATURE] is None
    assert attrs[ATTR_TARGET_TEMP_LOW] == 19.0
    assert attrs[ATTR_TARGET_TEMP_HIGH] == 25.0


@pytest.mark.usefixtures("combined")
async def test_combined_above_high_cools(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """Above the high target, the AC cools to the high target."""
    await _set_room(hass, "27")
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)

    assert _state(hass) == HVACMode.HEAT_COOL
    assert _state(hass, HEATER) == HVACMode.OFF
    assert _state(hass, AC) == HVACMode.COOL
    assert _sent(ac) == [{ATTR_TEMPERATURE: 25.0}]
    assert _attrs(hass)["active_entity_id"] == AC


@pytest.mark.parametrize(("room", "source"), [("20", HEATER), ("24", AC)])
@pytest.mark.usefixtures("combined")
async def test_combined_between_targets_closest(
    hass: HomeAssistant, room: str, source: str
) -> None:
    """Between the targets, the source of the closest target starts."""
    await _set_room(hass, room)
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)

    assert _attrs(hass)["active_entity_id"] == source


@pytest.mark.usefixtures("combined")
async def test_combined_switches_with_room_temperature(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """Crossing a target switches source; in between, the source is kept."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)

    await _set_room(hass, "22")
    assert _attrs(hass)["active_entity_id"] == HEATER

    await _set_room(hass, "26")
    assert _state(hass) == HVACMode.HEAT_COOL
    assert _state(hass, HEATER) == HVACMode.OFF
    assert _state(hass, AC) == HVACMode.COOL
    assert _sent(ac) == [{ATTR_TEMPERATURE: 25.0}]
    assert _attrs(hass)["active_entity_id"] == AC

    await _set_room(hass, "22")
    assert _attrs(hass)["active_entity_id"] == AC

    await _set_room(hass, "18.5")
    assert _state(hass) == HVACMode.HEAT_COOL
    assert _state(hass, HEATER) == HVACMode.HEAT
    assert _state(hass, AC) == HVACMode.OFF


async def test_combined_shared_source(
    hass: HomeAssistant, sources: None, ac: FakeClimate
) -> None:
    """One heat pump serving heat and cool switches its own mode."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bedroom",
        data={
            CONF_NAME: "Bedroom",
            CONF_HEAT_ENTITY: AC,
            CONF_COOL_ENTITY: AC,
            CONF_TEMPERATURE_SENSOR: SENSOR,
            CONF_MIN_PHASE_DURATION: 0,
        },
    )
    # The fixture AC has no heat mode: give it one.
    ac._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]
    ac.async_write_ha_state()
    await _set_room(hass, "18")
    await _setup(hass, entry)
    bedroom = "climate.bedroom"

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: bedroom, "hvac_mode": HVACMode.HEAT_COOL},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert _state(hass, bedroom) == HVACMode.HEAT_COOL
    assert _state(hass, AC) == HVACMode.HEAT

    await _set_room(hass, "30")
    assert _state(hass, bedroom) == HVACMode.HEAT_COOL
    assert _state(hass, AC) == HVACMode.COOL


@pytest.mark.usefixtures("combined")
async def test_combined_new_targets_switch_phase(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """New targets go to the running source, and may switch it."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)

    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=18.5, target_temp_high=25.0
    )
    assert _sent(heater)[-1] == {ATTR_TEMPERATURE: 18.5}

    # The room (18) is now above the high target.
    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=16.0, target_temp_high=17.0
    )
    assert _state(hass) == HVACMode.HEAT_COOL
    assert _state(hass, HEATER) == HVACMode.OFF
    assert _state(hass, AC) == HVACMode.COOL
    assert _sent(ac) == [{ATTR_TEMPERATURE: 17.0}]


@pytest.mark.usefixtures("combined")
async def test_combined_target_out_of_source_range_sent_again(
    hass: HomeAssistant, ac: FakeClimate
) -> None:
    """A target the source cannot take sends the state each time it is set.

    The state does not change (the source shows its minimum), but the
    frontend must get it again to drop the value it shows.
    """
    await _set_room(hass, "30")
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    states: list[State] = []
    hass.bus.async_listen(
        "state_changed",
        lambda event: event.data["entity_id"] == ENTITY_ID
        and states.append(event.data["new_state"]),
    )

    for _ in range(2):
        states.clear()
        await _call(
            hass, SERVICE_SET_TEMPERATURE, target_temp_low=10.0, target_temp_high=14.0
        )
        assert states
        assert states[-1].attributes[ATTR_TARGET_TEMP_HIGH] == 16.0
    assert _saved(hass)["target_temperature_high"] == 16.0


@pytest.mark.usefixtures("combined")
async def test_combined_targets_kept_as_sources_get_them(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """Each low/high target goes to one source: it is kept as that source gets it.

    The phase then switches where the source works: the AC cannot go below
    16, so a high target of 14 is 16, and 15 does not switch to cool.
    """
    await _set_room(hass, "5")
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    # The heater has a 0.5 step, the AC a 16 minimum.
    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=10.2, target_temp_high=14.0
    )

    assert _saved(hass)["target_temperature_low"] == 10.0
    assert _saved(hass)["target_temperature_high"] == 16.0
    await _set_room(hass, "15")
    assert _attrs(hass)["active_entity_id"] == HEATER
    await _set_room(hass, "17")
    assert _attrs(hass)["active_entity_id"] == AC


@pytest.mark.usefixtures("combined")
async def test_combined_single_target_is_a_setpoint(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """The single target of heat is the low target, the one of cool the high one."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    assert _sent(heater) == [{ATTR_TEMPERATURE: 19.0}]

    # Heat shows the low target as its single target.
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    attrs = _attrs(hass)
    assert attrs[ATTR_TEMPERATURE] == 19.0
    assert attrs[ATTR_TARGET_TEMP_LOW] is None
    assert attrs[ATTR_TARGET_TEMP_HIGH] is None

    # Setting it in heat sets the low target of heat_cool.
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=22.0)
    assert _sent(heater)[-1] == {ATTR_TEMPERATURE: 22.0}
    assert _saved(hass)["target_temperature_low"] == 22.0
    assert _saved(hass)["target_temperature_high"] == 25.0

    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    attrs = _attrs(hass)
    assert attrs[ATTR_TEMPERATURE] is None
    assert attrs[ATTR_TARGET_TEMP_LOW] == 22.0
    assert attrs[ATTR_TARGET_TEMP_HIGH] == 25.0


@pytest.mark.usefixtures("combined")
async def test_combined_cool_single_target_is_the_high_target(
    hass: HomeAssistant, ac: FakeClimate
) -> None:
    """Cool shows the high target as its single target and sets it."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)
    assert _attrs(hass)[ATTR_TEMPERATURE] == 25.0

    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=26.0)

    assert _sent(ac)[-1] == {ATTR_TEMPERATURE: 26.0}
    assert _saved(hass)["target_temperature_high"] == 26.0
    assert _saved(hass)["target_temperature_low"] == 19.0
    # The single target of the other modes is apart.
    assert _saved(hass)["target_temperature"] == 20.0


@pytest.mark.usefixtures("combined")
async def test_combined_off_shows_targets_of_next_mode(hass: HomeAssistant) -> None:
    """While off, both setpoints are shown; a single target is the next mode's."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)
    await _call(hass, SERVICE_TURN_OFF)
    attrs = _attrs(hass)
    assert attrs[ATTR_TEMPERATURE] is None
    assert (attrs[ATTR_TARGET_TEMP_LOW], attrs[ATTR_TARGET_TEMP_HIGH]) == (19.0, 25.0)

    # Off, the single target is the one of the mode turn_on goes to (cool).
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=23.0)
    assert _saved(hass)["target_temperature_high"] == 23.0

    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    await _call(hass, SERVICE_TURN_OFF)
    attrs = _attrs(hass)
    assert attrs[ATTR_TEMPERATURE] is None
    assert attrs[ATTR_TARGET_TEMP_LOW] == 19.0
    assert attrs[ATTR_TARGET_TEMP_HIGH] == 23.0


@pytest.mark.usefixtures("combined")
async def test_combined_source_turned_off_elsewhere(hass: HomeAssistant) -> None:
    """The source has the upper hand: turned off elsewhere, heat_cool ends."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)

    await _on_source(hass, HEATER, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.OFF)

    assert _state(hass) == HVACMode.OFF
    # Back to heat_cool only when asked: the room crossing a target does nothing.
    await _set_room(hass, "30")
    assert _state(hass, AC) == HVACMode.OFF


@pytest.mark.usefixtures("combined")
async def test_combined_other_mode_set_elsewhere(hass: HomeAssistant) -> None:
    """A source turned on elsewhere ends heat_cool: the entity follows it."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)

    await _on_source(hass, AC, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)

    assert _state(hass) == HVACMode.COOL
    assert _state(hass, HEATER) == HVACMode.OFF
    # The room below the low target does not switch back to heat.
    await _set_room(hass, "15")
    assert _state(hass, AC) == HVACMode.COOL


@pytest.mark.usefixtures("combined")
async def test_combined_takeover_on_source(
    hass: HomeAssistant, heater: FakeClimate, freezer: FrozenDateTimeFactory
) -> None:
    """A target changed on the running source becomes the low or high target."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    await _wait(hass, freezer, 13)

    setattr(heater, _attr_name("target_temperature"), 21.0)
    heater.async_write_ha_state()
    await hass.async_block_till_done()

    assert _attrs(hass)[ATTR_TARGET_TEMP_LOW] == 21.0
    assert _saved(hass)["target_temperature_low"] == 21.0
    assert _saved(hass)["target_temperature_high"] == 25.0


@pytest.mark.usefixtures("combined")
async def test_combined_inverted_targets_keep_phase(hass: HomeAssistant) -> None:
    """Low above high (a source took over): between them, the phase is kept."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    entity = hass.data[CLIMATE_DOMAIN].get_entity(ENTITY_ID)
    entity._target_store[ATTR_TARGET_TEMP_LOW] = 25.0
    entity._target_store[ATTR_TARGET_TEMP_HIGH] = 23.0

    await _set_room(hass, "24")
    assert _attrs(hass)["active_entity_id"] == HEATER

    await _set_room(hass, "26")
    assert _attrs(hass)["active_entity_id"] == AC

    await _set_room(hass, "24")
    assert _attrs(hass)["active_entity_id"] == AC


@pytest.mark.usefixtures("combined")
async def test_combined_set_again_keeps_phase(hass: HomeAssistant) -> None:
    """Asking heat_cool again keeps the phase between the targets."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    await _set_room(hass, "26")
    await _set_room(hass, "21")
    assert _attrs(hass)["active_entity_id"] == AC

    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    assert _attrs(hass)["active_entity_id"] == AC
    assert _state(hass, HEATER) == HVACMode.OFF


@pytest.mark.usefixtures("combined")
async def test_combined_mode_asked_during_phase_switch(
    hass: HomeAssistant, ac: FakeClimate
) -> None:
    """A mode asked while the phase switches waits for it, then wins."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)

    release = asyncio.Event()
    set_mode = ac.async_set_hvac_mode

    async def slow(hvac_mode: HVACMode) -> None:
        await release.wait()
        await set_mode(hvac_mode)

    ac.async_set_hvac_mode = slow
    # The room asks for cool: the switch waits on the AC.
    hass.states.async_set(
        SENSOR, "30", {"unit_of_measurement": "°C", "device_class": "temperature"}
    )
    for _ in range(20):
        await asyncio.sleep(0)
    asked = hass.async_create_task(
        hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_HVAC_MODE,
            {ATTR_ENTITY_ID: ENTITY_ID, "hvac_mode": HVACMode.HEAT},
            blocking=True,
        )
    )
    for _ in range(20):
        await asyncio.sleep(0)
    release.set()
    await asked
    await hass.async_block_till_done()

    assert _state(hass) == HVACMode.HEAT
    assert _state(hass, HEATER) == HVACMode.HEAT
    assert _state(hass, AC) == HVACMode.OFF


async def test_combined_restored_targets_keep_gap(
    hass: HomeAssistant, sources: None, combined_entry: MockConfigEntry
) -> None:
    """Restored targets too close (or inverted) get the gap back."""
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(ENTITY_ID, HVACMode.OFF),
                {"target_temperature_low": 22.0, "target_temperature_high": 21.0},
            ),
        ),
    )
    await _setup(hass, combined_entry)

    assert _saved(hass)["target_temperature_low"] == 22.0
    assert _saved(hass)["target_temperature_high"] == 23.0


async def test_combined_slow_source(
    hass: HomeAssistant,
    sources: None,
    combined_entry: MockConfigEntry,
    ac: FakeClimate,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A source slow to show its new mode does not end heat_cool."""
    await _set_room(hass, "18")
    await _setup(hass, combined_entry)
    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=20.0, target_temp_high=26.0
    )
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)

    # The AC takes a few seconds to report its mode.
    async def slow(hvac_mode: HVACMode) -> None:
        ac.calls.append(("set_hvac_mode", {"hvac_mode": hvac_mode}))

    ac.async_set_hvac_mode = slow
    await _set_room(hass, "30")
    assert _state(hass, HEATER) == HVACMode.OFF
    assert _state(hass) == HVACMode.HEAT_COOL

    await _wait(hass, freezer, 5)
    ac._attr_hvac_mode = HVACMode.COOL
    ac.async_write_ha_state()
    await hass.async_block_till_done()
    assert _state(hass) == HVACMode.HEAT_COOL
    assert _attrs(hass)["active_entity_id"] == AC
    assert _sent(ac) == [{ATTR_TEMPERATURE: 26.0}]


async def test_combined_source_never_switches(
    hass: HomeAssistant,
    sources: None,
    combined_entry: MockConfigEntry,
    ac: FakeClimate,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A source that never shows its new mode ends heat_cool after the wait."""
    await _set_room(hass, "18")
    await _setup(hass, combined_entry)
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)

    async def ignore(hvac_mode: HVACMode) -> None:
        """The device does not react."""

    ac.async_set_hvac_mode = ignore
    await _set_room(hass, "30")
    assert _state(hass) == HVACMode.HEAT_COOL

    await _wait(hass, freezer, 13)
    assert _state(hass) == HVACMode.OFF


@pytest.mark.usefixtures("combined")
async def test_combined_without_room_temperature(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """Without any room temperature, the source already running is kept."""
    for source in (heater, ac):
        setattr(source, _attr_name("current_temperature"), None)
        source.async_write_ha_state()
    await _set_room(hass, STATE_UNAVAILABLE)
    await _on_source(hass, AC, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)

    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)

    assert _state(hass) == HVACMode.HEAT_COOL
    assert _attrs(hass)["active_entity_id"] == AC


@pytest.mark.usefixtures("combined")
async def test_combined_switch_error_logged(
    hass: HomeAssistant, ac: FakeClimate, caplog: pytest.LogCaptureFixture
) -> None:
    """A source refusing the new phase is logged."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)

    async def refuse(hvac_mode: HVACMode) -> None:
        raise HomeAssistantError("refused")

    ac.async_set_hvac_mode = refuse
    await _set_room(hass, "30")

    assert "Could not switch climate.living_room to cool: refused" in caplog.text


@pytest.mark.usefixtures("combined")
async def test_combined_sensor_unavailable(hass: HomeAssistant) -> None:
    """Without the sensor, the room temperature comes from the sources."""
    await _set_room(hass, STATE_UNAVAILABLE)

    # Off: the first usable source, the heater.
    assert _attrs(hass)["current_temperature"] == 19.5


@pytest.mark.usefixtures("combined")
async def test_combined_sensor_other_unit(hass: HomeAssistant) -> None:
    """A sensor in another unit is converted."""
    await _set_room(hass, "64.4", "°F")

    assert _attrs(hass)["current_temperature"] == pytest.approx(18.0)


@pytest.mark.usefixtures("combined")
async def test_combined_refused_without_cool_source(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """heat_cool needs both sources: refused when one is unavailable."""
    hass.states.async_set(AC, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    assert HVACMode.HEAT_COOL in _attrs(hass)["unavailable_modes"]

    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    assert err.value.translation_key == "source_unavailable"
    assert err.value.translation_placeholders == {
        "hvac_mode": HVACMode.HEAT_COOL,
        "entity_id": AC,
    }
    assert heater.calls == []


@pytest.mark.usefixtures("combined")
async def test_combined_turn_on_restores_it(hass: HomeAssistant) -> None:
    """Turn on goes back to heat_cool."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    await _call(hass, SERVICE_TURN_OFF)
    assert _state(hass) == HVACMode.OFF

    await _call(hass, SERVICE_TURN_ON)
    assert _state(hass) == HVACMode.HEAT_COOL


@pytest.mark.usefixtures("combined")
async def test_combined_uses_cool_settings(hass: HomeAssistant, ac: FakeClimate) -> None:
    """The cool phase uses the fan settings remembered for cool."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)
    await _call(hass, SERVICE_SET_FAN_MODE, fan_mode="high")
    await _on_source(hass, AC, SERVICE_SET_FAN_MODE, fan_mode="low")
    await _call(hass, SERVICE_TURN_OFF)
    await _on_source(hass, AC, SERVICE_SET_FAN_MODE, fan_mode="auto")

    await _set_room(hass, "30")
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)

    assert hass.states.get(AC).attributes[ATTR_FAN_MODE] == "low"


@pytest.mark.parametrize(("saved", "mode"), [(True, HVACMode.HEAT_COOL), (False, HVACMode.HEAT)])
async def test_combined_restored_after_restart(
    hass: HomeAssistant,
    sources: None,
    combined_entry: MockConfigEntry,
    heater: FakeClimate,
    saved: bool,
    mode: HVACMode,
) -> None:
    """heat_cool and its targets survive a restart."""
    heater._attr_hvac_mode = HVACMode.HEAT
    heater.async_write_ha_state()
    await _set_room(hass, "18")
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(ENTITY_ID, mode),
                {
                    "heat_cool": saved,
                    "target_temperature_low": 20.0,
                    "target_temperature_high": 23.0,
                },
            ),
        ),
    )
    await _setup(hass, combined_entry)

    assert _state(hass) == mode
    assert _saved(hass)["target_temperature_low"] == 20.0
    assert _saved(hass)["target_temperature_high"] == 23.0


async def test_combined_restored_when_sources_ready(
    hass: HomeAssistant,
    sources: None,
    combined_entry: MockConfigEntry,
    heater: FakeClimate,
) -> None:
    """Sources not ready at startup: heat_cool comes back once they are."""
    hass.states.async_set(HEATER, STATE_UNAVAILABLE)
    hass.states.async_set(AC, STATE_UNAVAILABLE)
    await _set_room(hass, "18")
    mock_restore_cache_with_extra_data(
        hass, ((State(ENTITY_ID, HVACMode.HEAT_COOL), {"heat_cool": True}),)
    )
    await _setup(hass, combined_entry)
    assert _saved(hass)["heat_cool"] is True

    heater._attr_hvac_mode = HVACMode.HEAT
    heater.async_write_ha_state()
    await hass.async_block_till_done()
    assert _state(hass) == HVACMode.HEAT_COOL


# Combined heat_cool: minimum phase duration and contradicting sources.


async def _setup_combined(
    hass: HomeAssistant, *, sensor: bool = True, **options: Any
) -> None:
    """Set up the combined heat_cool, targets 19-25 °C, room at 18 °C."""
    data: dict[str, Any] = {
        CONF_NAME: "Living room",
        CONF_HEAT_ENTITY: HEATER,
        CONF_COOL_ENTITY: AC,
        **options,
    }
    if sensor:
        data[CONF_TEMPERATURE_SENSOR] = SENSOR
        await _set_room(hass, "18")
    await _setup(hass, MockConfigEntry(domain=DOMAIN, title="Living room", data=data))
    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=19.0, target_temp_high=25.0
    )


async def _set_reading(hass: HomeAssistant, source: FakeClimate, value: float) -> None:
    """Show a room temperature on a source."""
    setattr(source, _attr_name("current_temperature"), value)
    source.async_write_ha_state()
    await hass.async_block_till_done()


@pytest.mark.usefixtures("sources")
async def test_phase_held_by_default(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A phase lasts 10 minutes before switching by itself to the other one."""
    await _setup_combined(hass)
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    assert _attrs(hass)["active_entity_id"] == HEATER

    await _set_room(hass, "26")
    await _wait(hass, freezer, 9 * 60)
    assert _attrs(hass)["active_entity_id"] == HEATER
    assert _state(hass, AC) == HVACMode.OFF

    # At the end of the hold, the room is checked again without any update.
    await _wait(hass, freezer, 61)
    assert _attrs(hass)["active_entity_id"] == AC
    assert _state(hass, HEATER) == HVACMode.OFF

    # The new phase is held too.
    await _set_room(hass, "18")
    await _wait(hass, freezer, 5 * 60)
    assert _attrs(hass)["active_entity_id"] == AC
    await _wait(hass, freezer, 5 * 60)
    assert _attrs(hass)["active_entity_id"] == HEATER


@pytest.mark.usefixtures("sources")
async def test_phase_hold_ends_if_back_between_targets(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Back between the targets at the end of the hold: no switch."""
    await _setup_combined(hass)
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)

    await _set_room(hass, "26")
    await _set_room(hass, "24")
    await _wait(hass, freezer, 11 * 60)
    assert _attrs(hass)["active_entity_id"] == HEATER


@pytest.mark.usefixtures("sources")
async def test_phase_hold_configured(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The minimum phase duration is an option."""
    await _setup_combined(hass, **{CONF_MIN_PHASE_DURATION: 2})
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)

    await _set_room(hass, "26")
    await _wait(hass, freezer, 60)
    assert _attrs(hass)["active_entity_id"] == HEATER
    await _wait(hass, freezer, 61)
    assert _attrs(hass)["active_entity_id"] == AC


@pytest.mark.usefixtures("sources")
async def test_phase_hold_ignored_on_new_targets(hass: HomeAssistant) -> None:
    """New targets from the user switch the phase at once."""
    await _setup_combined(hass)
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)

    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=16.0, target_temp_high=17.0
    )
    assert _attrs(hass)["active_entity_id"] == AC
    assert _state(hass, HEATER) == HVACMode.OFF


async def test_phase_not_held_after_restart(
    hass: HomeAssistant, sources: None, heater: FakeClimate
) -> None:
    """A phase brought back after a restart is not held."""
    heater._attr_hvac_mode = HVACMode.HEAT
    heater.async_write_ha_state()
    await _set_room(hass, "18")
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(ENTITY_ID, HVACMode.HEAT_COOL),
                {
                    "heat_cool": True,
                    "target_temperature_low": 19.0,
                    "target_temperature_high": 25.0,
                },
            ),
        ),
    )
    await _setup(
        hass,
        MockConfigEntry(
            domain=DOMAIN,
            title="Living room",
            data={
                CONF_NAME: "Living room",
                CONF_HEAT_ENTITY: HEATER,
                CONF_COOL_ENTITY: AC,
                CONF_TEMPERATURE_SENSOR: SENSOR,
            },
        ),
    )
    assert _state(hass) == HVACMode.HEAT_COOL

    await _set_room(hass, "26")
    assert _attrs(hass)["active_entity_id"] == AC


@pytest.mark.usefixtures("sources")
async def test_contradicting_sources_keep_phase(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """Without a sensor, the phase switches only when both sources agree.

    Each source reads near its own sensor: the heater reads warm, the AC
    cold. Following the running one would switch back and forth.
    """
    await _setup_combined(hass, sensor=False, **{CONF_MIN_PHASE_DURATION: 0})
    await _set_reading(hass, heater, 18.0)
    await _set_reading(hass, ac, 18.0)
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    assert _attrs(hass)["active_entity_id"] == HEATER

    # The heater reads above high, the AC below low: heat is kept.
    await _set_reading(hass, heater, 26.0)
    assert _attrs(hass)["active_entity_id"] == HEATER
    # The AC in between: kept too.
    await _set_reading(hass, ac, 22.0)
    assert _attrs(hass)["active_entity_id"] == HEATER

    # Both above high: cool.
    await _set_reading(hass, ac, 26.0)
    assert _attrs(hass)["active_entity_id"] == AC
    assert _state(hass, HEATER) == HVACMode.OFF

    # The AC reads below low, the heater still warm: cool is kept.
    await _set_reading(hass, ac, 18.0)
    assert _attrs(hass)["active_entity_id"] == AC
    await _set_reading(hass, heater, 18.0)
    assert _attrs(hass)["active_entity_id"] == HEATER


@pytest.mark.usefixtures("sources")
async def test_one_source_without_reading(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """A source without room temperature leaves the other one to decide."""
    await _setup_combined(hass, sensor=False, **{CONF_MIN_PHASE_DURATION: 0})
    await _set_reading(hass, heater, 18.0)
    await _set_reading(hass, ac, None)
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    assert _attrs(hass)["active_entity_id"] == HEATER

    await _set_reading(hass, heater, 26.0)
    assert _attrs(hass)["active_entity_id"] == AC


@pytest.mark.usefixtures("sources")
async def test_sensor_wins_over_sources(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """With a sensor, the readings of the sources are ignored."""
    await _setup_combined(hass, **{CONF_MIN_PHASE_DURATION: 0})
    await _set_reading(hass, heater, 30.0)
    await _set_reading(hass, ac, 30.0)
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    assert _attrs(hass)["active_entity_id"] == HEATER

    await _set_room(hass, "26")
    assert _attrs(hass)["active_entity_id"] == AC


# heat_cool with its own source.


@pytest.fixture
def heat_pump() -> FakeClimate:
    """Heat pump with a heat_cool mode and low/high targets."""
    return FakeClimate(
        HEAT_PUMP,
        [HVACMode.OFF, HVACMode.HEAT_COOL],
        features=ClimateEntityFeature.TARGET_TEMPERATURE_RANGE,
        current_temperature=22.0,
        target_temperature_low=19.0,
        target_temperature_high=25.0,
        target_temperature_step=0.5,
        min_temp=10.0,
        max_temp=30.0,
    )


@pytest.fixture
async def own_source(
    hass: HomeAssistant, heater: FakeClimate, heat_pump: FakeClimate
) -> None:
    """Set up a heater for heat and a heat pump for heat_cool."""
    setup_test_component_platform(hass, CLIMATE_DOMAIN, [heater, heat_pump])
    assert await async_setup_component(
        hass, CLIMATE_DOMAIN, {CLIMATE_DOMAIN: {"platform": "test"}}
    )
    await hass.async_block_till_done()
    await _setup(
        hass,
        MockConfigEntry(
            domain=DOMAIN,
            title="Living room",
            data={
                CONF_NAME: "Living room",
                CONF_HEAT_ENTITY: HEATER,
                CONF_HEAT_COOL_ENTITY: HEAT_PUMP,
            },
        ),
    )


@pytest.mark.usefixtures("own_source")
async def test_own_source_gets_targets(
    hass: HomeAssistant, heat_pump: FakeClimate
) -> None:
    """The heat_cool source gets the low/high targets, rounded and in its range."""
    assert _attrs(hass)["hvac_modes"] == [HVACMode.OFF, HVACMode.HEAT, HVACMode.HEAT_COOL]
    # The first targets come from the heat pump.
    assert _saved(hass)["target_temperature_low"] == 19.0
    assert _saved(hass)["target_temperature_high"] == 25.0

    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=5.0, target_temp_high=23.3
    )
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)

    assert _state(hass, HEAT_PUMP) == HVACMode.HEAT_COOL
    assert _sent(heat_pump) == [
        {ATTR_TARGET_TEMP_LOW: 10.0, ATTR_TARGET_TEMP_HIGH: 23.5}
    ]
    attrs = _attrs(hass)
    assert attrs[ATTR_TARGET_TEMP_LOW] == 10.0
    assert attrs[ATTR_TARGET_TEMP_HIGH] == 23.5
    # The targets only go to the heat pump: they are kept as it gets them.
    assert _saved(hass)["target_temperature_low"] == 10.0
    assert _saved(hass)["target_temperature_high"] == 23.5


@pytest.mark.usefixtures("own_source")
async def test_own_source_new_targets(
    hass: HomeAssistant, heat_pump: FakeClimate
) -> None:
    """New low/high targets are sent together to the running source."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    assert _sent(heat_pump) == []

    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=20.0, target_temp_high=24.0
    )
    assert _sent(heat_pump) == [
        {ATTR_TARGET_TEMP_LOW: 20.0, ATTR_TARGET_TEMP_HIGH: 24.0}
    ]


@pytest.mark.usefixtures("own_source")
async def test_own_source_late_targets_replaced(
    hass: HomeAssistant, heat_pump: FakeClimate, freezer: FrozenDateTimeFactory
) -> None:
    """Targets shown late by the source are ignored, then replaced."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)

    await _wait(hass, freezer, 5)
    setattr(heat_pump, _attr_name("target_temperature_low"), 16.0)
    setattr(heat_pump, _attr_name("target_temperature_high"), 28.0)
    heat_pump.async_write_ha_state()
    await hass.async_block_till_done()
    assert _attrs(hass)[ATTR_TARGET_TEMP_LOW] == 19.0

    await _wait(hass, freezer, 7)
    assert _sent(heat_pump) == [
        {ATTR_TARGET_TEMP_LOW: 19.0, ATTR_TARGET_TEMP_HIGH: 25.0}
    ]


@pytest.mark.usefixtures("own_source")
async def test_own_source_takeover(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Targets changed on the source become the targets of the entity."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    await _wait(hass, freezer, 13)

    await _on_source(
        hass, HEAT_PUMP, SERVICE_SET_TEMPERATURE, target_temp_low=21.0, target_temp_high=24.0
    )

    assert _saved(hass)["target_temperature_low"] == 21.0
    assert _saved(hass)["target_temperature_high"] == 24.0


# Minimum gap between the low and high targets.


@pytest.fixture
async def gap(hass: HomeAssistant, sources: None) -> None:
    """Set up the combined heat_cool with a gap of 2 degrees, targets 19-25."""
    await _set_room(hass, "18")
    await _setup(
        hass,
        MockConfigEntry(
            domain=DOMAIN,
            title="Living room",
            data={
                CONF_NAME: "Living room",
                CONF_HEAT_ENTITY: HEATER,
                CONF_COOL_ENTITY: AC,
                CONF_TEMPERATURE_SENSOR: SENSOR,
                CONF_MIN_GAP: 2.0,
            },
        ),
    )
    await _call(
        hass, SERVICE_SET_TEMPERATURE, target_temp_low=19.0, target_temp_high=25.0
    )


@pytest.mark.parametrize(
    ("data", "low", "high"),
    [
        # Within the gap: nothing moves.
        ({"target_temp_low": 21.0, "target_temp_high": 24.0}, 21.0, 24.0),
        ({"target_temp_low": 23.0, "target_temp_high": 25.0}, 23.0, 25.0),
        # The low target is the one just set: the high one moves.
        ({"target_temp_low": 24.0, "target_temp_high": 25.0}, 24.0, 26.0),
        # Both set: the high one moves.
        ({"target_temp_low": 22.0, "target_temp_high": 23.0}, 22.0, 24.0),
        # The single target of the mode is a setpoint too.
        ({"temperature": 24.0}, 24.0, 26.0),
    ],
)
@pytest.mark.usefixtures("gap")
async def test_gap_keeps_targets_apart(
    hass: HomeAssistant, data: dict[str, float], low: float, high: float
) -> None:
    """Setting a target moves the other one to keep the gap."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)

    await _call(hass, SERVICE_SET_TEMPERATURE, **data)

    assert _saved(hass)["target_temperature_low"] == low
    assert _saved(hass)["target_temperature_high"] == high


@pytest.mark.usefixtures("gap")
async def test_gap_cool_single_target_moves_low(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """Lowering the cooling setpoint pulls the heating one down."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)

    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=20.0)

    assert _saved(hass)["target_temperature_low"] == 18.0
    assert _saved(hass)["target_temperature_high"] == 20.0
    # The heater gets it once it runs.
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    assert _sent(heater)[-1] == {ATTR_TEMPERATURE: 18.0}


@pytest.mark.usefixtures("gap")
async def test_gap_limited_by_the_source_range(hass: HomeAssistant) -> None:
    """When the other source cannot follow, the target just set gives way.

    Heat tops at 30, so a gap of 2 degrees leaves a high target of 32.
    """
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=17.0)
    # The low target follows 2 degrees below.
    assert _saved(hass)["target_temperature_high"] == 17.0
    assert _saved(hass)["target_temperature_low"] == 15.0

    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=30.0)
    assert _saved(hass)["target_temperature_low"] == 30.0
    assert _saved(hass)["target_temperature_high"] == 32.0


async def test_initial_targets_keep_gap(hass: HomeAssistant, sources: None) -> None:
    """The first targets taken from the sources get the configured gap."""
    await _setup(
        hass,
        MockConfigEntry(
            domain=DOMAIN,
            title="Living room",
            data={
                CONF_NAME: "Living room",
                CONF_HEAT_ENTITY: HEATER,
                CONF_COOL_ENTITY: AC,
                CONF_MIN_GAP: 5.0,
            },
        ),
    )

    # The heater shows 20, the AC 24: the high target moves.
    assert _saved(hass)["target_temperature_low"] == 20.0
    assert _saved(hass)["target_temperature_high"] == 25.0


async def test_min_gap_by_default(
    hass: HomeAssistant, sources: None, combined_entry: MockConfigEntry
) -> None:
    """Without a configured gap, the low target stays 1 degree below the high one."""
    await _setup(hass, combined_entry)

    await _call(hass, SERVICE_SET_TEMPERATURE, target_temp_low=22.0, target_temp_high=22.0)
    assert _saved(hass)["target_temperature_low"] == 22.0
    assert _saved(hass)["target_temperature_high"] == 23.0

    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=23.0)
    assert _saved(hass)["target_temperature_low"] == 23.0
    assert _saved(hass)["target_temperature_high"] == 24.0


@pytest.mark.usefixtures("gap")
async def test_gap_kept_on_source_takeover(
    hass: HomeAssistant, heater: FakeClimate, freezer: FrozenDateTimeFactory
) -> None:
    """A change made on the source wins: the other target moves to keep the gap."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    await _wait(hass, freezer, 13)

    setattr(heater, _attr_name("target_temperature"), 24.0)
    heater.async_write_ha_state()
    await hass.async_block_till_done()

    assert _saved(hass)["target_temperature_low"] == 24.0
    assert _saved(hass)["target_temperature_high"] == 26.0


# Combined heat_cool: a source of the phase unavailable for a while


async def _lose(hass: HomeAssistant, entity_id: str) -> None:
    """Make a source unavailable."""
    hass.states.async_set(entity_id, STATE_UNAVAILABLE)
    await hass.async_block_till_done()


async def _back(hass: HomeAssistant, source: FakeClimate, mode: HVACMode, target: float) -> None:
    """Bring a source back, in a mode, showing its own target."""
    source._attr_hvac_mode = mode
    setattr(source, _attr_name("target_temperature"), target)
    source.async_write_ha_state()
    await hass.async_block_till_done()


@pytest.mark.usefixtures("combined")
async def test_combined_kept_while_phase_source_unavailable(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """The combined mode waits for its source, then sends it the targets."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    assert heater.target_temperature == 19.0

    await _lose(hass, HEATER)
    assert _state(hass) == HVACMode.HEAT_COOL

    # Back in heat, with its own target: it gets the one of the entity.
    await _back(hass, heater, HVACMode.HEAT, 15.0)
    assert _state(hass) == HVACMode.HEAT_COOL
    assert _attrs(hass)["active_entity_id"] == HEATER
    assert heater.target_temperature == 19.0
    assert _attrs(hass)["saved_targets"][ATTR_TARGET_TEMP_LOW] == 19.0


@pytest.mark.usefixtures("combined")
async def test_combined_ends_when_phase_source_back_off(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """A source back off was turned off meanwhile: the combined mode ends."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    await _lose(hass, HEATER)

    await _back(hass, heater, HVACMode.OFF, 19.0)

    assert _state(hass) == HVACMode.OFF
    # Turned on elsewhere later: it gives its target, it is not the return.
    await _back(hass, heater, HVACMode.HEAT, 22.0)
    assert _state(hass) == HVACMode.HEAT
    assert heater.target_temperature == 22.0
    assert _attrs(hass)["saved_targets"][ATTR_TARGET_TEMP_LOW] == 22.0


@pytest.mark.usefixtures("combined")
async def test_combined_switches_phase_while_source_unavailable(
    hass: HomeAssistant, ac: FakeClimate
) -> None:
    """The other phase still runs when the room asks for it."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT_COOL)
    await _lose(hass, HEATER)

    await _set_room(hass, "30")

    assert _state(hass) == HVACMode.HEAT_COOL
    assert _state(hass, AC) == HVACMode.COOL
    assert _attrs(hass)["active_entity_id"] == AC
