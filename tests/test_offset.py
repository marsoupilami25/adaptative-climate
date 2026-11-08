"""Tests for the temperature offset of the mode sources.

The heater reads 2 degrees warmer than the room (heat_offset 2), the AC
1 degree colder (cool_offset -1). The entity shows the room: a source gets
the target plus its offset, and its targets and readings are shown minus
its offset.
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
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, CONF_NAME
from homeassistant.core import HomeAssistant

from custom_components.adaptative_climate.const import (
    CONF_COOL_ENTITY,
    CONF_DRY_ENTITY,
    CONF_HEAT_ENTITY,
    CONF_MAX_TEMP,
    CONF_MIN_PHASE_DURATION,
    DOMAIN,
)

from .conftest import AC, ENTITY_ID, HEATER, FakeClimate

LOW = "target_temperature_low"
HIGH = "target_temperature_high"


def _entry(**settings: Any) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id="01JTESTENTRY000000000000000",
        title="Living room",
        data={
            CONF_NAME: "Living room",
            CONF_HEAT_ENTITY: HEATER,
            CONF_COOL_ENTITY: AC,
            CONF_DRY_ENTITY: AC,
            "heat_offset": 2.0,
            "cool_offset": -1.0,
            **settings,
        },
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture
async def offsets(hass: HomeAssistant, sources: None) -> None:
    """Set up the entry with the offsets."""
    await _setup(hass, _entry())


async def _call(hass: HomeAssistant, service: str, **data: Any) -> None:
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
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _attrs(hass: HomeAssistant) -> dict[str, Any]:
    return hass.states.get(ENTITY_ID).attributes


def _sent(source: FakeClimate) -> list[float]:
    return [
        data[ATTR_TEMPERATURE]
        for name, data in source.calls
        if name == "set_temperature" and ATTR_TEMPERATURE in data
    ]


def _saved(hass: HomeAssistant, name: str) -> float | None:
    entity = hass.data[CLIMATE_DOMAIN].get_entity(ENTITY_ID)
    return entity.extra_restore_state_data.as_dict()[name]


@pytest.mark.usefixtures("offsets")
async def test_initial_targets_minus_offset(hass: HomeAssistant) -> None:
    """The first targets come from the sources, minus their offset."""
    # The heater shows 20 (18 in the room), the AC 24 (25 in the room).
    assert _saved(hass, LOW) == 18.0
    assert _saved(hass, HIGH) == 25.0
    assert _saved(hass, "target_temperature") == 18.0
    assert (_attrs(hass)["target_temp_low"], _attrs(hass)["target_temp_high"]) == (18.0, 25.0)
    # Off: the room temperature of the first source, the heater (19.5 - 2).
    assert _attrs(hass)["current_temperature"] == 17.5


@pytest.mark.usefixtures("offsets")
async def test_heat_sends_target_plus_offset(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """The heater gets the target plus 2, the entity shows the target."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    # The heater already shows 20, the target 18 plus 2: nothing sent.
    assert _sent(heater) == []
    assert _attrs(hass)[ATTR_TEMPERATURE] == 18.0

    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=21.0)

    assert _sent(heater) == [23.0]
    assert _attrs(hass)[ATTR_TEMPERATURE] == 21.0
    assert _saved(hass, LOW) == 21.0
    assert _attrs(hass)["current_temperature"] == 17.5
    # The range of the heater (5-30), in the room.
    assert (_attrs(hass)["min_temp"], _attrs(hass)["max_temp"]) == (3.0, 28.0)


@pytest.mark.usefixtures("offsets")
async def test_negative_offset(hass: HomeAssistant, ac: FakeClimate) -> None:
    """The AC reads 1 degree colder: it gets the target minus 1."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.COOL)
    # The AC already shows 24, the target 25 minus 1.
    assert _sent(ac) == []
    assert _attrs(hass)[ATTR_TEMPERATURE] == 25.0

    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=26.0)

    assert _sent(ac) == [25.0]
    assert _attrs(hass)[ATTR_TEMPERATURE] == 26.0
    assert _attrs(hass)["current_temperature"] == 22.0


@pytest.mark.usefixtures("offsets")
async def test_dry_has_its_own_offset(hass: HomeAssistant, ac: FakeClimate) -> None:
    """The offset belongs to the mode: the AC in dry has none."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.DRY)

    # The single target, 18, as is.
    assert _sent(ac) == [18.0]
    assert _attrs(hass)[ATTR_TEMPERATURE] == 18.0
    assert _attrs(hass)["current_temperature"] == 21.0


