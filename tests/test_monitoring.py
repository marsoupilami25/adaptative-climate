"""Tests for the monitoring: the problem sensor of the readings.

The heater reads 19.5, the AC 21 (it serves cool and dry).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.climate import HVACMode
from homeassistant.const import CONF_NAME, STATE_OFF, STATE_ON, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.adaptative_climate.const import (
    CONF_COOL_ENTITY,
    CONF_DRY_ENTITY,
    CONF_HEAT_ENTITY,
    CONF_MONITORING_DURATION,
    CONF_TEMPERATURE_SENSOR,
    DOMAIN,
)
from custom_components.adaptative_climate.engine.monitoring import (
    GapTracker,
    Reading,
    find_gaps,
)

from .conftest import AC, HEATER, FakeClimate, _attr_name

MONITORING = "binary_sensor.living_room_monitoring"
SENSOR = "sensor.room"


def _entry(**settings: Any) -> MockConfigEntry:
    """Heater for heat, AC for cool and dry; no duration unless set (None: default)."""
    data = {
        CONF_NAME: "Living room",
        CONF_HEAT_ENTITY: HEATER,
        CONF_COOL_ENTITY: AC,
        CONF_DRY_ENTITY: AC,
        CONF_MONITORING_DURATION: 0,
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


async def _set_room(hass: HomeAssistant, value: float) -> None:
    hass.states.async_set(
        SENSOR, str(value), {"unit_of_measurement": "°C", "device_class": "temperature"}
    )
    await hass.async_block_till_done()


async def _read(hass: HomeAssistant, source: FakeClimate, value: float) -> None:
    """Change what a source reads."""
    setattr(source, _attr_name("current_temperature"), value)
    source.async_write_ha_state()
    await hass.async_block_till_done()


async def _wait(hass: HomeAssistant, freezer: FrozenDateTimeFactory, minutes: float) -> None:
    freezer.tick(timedelta(minutes=minutes))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _problems(hass: HomeAssistant) -> list[dict[str, Any]]:
    return hass.states.get(MONITORING).attributes["problems"]


# Pure functions


def _reading(entity_id: str, temperature: float, *modes: HVACMode) -> Reading:
    return Reading(entity_id, modes or (HVACMode.HEAT,), temperature)


def test_find_gaps() -> None:
    """The sensor against each reading, and readings of different entities."""
    heater = _reading("climate.h", 18.0)
    ac = _reading("climate.a", 22.5, HVACMode.COOL)
    # The AC in dry, with another offset: never compared with the AC in cool.
    dry = _reading("climate.a", 18.0, HVACMode.DRY)

    gaps = find_gaps(20.0, [heater, ac, dry], 2.0)

    assert {key: round(gap.gap, 1) for key, gap in gaps.items()} == {
        ("sensor", "climate.a:cool"): 2.5,
        ("sources", "climate.h:heat", "climate.a:cool"): 4.5,
    }
    # Without sensor, only the sources.
    assert list(find_gaps(None, [heater, ac], 2.0)) == [
        ("sources", "climate.h:heat", "climate.a:cool")
    ]
    # A gap equal to the maximum is no problem.
    assert find_gaps(20.0, [heater], 2.0) == {}


def test_gap_tracker() -> None:
    """A gap is a problem once it lasted the duration, from zero when it comes back."""
    tracker = GapTracker(timedelta(minutes=15))
    gaps = find_gaps(None, [_reading("climate.h", 18.0), _reading("climate.a", 22.0)], 2.0)
    start = dt_util.utcnow()

    assert tracker.update(start, gaps) == {}
    assert tracker.next_problem(start) == timedelta(minutes=15)
    later = start + timedelta(minutes=10)
    assert tracker.update(later, gaps) == {}
    assert tracker.next_problem(later) == timedelta(minutes=5)
    later = start + timedelta(minutes=15)
    assert tracker.update(later, gaps) == gaps
    assert tracker.next_problem(later) is None

    # Gone, then back: from zero.
    assert tracker.update(later, {}) == {}
    assert tracker.update(later + timedelta(minutes=1), gaps) == {}


# The sensor entity


async def test_snapshot(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    sources: None,
) -> None:
    """The registry entry and state match the snapshot."""
    entry = _entry()
    entry.add_to_hass(hass)
    with patch("custom_components.adaptative_climate.PLATFORMS", [Platform.BINARY_SENSOR]):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    await snapshot_platform(hass, entity_registry, snapshot, entry.entry_id)


async def test_not_created_without_anything_to_compare(
    hass: HomeAssistant, sources: None
) -> None:
    """One source entity and no sensor: nothing to compare, no sensor."""
    await _setup(
        hass,
        MockConfigEntry(
            domain=DOMAIN,
            title="Living room",
            data={CONF_NAME: "Living room", CONF_COOL_ENTITY: AC, CONF_DRY_ENTITY: AC},
        ),
    )

    assert hass.states.get(MONITORING) is None


async def test_gap_between_sources(
    hass: HomeAssistant,
    sources: None,
    heater: FakeClimate,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Two sources reading too far apart: a problem, until they agree again."""
    await _setup(hass, _entry())
    assert hass.states.get(MONITORING).state == STATE_OFF

    await _read(hass, heater, 24.0)

    assert hass.states.get(MONITORING).state == STATE_ON
    assert _problems(hass) == [
        {
            "type": "sources",
            "gap": 3.0,
            "sources": [
                {"entity_id": HEATER, "modes": ["heat"], "temperature": 24.0},
                # The AC serves cool and dry, without offset: one reading.
                {"entity_id": AC, "modes": ["cool", "dry"], "temperature": 21.0},
            ],
        }
    ]
    assert hass.states.get(MONITORING).attributes["max_gap"] == 2.0
    assert (
        "Living room: temperatures disagree for 0 min, above 2.0: climate.heater (heat)"
        " reads 24.0 and climate.ac (cool, dry) reads 21.0: gap 3.0"
    ) in caplog.text

    # Logged once, not on each update.
    caplog.clear()
    await _read(hass, heater, 24.5)
    assert "disagree" not in caplog.text

    await _read(hass, heater, 22.0)
    assert hass.states.get(MONITORING).state == STATE_OFF
    assert _problems(hass) == []
    assert "Living room: temperatures agree again: climate.heater and climate.ac" in caplog.text


