"""Tests for the monitoring: the problem sensor of the readings, targets and sources.

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
    async_capture_events,
    async_fire_time_changed,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.adaptative_climate.const import (
    CONF_COOL_ENTITY,
    CONF_DRY_ENTITY,
    CONF_HEAT_ENTITY,
    CONF_MAX_TEMP,
    CONF_MONITORING_DURATION,
    CONF_TEMPERATURE_SENSOR,
    DOMAIN,
    EVENT_PROBLEM,
)
from custom_components.adaptative_climate.engine.monitoring import (
    ProblemTracker,
    Reading,
    find_gaps,
)

from .conftest import AC, HEATER, FakeClimate, _attr_name

MONITORING = "binary_sensor.living_room_monitoring"
ENTITY_ID = "climate.living_room"
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


async def _climate(hass: HomeAssistant, service: str, **data: Any) -> None:
    """Call a climate service on the Adaptative Climate entity."""
    await hass.services.async_call(
        CLIMATE_DOMAIN, service, {ATTR_ENTITY_ID: ENTITY_ID, **data}, blocking=True
    )
    await hass.async_block_till_done()


async def _wait_seconds(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float
) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _silent(source: FakeClimate) -> None:
    """Make a source take target calls without showing them, like a lost command."""

    async def ignore(**kwargs: Any) -> None:
        source.calls.append(("set_temperature", kwargs))

    source.async_set_temperature = ignore


async def _show_target(hass: HomeAssistant, source: FakeClimate, value: float) -> None:
    """Show a target on a source, as the device reports it."""
    setattr(source, _attr_name("target_temperature"), value)
    source.async_write_ha_state()
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
    tracker = ProblemTracker(timedelta(minutes=15))
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


async def test_created_with_one_source(hass: HomeAssistant, sources: None) -> None:
    """One source entity and no sensor: no temperature to compare, but targets."""
    await _setup(
        hass,
        MockConfigEntry(
            domain=DOMAIN,
            title="Living room",
            data={CONF_NAME: "Living room", CONF_COOL_ENTITY: AC, CONF_DRY_ENTITY: AC},
        ),
    )

    assert hass.states.get(MONITORING).state == STATE_OFF


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


# Targets


async def test_target_not_shown(
    hass: HomeAssistant,
    sources: None,
    heater: FakeClimate,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A target the source does not show is a problem after 30 s at least."""
    events = async_capture_events(hass, EVENT_PROBLEM)
    await _setup(hass, _entry())
    await _climate(hass, SERVICE_SET_HVAC_MODE, **{ATTR_HVAC_MODE: HVACMode.HEAT})
    await _wait_seconds(hass, freezer, 13)
    _silent(heater)

    await _climate(hass, SERVICE_SET_TEMPERATURE, **{ATTR_TEMPERATURE: 23.0})
    # Duration 0, but a source may take a while to show it.
    await _wait_seconds(hass, freezer, 29)
    assert not [p for p in _problems(hass) if p["type"] == "target"]

    await _wait_seconds(hass, freezer, 1)
    target = {
        "type": "target",
        "entity_id": HEATER,
        "mode": "heat",
        "attribute": "temperature",
        "expected": 23.0,
        "actual": 20.0,
    }
    assert hass.states.get(MONITORING).state == STATE_ON
    assert target in _problems(hass)
    assert (
        "Living room: climate.heater (heat) shows temperature 20.0 instead of 23.0"
        in caplog.text
    )
    started = [e.data for e in events if e.data["problem"]["type"] == "target"]
    assert started == [
        {
            "entry_id": "01JTESTENTRY000000000000000",
            "name": "Living room",
            "entity_id": MONITORING,
            "status": "started",
            "message": "climate.heater (heat) shows temperature 20.0 instead of 23.0 for 0 min",
            "problem": target,
        }
    ]

    # The device shows it at last.
    await _show_target(hass, heater, 23.0)
    assert target not in _problems(hass)
    assert "Living room: climate.heater shows the temperature sent to it again" in caplog.text
    assert [e.data["status"] for e in events if e.data["problem"]["type"] == "target"] == [
        "started",
        "ended",
    ]


