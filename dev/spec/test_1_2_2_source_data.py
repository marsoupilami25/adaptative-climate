"""Spec §1.2.2 Source data storage management (SRC-DATA).

The capabilities a source stores are seen through the AC entity: the range
(`min_temp` / `max_temp`), the fan options, the temperature targets shown.
A heat pump serves heat and cool, with other capabilities in each mode.
"""

from __future__ import annotations

from typing import Any

import pytest

from dev.spec.harness import Bench, yaml_entry

spec = pytest.mark.spec

PUMP = "climate.heat_pump"
DRYER = "climate.dryer"
HEATER = "climate.heater"
AIRCON = "climate.aircon"


def ac(bench: Bench) -> Any:
    return bench.ac("Living room")


def shown_range(bench: Bench) -> tuple[float, float]:
    return (ac(bench).attr("min_temp"), ac(bench).attr("max_temp"))


def pump(bench: Bench, **values: Any) -> Any:
    """Heat at 10–30 °C, cool at 16–32 °C, both with fan low/high; 15–25 °C shown while off."""
    profiles = {
        "off": {"min_temp": 15.0, "max_temp": 25.0},
        "heat": {"min_temp": 10.0, "max_temp": 30.0, "fan_modes": ["low", "high"]},
        "cool": {"min_temp": 16.0, "max_temp": 32.0, "fan_modes": ["low", "high"]},
    }
    return bench.device(PUMP, ["heat", "cool"], fan_mode="low", profiles=profiles, **values)


async def start(bench: Bench, dryer: dict[str, Any] | None = None, **options: Any) -> None:
    """The pump for heat and cool, a dryer for dry (the entity keeps a source)."""
    bench.device(DRYER, ["dry"], **(dryer or {}))
    await bench.start(
        [yaml_entry("Living room", heat_entity=PUMP, cool_entity=PUMP, dry_entity=DRYER, **options)]
    )


# --- SRC-DATA-1, 2, 3: discovered as the modes are used ---------------------------------------------


@spec("SRC-DATA-1", "ENT-CAP-2", "ENT-RANGE-1", "ENT-RANGE-2")
async def test_src_data_1_capabilities_read_while_running_the_mode(bench: Bench) -> None:
    pump(bench)
    await start(bench, dryer={"min_temp": 18.0, "max_temp": 26.0})
    await ac(bench).set_hvac_mode("dry")
    await ac(bench).set_hvac_mode("heat")
    assert shown_range(bench) == (10.0, 30.0)
    await ac(bench).set_hvac_mode("cool")
    assert shown_range(bench) == (16.0, 32.0)
    # In OFF, the widest range of the modes (heat_cool, bi-source: 10–32)
    await ac(bench).set_hvac_mode("off")
    assert shown_range(bench) == (10.0, 32.0)


@spec("SRC-DATA-1", "SRC-DATA-2", "SRC-DATA-3", "ENT-CAP-3", "ENT-CAP-4")
async def test_src_data_2_nothing_read_while_off(bench: Bench) -> None:
    """Discovered (its modes available), no mode run: Home Assistant defaults."""
    pump(bench)
    await start(bench)
    assert ac(bench).attr("unavailable_modes") == []
    assert shown_range(bench) == (7.0, 35.0)
    assert not ac(bench).attr("fan_modes")


# --- SRC-DATA-4: restore -------------------------------------------------------------------------


@spec("SRC-DATA-4", "SRC-UNUS-1", "ENT-RANGE-2")
async def test_src_data_4_capabilities_restored(bench: Bench) -> None:
    device = pump(bench)
    await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await bench.stop()
    device.available = False
    await bench.start(bench.yaml)
    assert ac(bench).hvac_mode is None  # WAITING(heat)
    assert shown_range(bench) == (10.0, 30.0)


@spec("SRC-DATA-4", "SRC-DATA-6")
async def test_src_data_4_changes_while_stopped_are_seen_at_once(bench: Bench) -> None:
    device = pump(bench)
    await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await bench.stop()
    device.min_temp = 12.0
    device.profiles["heat"]["min_temp"] = 12.0
    await bench.start(bench.yaml)
    assert ac(bench).state == "heat"
    assert shown_range(bench) == (12.0, 30.0)


@spec("SRC-DATA-4", "SRC-DATA-10")
async def test_src_data_4_item_gone_while_stopped_waits_its_confirmation(bench: Bench) -> None:
    device = pump(bench)
    await start(bench)
    await ac(bench).set_hvac_mode("heat")
    assert ac(bench).attr("fan_modes") == ["low", "high"]
    await bench.stop()
    device.fan_modes = ["low"]
    device.profiles["heat"]["fan_modes"] = ["low"]
    await bench.start(bench.yaml)
    assert ac(bench).attr("fan_modes") == ["low", "high"]
    await bench.advance(61)
    assert ac(bench).attr("fan_modes") == ["low"]


