"""Spec §1.3.5.4 Fan and swing values (ENT-FANV), and §1.3.6 stored data (ENT-DATA).

fan_mode, swing_mode and swing_horizontal_mode are handled the same way:
the main tests use fan, one test runs over the three.
"""

from __future__ import annotations

from typing import Any

import pytest

from dev.spec.harness import Bench, yaml_entry

spec = pytest.mark.spec

HEATER = "climate.heater"
AIRCON = "climate.aircon"
DRYER = "climate.dryer"
ROOM = "sensor.room"
SETTLE = 12


def ac(bench: Bench) -> Any:
    return bench.ac("Living room")


def fan(bench: Bench) -> Any:
    return ac(bench).attr("fan_mode")


async def start(bench: Bench, *, dryer: bool = False, **options: Any) -> tuple[Any, Any]:
    """Heater fan low/high (at low), aircon fan Auto/Low/High (at Auto)."""
    heater = bench.device(HEATER, ["heat"], fan_modes=["low", "high"], fan_mode="low")
    aircon = bench.device(AIRCON, ["cool"], fan_modes=["Auto", "Low", "High"], fan_mode="Auto")
    entry = {"heat_entity": HEATER, "cool_entity": AIRCON}
    if dryer:
        bench.device(DRYER, ["dry"], fan_modes=["low", "high"], fan_mode="low")
        entry["dry_entity"] = DRYER
    await bench.start([yaml_entry("Living room", **entry, **options)])
    return heater, aircon


async def mode(bench: Bench, hvac_mode: str) -> None:
    """The user asks for a mode; the settle time passes."""
    await ac(bench).set_hvac_mode(hvac_mode)
    await bench.advance(SETTLE + 1)


# --- ENT-FANV-1, ENT-FANV-2, ENT-FANV-6: a memory per mode -------------------------------------------------