async def test_target_problem_after_duration(
    hass: HomeAssistant,
    sources: None,
    heater: FakeClimate,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A target the source does not show waits for the monitoring duration."""
    await _setup(hass, _entry(**{CONF_MONITORING_DURATION: 2}))
    await _climate(hass, SERVICE_SET_HVAC_MODE, **{ATTR_HVAC_MODE: HVACMode.HEAT})
    await _wait_seconds(hass, freezer, 13)
    _silent(heater)
    await _climate(hass, SERVICE_SET_TEMPERATURE, **{ATTR_TEMPERATURE: 23.0})

    await _wait(hass, freezer, 1.9)
    assert hass.states.get(MONITORING).state == STATE_OFF
    await _wait(hass, freezer, 0.1)
    assert hass.states.get(MONITORING).state == STATE_ON


async def test_target_not_judged_during_settle_or_off(
    hass: HomeAssistant,
    sources: None,
    heater: FakeClimate,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A source may show its own target during the settle time; off, nothing is judged."""
    await _setup(hass, _entry())
    await _climate(hass, SERVICE_SET_HVAC_MODE, **{ATTR_HVAC_MODE: HVACMode.HEAT})
    _silent(heater)
    await _climate(hass, SERVICE_SET_TEMPERATURE, **{ATTR_TEMPERATURE: 23.0})
    entity = hass.data[CLIMATE_DOMAIN].get_entity(ENTITY_ID)
    assert entity._targets.settling
    assert entity._targets.mismatches() == []

    await _wait_seconds(hass, freezer, 12)
    assert len(entity._targets.mismatches()) == 1

    await _climate(hass, SERVICE_SET_HVAC_MODE, **{ATTR_HVAC_MODE: HVACMode.OFF})
    assert entity._targets.mismatches() == []
    await _wait(hass, freezer, 1)
    assert hass.states.get(MONITORING).state == STATE_OFF


async def test_target_taken_outside_limits_is_no_problem(
    hass: HomeAssistant,
    sources: None,
    heater: FakeClimate,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A target set on the source above the limit is taken as is: no problem."""
    await _setup(hass, _entry(**{CONF_MAX_TEMP: 25}))
    await _climate(hass, SERVICE_SET_HVAC_MODE, **{ATTR_HVAC_MODE: HVACMode.HEAT})
    await _wait_seconds(hass, freezer, 13)

    await _show_target(hass, heater, 28.0)
    await _wait(hass, freezer, 1)

    assert not [p for p in _problems(hass) if p["type"] == "target"]


# Exclusivity


async def test_stuck_source(
    hass: HomeAssistant,
    sources: None,
    heater: FakeClimate,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A source that does not turn off is a problem at once, until it stops."""
    events = async_capture_events(hass, EVENT_PROBLEM)
    await _setup(hass, _entry(**{CONF_MONITORING_DURATION: 15}))
    await _climate(hass, SERVICE_SET_HVAC_MODE, **{ATTR_HVAC_MODE: HVACMode.HEAT})
    heater.failing_modes = {HVACMode.OFF}

    await _climate(hass, SERVICE_SET_HVAC_MODE, **{ATTR_HVAC_MODE: HVACMode.COOL})

    stuck = {
        "type": "exclusivity",
        "entity_id": HEATER,
        "mode": "heat",
        "running": AC,
        "error": "climate.heater cannot be reached",
    }
    assert hass.states.get(MONITORING).state == STATE_ON
    assert _problems(hass) == [stuck]
    assert (
        "Living room: climate.heater (heat) does not turn off while climate.ac runs"
        " (climate.heater cannot be reached); tried again every minute"
    ) in caplog.text
    assert [(e.data["status"], e.data["problem"]) for e in events] == [("started", stuck)]

    heater.failing_modes = set()
    await _wait(hass, freezer, 1.1)

    assert hass.states.get(MONITORING).state == STATE_OFF
    assert "Living room: climate.heater no longer runs along with another source" in caplog.text
    assert [e.data["status"] for e in events] == ["started", "ended"]