@spec("SRC-DATA-4", "SRC-DATA-3", "SRC-UNDISC-1")
async def test_src_data_4_never_read_source_waits_for_its_first_usable_change(
    bench: Bench,
) -> None:
    heater = bench.device(HEATER, ["heat"], available=False)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    assert not ac(bench).available  # its only source is not discovered
    await heater.set(available=True)
    assert ac(bench).state == "off"
    assert ac(bench).attr("hvac_modes") == ["off", "heat"]


# --- SRC-DATA-6, SRC-DATA-12: updates -------------------------------------------------------------


@spec("SRC-DATA-6", "SRC-DATA-12", "ENT-CAP-7")
async def test_src_data_6_new_number_stored_at_once(bench: Bench) -> None:
    device = pump(bench)
    await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await device.set(max_temp=28.0)
    assert shown_range(bench) == (10.0, 28.0)


@spec("SRC-DATA-6", "SRC-DATA-10", "SRC-DATA-12")
async def test_src_data_6_lists_compared_item_by_item(bench: Bench) -> None:
    """[low, medium, high] shown as [low, medium, turbo]: turbo at once, high after 60 s."""
    device = pump(bench)
    device.profiles["heat"]["fan_modes"] = ["low", "medium", "high"]
    await start(bench)
    await ac(bench).set_hvac_mode("heat")
    assert ac(bench).attr("fan_modes") == ["low", "medium", "high"]
    await device.set(fan_modes=["low", "medium", "turbo"])
    assert set(ac(bench).attr("fan_modes")) == {"low", "medium", "high", "turbo"}
    await bench.advance(59)
    assert "high" in ac(bench).attr("fan_modes")
    await bench.advance(2)
    assert set(ac(bench).attr("fan_modes")) == {"low", "medium", "turbo"}


@spec("SRC-DATA-6", "SRC-DATA-10", "ENT-FAN-2")
async def test_src_data_6_feature_removed_after_its_confirmation(bench: Bench) -> None:
    device = pump(bench)
    await start(bench)
    await ac(bench).set_hvac_mode("heat")
    assert ac(bench).attr("fan_modes") == ["low", "high"]
    await device.set(fan_modes=None, fan_mode=None)  # the FAN_MODE feature is gone
    assert ac(bench).attr("fan_modes") == ["low", "high"]
    await bench.advance(61)
    assert not ac(bench).attr("fan_modes")


# --- SRC-DATA-8: low_high_seen --------------------------------------------------------------------


@spec("SRC-DATA-8", "ENT-FEAT-2")
async def test_src_data_8_low_high_once_shown_in_the_mode(bench: Bench) -> None:
    """A source with both features gets low/high once it showed them in that mode."""
    device = bench.device(
        PUMP,
        ["heat_cool"],
        single_target=True,
        range_target=True,
        temperature=21.0,
        target_temp_low=None,
        target_temp_high=None,
    )
    bench.device(DRYER, ["dry"])
    await bench.start([yaml_entry("Living room", heat_cool_entity=PUMP, dry_entity=DRYER)])
    await ac(bench).set_hvac_mode("heat_cool")
    assert ac(bench).attr("temperature") is not None
    assert ac(bench).attr("target_temp_low") is None
    await bench.advance(15)
    await device.set(target_temp_low=19.0, target_temp_high=24.0)
    assert ac(bench).attr("target_temp_low") is not None
    assert ac(bench).attr("temperature") is None
    # Never removed: after a restart, while the device no longer shows them
    await bench.stop()
    device.target_temp_low = device.target_temp_high = None
    await bench.start(bench.yaml)
    assert ac(bench).attr("target_temp_low") is not None


# --- SRC-DATA-9: data of a source entity no longer configured --------------------------------------------


@spec("SRC-DATA-9", "ENT-INIT-4")
async def test_src_data_9_source_entity_removed_loses_its_data(bench: Bench) -> None:
    # The heater shows 10–30 in heat, 7–35 while off
    heater = bench.device(
        HEATER, ["heat"],
        profiles={"heat": {"min_temp": 10.0, "max_temp": 30.0}, "off": {"min_temp": 7.0, "max_temp": 35.0}},
    )
    aircon = bench.device(AIRCON, ["cool"], min_temp=16.0, max_temp=32.0)
    await bench.start()
    result = await bench.create_entry(name="Living room", heat_entity=HEATER, cool_entity=AIRCON)
    assert result["type"] == "create_entry"
    await heater.set(hvac_mode="heat")
    await heater.set(hvac_mode="off")
    await aircon.set(hvac_mode="cool")
    await aircon.set(hvac_mode="off")
    assert shown_range(bench) == (10.0, 32.0)
    await bench.change_options("Living room", heat_entity=None)
    await bench.change_options("Living room", heat_entity=HEATER)
    # Heat is no longer discovered: its range is the provisional one again,
    # what the heater shows now, off (SRC-DATA-13): 7–35, the widest
    assert shown_range(bench) == (7.0, 35.0)


# --- SRC-DATA-13: provisional capabilities ---------------------------------------------------------