@spec("ENT-FANV-1", "ENT-FANV-6", "ENT-FANV-8", "ENT-SET-2")
async def test_ent_fanv_1_each_mode_finds_its_value(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await mode(bench, "heat")
    assert fan(bench) == "low"  # empty memory: the value of the heater
    await ac(bench).set_fan_mode("high")
    await mode(bench, "cool")
    assert fan(bench) == "Auto"
    await heater.set(fan_mode="low")  # changed while the heater is not used: ignored
    heater.clear_calls()
    await mode(bench, "heat")
    assert heater.values_asked("fan_mode") == ["high"]
    assert fan(bench) == "high"
    assert "high" in str(ac(bench).attr("saved_settings"))


@spec("ENT-FANV-1", "ENT-DATA-1")
async def test_ent_fanv_1_memory_saved_across_restarts(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await mode(bench, "heat")
    await ac(bench).set_fan_mode("high")
    await mode(bench, "cool")
    await bench.stop()
    heater.fan_mode = "low"
    await bench.start(bench.yaml)
    heater.clear_calls()
    await mode(bench, "heat")
    assert heater.values_asked("fan_mode") == ["high"]


@spec("ENT-FANV-1", "ENT-FANV-4", "ENT-FAN-1")
@pytest.mark.parametrize(
    ("setting", "options"),
    [
        pytest.param("fan_mode", ["low", "high"], id="fan"),
        pytest.param("swing_mode", ["off", "on"], id="swing"),
        pytest.param("swing_horizontal_mode", ["off", "on"], id="horizontal swing"),
    ],
)
async def test_ent_fanv_1_the_three_settings(
    bench: Bench, setting: str, options: list[str]
) -> None:
    plural = {"fan_mode": "fan_modes", "swing_mode": "swing_modes",
              "swing_horizontal_mode": "swing_horizontal_modes"}[setting]
    heater = bench.device(HEATER, ["heat"], **{plural: options, setting: options[0]})
    bench.device(AIRCON, ["cool"])
    await bench.start([yaml_entry("Living room", heat_entity=HEATER, cool_entity=AIRCON)])
    await mode(bench, "heat")
    assert ac(bench).attr(plural) == options
    assert ac(bench).attr(setting) == options[0]
    await getattr(ac(bench), f"set_{setting}")(options[1])
    assert heater.values_asked(setting) == [options[1]]
    await mode(bench, "cool")
    await heater.set(**{setting: options[0]})
    await mode(bench, "heat")
    assert heater.values_asked(setting) == [options[1], options[1]]


@spec("ENT-FANV-2", "ENT-FAN-5", "ENT-FAN-6")
async def test_ent_fanv_2_synchronized_modes_share_their_value(bench: Bench) -> None:
    """Shared options low/high, written as heat writes them; the aircon gets its own spelling."""
    heater, aircon = await start(bench, sync_modes=["heat", "cool"])
    await mode(bench, "heat")
    await ac(bench).set_fan_mode("high")
    await mode(bench, "cool")
    assert aircon.values_asked("fan_mode") == ["High"]
    assert fan(bench) == "High"


@spec("ENT-FANV-2", "ENT-FAN-8")
async def test_ent_fanv_2_bi_source_sync_shares_the_two_phases(bench: Bench) -> None:
    sensor = bench.sensor(ROOM, 21.0)
    heater, aircon = await start(bench, bi_source_sync=True, temperature_sensor=ROOM)
    await ac(bench).set_temperature(target_temp_low=19.0, target_temp_high=24.0)
    await mode(bench, "heat_cool")  # phase heat
    await ac(bench).set_fan_mode("high")
    await sensor.set(26.0)  # phase cool
    await bench.advance(SETTLE + 1)
    assert aircon.values_asked("fan_mode")[-1] == "High"


# --- ENT-FANV-3: what a memory holds -------------------------------------------------------------------


@spec("ENT-FANV-3", "ENT-FAN-3")
async def test_ent_fanv_3_value_not_shared_is_not_remembered(bench: Bench) -> None:
    heater, aircon = await start(bench, sync_modes=["heat", "cool"])
    await mode(bench, "heat")
    await ac(bench).set_fan_mode("high")
    await mode(bench, "cool")
    assert ac(bench).attr("fan_modes") == ["Auto", "Low", "High"]  # all of cool
    await ac(bench).set_fan_mode("Auto")  # offered by cool only
    assert aircon.values_asked("fan_mode")[-1] == "Auto"
    assert fan(bench) == "Auto"
    await mode(bench, "heat")
    await mode(bench, "cool")
    assert aircon.values_asked("fan_mode")[-1] == "High"  # the shared memory kept high


@spec("ENT-FANV-3", "ENT-CAP-7")
async def test_ent_fanv_3_value_no_longer_offered_is_removed(bench: Bench) -> None:
    """The current mode no longer offers it: the value of the device is taken."""
    heater, _ = await start(bench, removal_confirmation_timer=0)
    await mode(bench, "heat")
    await ac(bench).set_fan_mode("high")
    heater.clear_calls()
    await heater.set(fan_modes=["low", "medium"], fan_mode="medium")
    assert fan(bench) == "medium"
    assert heater.values_asked("fan_mode") == []


# --- ENT-FANV-4, ENT-FANV-5: how the memory is filled ------------------------------------------------------


@spec("ENT-FANV-4", "SRC-SET-11")
async def test_ent_fanv_4_value_taken_from_the_active_source(bench: Bench) -> None:
    heater, _ = await start(bench)
    await mode(bench, "heat")
    await heater.set(fan_mode="high")
    assert fan(bench) == "high"
    await mode(bench, "cool")
    await heater.set(fan_mode="low")
    heater.clear_calls()
    await mode(bench, "heat")
    assert heater.values_asked("fan_mode") == ["high"]


@spec("ENT-FANV-5", "ENT-CAP-6", "ENT-CAP-7")
async def test_ent_fanv_5_remembered_value_sent_at_the_discovery(bench: Bench) -> None:
    """Cool never run: at its discovery, the shared value is sent, not the aircon's taken."""
    heater, aircon = await start(bench, sync_modes=["heat", "cool"])
    await mode(bench, "heat")
    await ac(bench).set_fan_mode("high")
    await mode(bench, "cool")
    assert aircon.values_asked("fan_mode") == ["High"]
    assert fan(bench) == "High"


@spec("ENT-FANV-5", "SRC-SET-12")
async def test_ent_fanv_5_empty_memory_takes_the_value_of_the_source(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await mode(bench, "cool")
    assert fan(bench) == "Auto"
    assert aircon.values_asked("fan_mode") == []


# --- ENT-FANV-7, ENT-FANV-8, ENT-FANV-9: sent, shown ---------------------------------------------------------


@spec("ENT-FANV-7", "ENT-SET-1")
async def test_ent_fanv_7_value_set_while_waiting_sent_on_return(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await mode(bench, "heat")
    await heater.set(available=False)
    await ac(bench).set_fan_mode("high")
    assert fan(bench) == "high"
    await heater.set(available=True)
    assert heater.values_asked("fan_mode")[-1] == "high"


@spec("ENT-FANV-8", "SRC-SET-10")
async def test_ent_fanv_8_setting_not_applied_keeps_the_value_of_the_entity(bench: Bench) -> None:
    heater, _ = await start(bench)
    await mode(bench, "heat")
    heater.ignore = {"set_fan_mode"}
    await ac(bench).set_fan_mode("high")
    await bench.advance(60)
    assert heater.fan_mode == "low"
    assert fan(bench) == "high"


@spec("ENT-FANV-8", "ENT-FAN-3")
async def test_ent_fanv_8_off_shows_none_unless_every_mode_is_synchronized(bench: Bench) -> None:
    await start(bench)
    await mode(bench, "heat")
    await ac(bench).set_hvac_mode("off")
    assert fan(bench) is None


@spec("ENT-FANV-9", "ENT-FANV-8", "ENT-FAN-3")
async def test_ent_fanv_9_value_set_in_off_with_every_mode_synchronized(bench: Bench) -> None:
    heater, aircon = await start(bench, sync_modes=["heat", "cool"])
    await mode(bench, "heat")
    await ac(bench).set_hvac_mode("off")
    assert ac(bench).attr("fan_modes") == ["low", "high"]
    await ac(bench).set_fan_mode("high")
    assert fan(bench) == "high"
    heater.clear_calls()
    await mode(bench, "heat")
    assert heater.values_asked("fan_mode") == ["high"]


# --- ENT-DATA-1 --------------------------------------------------------------------------------------


@spec("ENT-DATA-1", "ENT-FANV-1", "ENT-INIT-4")
async def test_ent_data_1_memory_of_a_mode_no_longer_configured_is_dropped(bench: Bench) -> None:
    bench.device(HEATER, ["heat"])
    dryer = bench.device(DRYER, ["dry"], fan_modes=["low", "high"], fan_mode="low")
    await bench.start()
    await bench.create_entry(name="Living room", heat_entity=HEATER, dry_entity=DRYER)
    await mode(bench, "dry")
    await ac(bench).set_fan_mode("high")
    await ac(bench).set_hvac_mode("off")
    await bench.change_options("Living room", dry_entity=None)
    await bench.change_options("Living room", dry_entity=DRYER)
    await dryer.set(fan_mode="low")
    dryer.clear_calls()
    await mode(bench, "dry")
    assert dryer.values_asked("fan_mode") == []  # nothing remembered: its value is taken
    assert fan(bench) == "low"


@spec("ENT-FANV-3", "ENT-FANV-5", "SRC-DATA-4", "ENT-CAP-7")
async def test_ent_fanv_3_value_removed_while_the_mode_is_not_current(bench: Bench) -> None:
    """While Home Assistant was stopped, the dryer lost its high speed. At the start (INIT,
    no current mode), high is removed from the memory of dry, nothing is sent. Dry resumes
    with an empty memory: nothing shown until the dryer reports a speed (ENT-FANV-8)."""
    dryer = bench.device(DRYER, ["dry"], fan_modes=["low", "high"], fan_mode="low")
    await bench.start(
        [yaml_entry("Living room", dry_entity=DRYER, removal_confirmation_timer=0)]
    )
    await mode(bench, "dry")
    await ac(bench).set_fan_mode("high")
    assert dryer.fan_mode == "high"
    await bench.stop()
    dryer.fan_modes = ["low", "medium"]
    dryer.fan_mode = "medium"
    dryer.clear_calls()
    await bench.start(bench.yaml)
    assert ac(bench).state == "dry"
    assert fan(bench) is None
    assert dryer.values_asked("fan_mode") == []
    await dryer.set(fan_mode="low")
    assert fan(bench) == "low"
    assert "high" not in str(ac(bench).attr("saved_settings"))


@spec("ENT-FANV-3", "ENT-FAN-6", "SRC-DATA-1")
async def test_ent_fanv_3_value_still_offered_by_the_current_mode(bench: Bench) -> None:
    """Heat and cool share their fan. The aircon, asked off, keeps running cool and loses
    its high speed: high is no longer shared, so no longer remembered; heat still offers
    it: it stays the value shown, nothing is sent."""
    heater, aircon = await start(
        bench, sync_modes=["heat", "cool"], removal_confirmation_timer=0
    )
    heater.fan_modes = aircon.fan_modes = ["low", "high"]
    heater.fan_mode = aircon.fan_mode = "low"
    await mode(bench, "cool")
    await ac(bench).set_fan_mode("high")
    aircon.obey = False  # it will not turn off
    await mode(bench, "heat")
    assert fan(bench) == "high"
    heater.clear_calls()
    await aircon.set(fan_modes=["low"], fan_mode="low")  # still in cool: read
    assert fan(bench) == "high"
    assert heater.values_asked("fan_mode") == []
    assert "high" not in str(ac(bench).attr("saved_settings"))