@pytest.mark.usefixtures("offsets")
async def test_change_on_source_minus_offset(
    hass: HomeAssistant, heater: FakeClimate, freezer: FrozenDateTimeFactory
) -> None:
    """A target set on the source is taken minus its offset, and not sent back."""
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=21.0)
    await _wait(hass, freezer, 13)

    await _on_source(hass, HEATER, SERVICE_SET_TEMPERATURE, temperature=24.0)

    assert _attrs(hass)[ATTR_TEMPERATURE] == 22.0
    assert _saved(hass, LOW) == 22.0
    # Only the call made on the heater: nothing sent back.
    assert _sent(heater) == [23.0, 24.0]


async def test_source_turned_on_elsewhere_minus_offset(
    hass: HomeAssistant, sources: None, heater: FakeClimate
) -> None:
    """A source turned on elsewhere gives its target, minus its offset."""
    await _setup(hass, _entry())
    await _on_source(hass, HEATER, SERVICE_SET_TEMPERATURE, temperature=25.0)
    await _on_source(hass, HEATER, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)

    assert _attrs(hass)[ATTR_TEMPERATURE] == 23.0
    assert _saved(hass, LOW) == 23.0
    assert _sent(heater) == [25.0]


async def test_limits_apply_to_the_room(
    hass: HomeAssistant, sources: None, heater: FakeClimate
) -> None:
    """The configured limits apply to the target, the source range to what it gets."""
    await _setup(hass, _entry(**{CONF_MAX_TEMP: 25.0}))
    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)
    assert _attrs(hass)["max_temp"] == 25.0

    await _call(hass, SERVICE_SET_TEMPERATURE, temperature=24.0)
    # 24 plus 2: above the limit, but in the range of the heater.
    assert _sent(heater) == [26.0]
    assert _attrs(hass)[ATTR_TEMPERATURE] == 24.0


async def test_source_range_with_offset(
    hass: HomeAssistant, sources: None, heater: FakeClimate
) -> None:
    """The source gets at most its maximum, the target shown is minus the offset."""
    await _setup(hass, _entry(heat_offset=4.0))
    # Off, the range is the widest one: the heating setpoint can be 28.
    await _call(hass, SERVICE_SET_TEMPERATURE, target_temp_low=28.0, target_temp_high=30.0)

    await _call(hass, SERVICE_SET_HVAC_MODE, hvac_mode=HVACMode.HEAT)

    # 28 plus 4 is above the maximum of the heater (30).
    assert _sent(heater) == [30.0]
    assert _attrs(hass)[ATTR_TEMPERATURE] == 26.0
    assert _attrs(hass)["max_temp"] == 26.0


async def test_combined_follows_readings_minus_offset(
    hass: HomeAssistant, sources: None, heater: FakeClimate, ac: FakeClimate
) -> None:
    """Without sensor, the combined heat_cool follows the readings minus their offset."""
    # The heater reads 19.5 (offset 0), the AC 21, 4 colder than the room: 25.
    await _setup(
        hass, _entry(heat_offset=0.0, cool_offset=-4.0, **{CONF_MIN_PHASE_DURATION: 0})
    )

    await _call(
        hass,
        SERVICE_SET_TEMPERATURE,
        hvac_mode=HVACMode.HEAT_COOL,
        target_temp_low=20.0,
        target_temp_high=24.0,
    )

    # Their mean (22.25) is closer to the high target: cool. Without the
    # offset, it would be 20.25: heat.
    assert _attrs(hass)["active_entity_id"] == AC
    assert _sent(ac) == [20.0]
    assert (_attrs(hass)["target_temp_low"], _attrs(hass)["target_temp_high"]) == (20.0, 24.0)