@spec("SRC-DATA-13", "ENT-CAP-4", "ENT-RANGE-1")
async def test_src_data_13_provisional_capabilities_follow_the_source_entity(bench: Bench) -> None:
    """Heat never run: the entity shows what the heater shows now, off; a change counts at
    once; not stored: read again at start."""
    heater = bench.device(HEATER, ["heat"], min_temp=10.0, max_temp=30.0)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    assert shown_range(bench) == (10.0, 30.0)
    await heater.set(max_temp=28.0)
    assert shown_range(bench) == (10.0, 28.0)
    await bench.stop()
    heater.max_temp = 26.0
    await bench.start(bench.yaml)
    assert shown_range(bench) == (10.0, 26.0)


@spec("SRC-DATA-13", "ENT-CAP-6", "ENT-FAN-2")
async def test_src_data_13_held_capability_found_again_meanwhile(bench: Bench) -> None:
    """The heater shows its fan a few seconds after it enters heat: held meanwhile, the
    fan never disappears."""
    heater = bench.device(HEATER, ["heat", "cool"], fan_modes=["low", "high"], fan_mode="low",
                          profiles={"heat": {"fan_modes": None}})
    await bench.start([yaml_entry("Living room", heat_entity=HEATER, cool_entity=HEATER)])
    await ac(bench).set_hvac_mode("heat")  # heat discovered without fan: the fan is held
    assert ac(bench).attr("fan_modes") == ["low", "high"]
    await bench.advance(5)
    await heater.set(fan_modes=["low", "high"])  # shown now: stored
    await bench.advance(60)
    assert ac(bench).attr("fan_modes") == ["low", "high"]


# --- SRC-DATA-10, SRC-DATA-11: removal confirmation ------------------------------------------------


async def heat_with_fan(bench: Bench, **options: Any) -> Any:
    device = pump(bench)
    await start(bench, **options)
    await ac(bench).set_hvac_mode("heat")
    return device


@spec("SRC-DATA-10")
async def test_src_data_10_shown_again_cancels_the_removal(bench: Bench) -> None:
    device = await heat_with_fan(bench)
    await device.set(fan_modes=["low"])
    await bench.advance(30)
    await device.set(fan_modes=["low", "high"])
    await bench.advance(60)
    assert ac(bench).attr("fan_modes") == ["low", "high"]


@spec("SRC-DATA-10")
async def test_src_data_10_other_changes_let_it_run(bench: Bench) -> None:
    device = await heat_with_fan(bench)
    await device.set(fan_modes=["low"])
    await bench.advance(30)
    await device.set(current_temperature=21.0)
    await bench.advance(31)
    assert ac(bench).attr("fan_modes") == ["low"]


@spec("SRC-DATA-10")
async def test_src_data_10_removed_at_once_with_a_zero_timer(bench: Bench) -> None:
    device = await heat_with_fan(bench, removal_confirmation_timer=0)
    await device.set(fan_modes=["low"])
    assert ac(bench).attr("fan_modes") == ["low"]


@spec("SRC-DATA-11")
async def test_src_data_11_leaving_the_mode_cancels_the_removal(bench: Bench) -> None:
    device = await heat_with_fan(bench)
    device.profiles["heat"]["fan_modes"] = ["low"]
    await device.set(fan_modes=["low"])  # in heat: its removal starts
    await bench.advance(30)
    await ac(bench).set_hvac_mode("cool")  # heat left: the removal is cancelled
    await bench.advance(60)
    await ac(bench).set_hvac_mode("heat")  # shown without high again: a new removal
    assert ac(bench).attr("fan_modes") == ["low", "high"]
    await bench.advance(61)
    assert ac(bench).attr("fan_modes") == ["low"]


@spec("SRC-DATA-11", "SRC-DATA-7")
async def test_src_data_11_not_usable_cancels_the_removal(bench: Bench) -> None:
    device = await heat_with_fan(bench)
    device.profiles["heat"]["fan_modes"] = ["low"]
    await device.set(fan_modes=["low"])
    await bench.advance(30)
    await device.set(available=False)
    await bench.advance(10)
    await device.set(available=True)  # back without high: a new removal
    await bench.advance(30)
    assert ac(bench).attr("fan_modes") == ["low", "high"]
    await bench.advance(31)
    assert ac(bench).attr("fan_modes") == ["low"]


@spec("SRC-DATA-6", "SRC-DATA-10", "ENT-STEP-1")
async def test_src_data_10_number_no_longer_shown(bench: Bench) -> None:
    """The step no longer shown: kept for the removal confirmation, then removed."""
    heater = bench.device(HEATER, ["heat"], target_temp_step=1.0)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    await ac(bench).set_hvac_mode("heat")
    assert ac(bench).attr("target_temp_step") == 1.0
    await heater.set(target_temp_step=None)
    await bench.advance(59)
    assert ac(bench).attr("target_temp_step") == 1.0
    await bench.advance(2)
    assert ac(bench).attr("target_temp_step") == 0.5
