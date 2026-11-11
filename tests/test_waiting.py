"""Tests of a source that becomes unavailable: what the entity keeps and shows."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_ACTION,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_TARGET_TEMP_STEP,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    HVACMode,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import issue_registry as ir

from custom_components.adaptative_climate.const import CONF_HEAT_ENTITY, DOMAIN

from .conftest import AC, ENTITY_ID, HEATER, FakeClimate

SENSOR_ID = "binary_sensor.living_room_source_unavailable"


async def _call(hass: HomeAssistant, service: str, **data: Any) -> None:
    """Call a climate service on the Adaptative Climate entity."""
    await hass.services.async_call(
        CLIMATE_DOMAIN, service, {ATTR_ENTITY_ID: ENTITY_ID, **data}, blocking=True
    )
    await hass.async_block_till_done()


async def _mode(hass: HomeAssistant, mode: HVACMode) -> None:
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=mode)


async def _lose(hass: HomeAssistant, entity_id: str) -> None:
    """Make a source unavailable."""
    hass.states.async_set(entity_id, STATE_UNAVAILABLE)
    await hass.async_block_till_done()


async def _back(hass: HomeAssistant, source: FakeClimate, mode: HVACMode) -> None:
    """Bring a source back, in a mode."""
    source._attr_hvac_mode = mode
    source.async_write_ha_state()
    await hass.async_block_till_done()


def _attrs(hass: HomeAssistant) -> dict[str, Any]:
    return dict(hass.states.get(ENTITY_ID).attributes)


def _sensor(hass: HomeAssistant) -> State:
    state = hass.states.get(SENSOR_ID)
    assert state is not None
    return state


@pytest.mark.usefixtures("init_integration")
async def test_waiting_for_source_of_mode(hass: HomeAssistant, heater: FakeClimate) -> None:
    """The mode is unknown, with the targets and range of the mode waited for."""
    await _mode(hass, HVACMode.HEAT)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=22.0)
    assert _sensor(hass).state == STATE_OFF

    await _lose(hass, HEATER)

    assert hass.states.get(ENTITY_ID).state == STATE_UNKNOWN
    attrs = _attrs(hass)
    assert attrs[ATTR_TEMPERATURE] == 22.0
    assert (attrs[ATTR_MIN_TEMP], attrs[ATTR_MAX_TEMP]) == (5.0, 30.0)
    assert attrs.get(ATTR_HVAC_ACTION) is None
    assert attrs["active_entity_id"] is None
    sensor = _sensor(hass)
    assert sensor.state == STATE_ON
    assert sensor.attributes["entity_ids"] == [HEATER]

    await _back(hass, heater, HVACMode.HEAT)

    assert hass.states.get(ENTITY_ID).state == HVACMode.HEAT
    assert _sensor(hass).state == STATE_OFF


@pytest.mark.usefixtures("init_integration")
async def test_range_and_step_kept_while_away(hass: HomeAssistant) -> None:
    """The range and step of a source away stay those it showed."""
    await _mode(hass, HVACMode.COOL)
    before = _attrs(hass)
    assert (before[ATTR_MIN_TEMP], before[ATTR_MAX_TEMP]) == (16.0, 32.0)

    await _lose(hass, AC)

    attrs = _attrs(hass)
    assert (attrs[ATTR_MIN_TEMP], attrs[ATTR_MAX_TEMP]) == (16.0, 32.0)
    assert attrs[ATTR_TARGET_TEMP_STEP] == before[ATTR_TARGET_TEMP_STEP]


@pytest.mark.usefixtures("init_integration")
async def test_target_set_while_waiting_sent_on_return(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """A target set while waiting is shown, and sent when the source is back."""
    await _mode(hass, HVACMode.HEAT)
    await _lose(hass, HEATER)

    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=23.0)
    assert _attrs(hass)[ATTR_TEMPERATURE] == 23.0
    assert hass.states.get(ENTITY_ID).state == STATE_UNKNOWN

    await _back(hass, heater, HVACMode.HEAT)
    assert heater.target_temperature == 23.0


@pytest.mark.usefixtures("init_integration")
async def test_fan_while_waiting(hass: HomeAssistant, ac: FakeClimate) -> None:
    """The fan of the mode waited for is shown; a change is sent when the source is back."""
    await _mode(hass, HVACMode.COOL)
    await _lose(hass, AC)

    attrs = _attrs(hass)
    assert attrs[ATTR_FAN_MODES] == ["auto", "low", "high"]
    assert attrs[ATTR_FAN_MODE] == "auto"

    await _call(hass, SERVICE_SET_FAN_MODE, fan_mode="high")
    assert _attrs(hass)[ATTR_FAN_MODE] == "high"
    assert ("set_fan_mode", {"fan_mode": "high"}) not in ac.calls

    await _back(hass, ac, HVACMode.COOL)
    assert ("set_fan_mode", {"fan_mode": "high"}) in ac.calls
    assert _attrs(hass)[ATTR_FAN_MODE] == "high"


@pytest.mark.usefixtures("init_integration")
async def test_turn_off_while_waiting(hass: HomeAssistant, heater: FakeClimate) -> None:
    """Turning off ends the wait; turn_on while waiting does nothing."""
    await _mode(hass, HVACMode.HEAT)
    await _lose(hass, HEATER)
    calls = len(heater.calls)

    await _call(hass, SERVICE_TURN_ON)
    assert hass.states.get(ENTITY_ID).state == STATE_UNKNOWN
    assert len(heater.calls) == calls

    await _call(hass, SERVICE_TURN_OFF)
    assert hass.states.get(ENTITY_ID).state == HVACMode.OFF
    assert _sensor(hass).state == STATE_OFF


@pytest.mark.usefixtures("init_integration")
async def test_off_source_unavailable(hass: HomeAssistant) -> None:
    """Off, a source away changes nothing: no wait, no problem."""
    await _lose(hass, HEATER)

    assert hass.states.get(ENTITY_ID).state == HVACMode.OFF
    assert _sensor(hass).state == STATE_OFF


@pytest.mark.usefixtures("init_integration")
async def test_other_source_on_while_waiting(hass: HomeAssistant, ac: FakeClimate) -> None:
    """Another source turned on elsewhere ends the wait."""
    await _mode(hass, HVACMode.HEAT)
    await _lose(hass, HEATER)

    await _back(hass, ac, HVACMode.COOL)

    assert hass.states.get(ENTITY_ID).state == HVACMode.COOL
    assert _sensor(hass).state == STATE_OFF


async def test_waiting_restored_after_restart(
    hass: HomeAssistant, sources: None, mock_config_entry: MockConfigEntry
) -> None:
    """Waiting for a source at shutdown, still unavailable at startup: still waiting."""
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(ENTITY_ID, STATE_UNKNOWN),
                {
                    "waiting": [HEATER, HVACMode.HEAT, HVACMode.HEAT],
                    "known": {HEATER: {ATTR_MIN_TEMP: 7.0, ATTR_MAX_TEMP: 28.0}},
                },
            ),
        ),
    )
    hass.states.async_set(HEATER, STATE_UNAVAILABLE)
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == STATE_UNKNOWN
    attrs = _attrs(hass)
    assert (attrs[ATTR_MIN_TEMP], attrs[ATTR_MAX_TEMP]) == (7.0, 28.0)
    assert _sensor(hass).state == STATE_ON


async def test_single_source_unavailable(hass: HomeAssistant, sources: None) -> None:
    """With one source, the entity is unavailable while it is; the sensor tells why."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Living room",
        data={CONF_NAME: "Living room", CONF_HEAT_ENTITY: HEATER},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _mode(hass, HVACMode.HEAT)

    await _lose(hass, HEATER)

    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE
    assert _sensor(hass).state == STATE_ON


@pytest.mark.usefixtures("init_integration")
async def test_mode_issue_kept_while_source_away(
    hass: HomeAssistant, issue_registry: ir.IssueRegistry
) -> None:
    """A source away is judged on the modes it offered when last usable."""
    issue_id = "01JTESTENTRY000000000000000_dry_not_supported"
    hass.states.async_set(AC, HVACMode.OFF, {"hvac_modes": [HVACMode.OFF, HVACMode.COOL]})
    await hass.async_block_till_done()
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is not None

    await _lose(hass, AC)

    assert issue_registry.async_get_issue(DOMAIN, issue_id) is not None
