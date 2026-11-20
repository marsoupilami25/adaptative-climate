"""Spec §1.1.4 End of an entry: unload (END-1), next start (END-2), deletion (END-3)."""

from __future__ import annotations

import pytest

from dev.spec.harness import Bench, yaml_entry

spec = pytest.mark.spec

HEATER = "climate.heater"
NOT_LOADED = "climate.not_loaded"


async def heating(bench: Bench, **options: object) -> None:
    """An entry in heat on its heater."""
    bench.device(HEATER, ["heat"])
    await bench.start([yaml_entry("Living room", heat_entity=HEATER, **options)])
    await bench.ac("Living room").set_hvac_mode("heat")
    assert bench.devices[HEATER].hvac_mode == "heat"


async def mode_not_offered(bench: Bench) -> None:
    """A heater seen without heat: its source is UNUSABLE, a Repairs issue is raised."""
    bench.device(HEATER, ["heat"], present=False)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    heater = bench.devices[HEATER]
    heater.hvac_modes = ["off", "cool"]
    await heater.appear()
    assert len(bench.issues()) == 1


# --- END-1 Unload ----------------------------------------------------------------------------


@spec("END-1")
async def test_end_1_source_entities_are_left_as_they_are(bench: Bench) -> None:
    await heating(bench)
    heater = bench.devices[HEATER]
    heater.clear_calls()
    await bench.unload("Living room")
    await bench.advance(60)
    assert heater.calls == []
    assert heater.hvac_mode == "heat"


@spec("END-1", "MON-SENS-4")
async def test_end_1_entities_become_unavailable(bench: Bench) -> None:
    await heating(bench)
    await bench.unload("Living room")
    ac = bench.ac("Living room")
    assert ac.state == "unavailable"
    assert ac.monitoring_sources.state == "unavailable"
    assert ac.monitoring_temperatures.state == "unavailable"


@spec("END-1")
async def test_end_1_running_requests_are_dropped(bench: Bench) -> None:
    """A device that does not obey: no retry after the unload."""
    bench.device(HEATER, ["heat"], obey=False)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    await bench.ac("Living room").set_hvac_mode("heat")
    heater = bench.devices[HEATER]
    assert heater.modes_asked() == ["heat"]
    heater.clear_calls()
    await bench.unload("Living room")
    await bench.advance(700, step=5)
    assert heater.calls == []


@spec("END-1", "ENT-HVAC-5")
async def test_end_1_repairs_issues_are_removed(bench: Bench) -> None:
    await mode_not_offered(bench)
    await bench.unload("Living room")
    assert bench.issues() == []


@spec("END-1", "MON-LIFE-2")
async def test_end_1_no_monitoring_event_on_unload(bench: Bench) -> None:
    """A problem reported ends without an `ended` event."""
    await bench.start(
        [yaml_entry("Living room", heat_entity=NOT_LOADED, monitoring_delay_timer=10)]
    )
    await bench.advance(11)
    assert bench.ac("Living room").monitoring_sources.state == "on"
    assert bench.problem_events(status="started")
    await bench.unload("Living room")
    await bench.advance(60)
    assert bench.problem_events(status="ended") == []


# --- END-2 Next start --------------------------------------------------------------------------


@spec("END-2", "SRC-STATE-10")
async def test_end_2_sources_are_resynchronized(bench: Bench) -> None:
    """Home Assistant wins: what changed on the device while it was stopped is undone."""
    await heating(bench)
    await bench.ac("Living room").set_temperature(temperature=22.0)
    await bench.advance(15)
    heater = bench.devices[HEATER]
    assert heater.temperature == 22.0
    await bench.stop()
    heater.hvac_mode = "off"
    heater.temperature = 25.0
    heater.clear_calls()
    await bench.start(bench.yaml)
    assert heater.modes_asked() == ["heat"]
    await bench.advance(15)
    assert heater.temperature == 22.0
    assert bench.ac("Living room").state == "heat"


@spec("END-2", "MON-SEND-3", "MON-LIFE-1")
async def test_end_2_monitoring_starts_empty(bench: Bench) -> None:
    """A problem still there is reported again after its whole delay."""
    await bench.start(
        [yaml_entry("Living room", heat_entity=NOT_LOADED, monitoring_delay_timer=60)]
    )
    await bench.advance(61)
    sensor = bench.ac("Living room").monitoring_sources
    assert sensor.state == "on"
    await bench.restart()
    sensor = bench.ac("Living room").monitoring_sources
    assert sensor.state == "off"
    await bench.advance(59)
    assert sensor.state == "off"
    await bench.advance(2)
    assert sensor.state == "on"
    assert len(bench.problem_events(status="started")) == 2


@spec("END-2", "ENT-HVAC-5")
async def test_end_2_repairs_issue_raised_again_if_its_cause_is_still_there(bench: Bench) -> None:
    await mode_not_offered(bench)
    await bench.restart()
    assert len(bench.issues()) == 1


@spec("END-2", "ENT-HVAC-5")
async def test_end_2_no_repairs_issue_once_its_cause_is_gone(bench: Bench) -> None:
    await mode_not_offered(bench)
    await bench.stop()
    bench.devices[HEATER].hvac_modes = ["off", "heat"]
    await bench.start(bench.yaml)
    assert bench.issues() == []


# --- END-3 Deletion ---------------------------------------------------------------------------


@spec("END-3")
async def test_end_3_stored_data_is_erased(bench: Bench) -> None:
    await heating(bench)
    entry_id = bench.entry("Living room").entry_id
    await bench.advance(60)  # the stored data is written
    assert bench.stored_about(entry_id), "nothing stored: the test proves nothing"
    await bench.delete("Living room")
    await bench.advance(60)
    assert bench.stored_about(entry_id) == []


@spec("END-3")
async def test_end_3_source_entities_are_left_as_they_are(bench: Bench) -> None:
    await heating(bench)
    heater = bench.devices[HEATER]
    heater.clear_calls()
    await bench.delete("Living room")
    await bench.advance(60)
    assert heater.calls == []
    assert heater.hvac_mode == "heat"
    assert not bench.ac("Living room").exists


@spec("END-3")
async def test_end_3_problems_and_issues_are_removed(bench: Bench) -> None:
    await mode_not_offered(bench)
    await bench.delete("Living room")
    assert bench.issues() == []
    assert not bench.ac("Living room").monitoring_sources.exists


@spec("END-3", "ENT-INIT-1")
async def test_end_3_entry_created_again_starts_from_zero(bench: Bench) -> None:
    """Nothing is kept: a new entry of the same name has no stored mode."""
    await heating(bench)
    await bench.delete("Living room")
    heater = bench.devices[HEATER]
    heater.clear_calls()
    result = await bench.create_entry(name="Living room", heat_entity=HEATER)
    assert result["type"] == "create_entry"
    assert bench.ac("Living room").state == "off"
    assert heater.modes_asked() == ["off"]
