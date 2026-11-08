"""Tests for the external sensor: the room temperature written to the sources.

The heater regulates with input_number.heater_external (0-40, step 0.5).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    CONF_NAME,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component

from custom_components.adaptative_climate.const import (
    CONF_COOL_ENTITY,
    CONF_HEAT_ENTITY,
    CONF_TEMPERATURE_SENSOR,
    DOMAIN,
)

from .conftest import AC, ENTITY_ID, HEATER, FakeClimate

SENSOR = "sensor.room"
EXTERNAL = "input_number.heater_external"


@pytest.fixture
async def external(hass: HomeAssistant) -> None:
    """Add the external sensor entities."""
    assert await async_setup_component(
        hass,
        "input_number",
        {
            "input_number": {
                "heater_external": {"min": 0, "max": 40, "step": 0.5, "initial": 10},
                "heater_fahrenheit": {
                    "min": 32,
                    "max": 104,
                    "step": 0.1,
                    "initial": 50,
                    "unit_of_measurement": "°F",
                },
                "heater_narrow": {"min": 5, "max": 20, "step": 0.5, "initial": 10},
            }
        },
    )
    await hass.async_block_till_done()


def _entry(**settings: Any) -> MockConfigEntry:
    data = {
        CONF_NAME: "Living room",
        CONF_HEAT_ENTITY: HEATER,
        CONF_COOL_ENTITY: AC,
        CONF_TEMPERATURE_SENSOR: SENSOR,
        "heat_external_sensor": EXTERNAL,
        **settings,
    }
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id="01JTESTENTRY000000000000000",
        title="Living room",
        data={key: value for key, value in data.items() if value is not None},
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _set_room(hass: HomeAssistant, value: Any) -> None:
    hass.states.async_set(
        SENSOR, str(value), {"unit_of_measurement": "°C", "device_class": "temperature"}
    )
    await hass.async_block_till_done()


async def _wait(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _value(hass: HomeAssistant, entity_id: str = EXTERNAL) -> float:
    return float(hass.states.get(entity_id).state)


async def _set_value(hass: HomeAssistant, value: float) -> None:
    """Change the external sensor directly (the device forgot it)."""
    await hass.services.async_call(
        "input_number", "set_value", {ATTR_ENTITY_ID: EXTERNAL, "value": value}, blocking=True
    )
    await hass.async_block_till_done()


@pytest.mark.usefixtures("sources", "external")
async def test_written_at_start_rounded(hass: HomeAssistant) -> None:
    """The room temperature is written at once, rounded to the step."""
    await _set_room(hass, 21.3)
    await _setup(hass, _entry())

    assert _value(hass) == 21.5


@pytest.mark.usefixtures("sources", "external")
async def test_written_at_most_every_minute(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A change waits for the minute after the last write, then the latest value goes."""
    await _set_room(hass, 20)
    await _setup(hass, _entry())
    assert _value(hass) == 20.0

    await _wait(hass, freezer, 10)
    await _set_room(hass, 21)
    await _set_room(hass, 22)
    assert _value(hass) == 20.0
    await _wait(hass, freezer, 49)
    assert _value(hass) == 20.0
    await _wait(hass, freezer, 1)
    assert _value(hass) == 22.0

    # More than a minute later: at once.
    await _wait(hass, freezer, 61)
    await _set_room(hass, 23)
    assert _value(hass) == 23.0


@pytest.mark.usefixtures("sources", "external")
async def test_written_again_every_30_minutes(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The value is written again, unchanged, every 30 minutes."""
    await _set_room(hass, 20)
    await _setup(hass, _entry())
    await _set_value(hass, 10)

    await _wait(hass, freezer, 29 * 60)
    assert _value(hass) == 10.0
    await _wait(hass, freezer, 60)
    assert _value(hass) == 20.0


@pytest.mark.usefixtures("sources", "external")
async def test_unit_of_the_target(hass: HomeAssistant) -> None:
    """A target in °F gets the room temperature in °F."""
    await _set_room(hass, 21)
    await _setup(hass, _entry(heat_external_sensor="input_number.heater_fahrenheit"))

    assert _value(hass, "input_number.heater_fahrenheit") == 69.8


@pytest.mark.usefixtures("sources", "external")
async def test_out_of_range_not_written(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """A value out of the range of the target is not written."""
    await _set_room(hass, 25)
    await _setup(hass, _entry(heat_external_sensor="input_number.heater_narrow"))

    assert _value(hass, "input_number.heater_narrow") == 10.0
    assert "out of the range of input_number.heater_narrow" in caplog.text


@pytest.mark.usefixtures("sources", "external")
async def test_nothing_written_without_room_temperature(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """While the room sensor is unavailable, nothing is written."""
    await _set_room(hass, STATE_UNAVAILABLE)
    await _setup(hass, _entry())
    assert _value(hass) == 10.0

    await _wait(hass, freezer, 31 * 60)
    assert _value(hass) == 10.0
    await _set_room(hass, 19)
    assert _value(hass) == 19.0


@pytest.mark.usefixtures("sources", "external")
async def test_offset_ignored(hass: HomeAssistant, heater: FakeClimate) -> None:
    """A source with an external sensor reads the room: its offset is ignored."""
    await _set_room(hass, 20)
    await _setup(hass, _entry(heat_offset=2.0))

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_TEMPERATURE: 21.0, ATTR_HVAC_MODE: HVACMode.HEAT},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert heater.calls[-1] == (
        "set_temperature",
        {ATTR_TEMPERATURE: 21.0, ATTR_ENTITY_ID: [HEATER]},
    )


@pytest.mark.usefixtures("sources", "external")
async def test_stopped_on_unload(hass: HomeAssistant) -> None:
    """Once the entry unloads, nothing is written."""
    await _set_room(hass, 20)
    entry = _entry()
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    await _set_room(hass, 25)
    assert _value(hass) == 20.0


async def test_config_flow_needs_room_sensor(hass: HomeAssistant) -> None:
    """An external sensor without the room sensor is refused."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Living room", CONF_HEAT_ENTITY: HEATER, "heat_external_sensor": EXTERNAL},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"heat_external_sensor": "external_sensor_without_sensor"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Living room",
            CONF_HEAT_ENTITY: HEATER,
            "heat_external_sensor": EXTERNAL,
            CONF_TEMPERATURE_SENSOR: SENSOR,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["heat_external_sensor"] == EXTERNAL