async def test_gap_with_room_sensor(
    hass: HomeAssistant,
    sources: None,
    heater: FakeClimate,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A source reading too far from the room sensor: a problem."""
    await _set_room(hass, 20.0)
    await _setup(hass, _entry(**{CONF_TEMPERATURE_SENSOR: SENSOR, "monitoring_gap": 3}))
    assert hass.states.get(MONITORING).state == STATE_OFF

    await _set_room(hass, 23.5)

    # 4 from the heater (19.5), 2.5 from the AC (21): the heater only.
    assert _problems(hass) == [
        {
            "type": "sensor",
            "gap": 4.0,
            "sensor_temperature": 23.5,
            "sources": [{"entity_id": HEATER, "modes": ["heat"], "temperature": 19.5}],
        }
    ]
    assert (
        "climate.heater (heat) reads 19.5, the room sensor 23.5: gap 4.0" in caplog.text
    )


async def test_readings_minus_offset(hass: HomeAssistant, sources: None) -> None:
    """Readings are compared minus the offset of their mode."""
    # The heater reads 19.5 (17 in the room), the AC 21 (17 in the room, in
    # cool; 21 in dry, without offset).
    await _set_room(hass, 17.0)
    await _setup(
        hass,
        _entry(
            **{CONF_TEMPERATURE_SENSOR: SENSOR, "heat_offset": 2.5, "cool_offset": 4.0}
        ),
    )

    # Only the AC in dry, without offset, is far from the room and the heater.
    assert hass.states.get(MONITORING).state == STATE_ON
    assert {
        (problem["type"], *(source["entity_id"] for source in problem["sources"]))
        for problem in _problems(hass)
    } == {("sensor", AC), ("sources", HEATER, AC)}
    assert all(
        source["modes"] == ["dry"]
        for problem in _problems(hass)
        for source in problem["sources"]
        if source["entity_id"] == AC
    )


async def test_problem_after_duration(
    hass: HomeAssistant,
    sources: None,
    heater: FakeClimate,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A gap is a problem once it lasted the duration (15 minutes by default)."""
    await _setup(hass, _entry(**{CONF_MONITORING_DURATION: None}))

    await _read(hass, heater, 24.0)
    assert hass.states.get(MONITORING).state == STATE_OFF
    await _wait(hass, freezer, 14)
    assert hass.states.get(MONITORING).state == STATE_OFF
    # No update needed: it turns on by itself.
    await _wait(hass, freezer, 1)
    assert hass.states.get(MONITORING).state == STATE_ON

    # Gone, then back: 15 minutes again.
    await _read(hass, heater, 20.0)
    assert hass.states.get(MONITORING).state == STATE_OFF
    await _read(hass, heater, 24.0)
    assert hass.states.get(MONITORING).state == STATE_OFF
    await _wait(hass, freezer, 15)
    assert hass.states.get(MONITORING).state == STATE_ON


async def test_unavailable_source_not_compared(
    hass: HomeAssistant, sources: None, heater: FakeClimate
) -> None:
    """A source without reading is left out."""
    await _setup(hass, _entry())
    await _read(hass, heater, 24.0)
    assert hass.states.get(MONITORING).state == STATE_ON

    hass.states.async_set(HEATER, "unavailable")
    await hass.async_block_till_done()

    assert hass.states.get(MONITORING).state == STATE_OFF
