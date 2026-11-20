"""Spec §5 Sequence examples, replayed end to end.

§5 is informative: each test checks what Home Assistant and the devices see
of a sequence, and carries the rules that make it so (EXEC-1, EXEC-2 for the
order of the events).
"""

from __future__ import annotations

from typing import Any

import pytest

from dev.spec.harness import Bench, yaml_entry

spec = pytest.mark.spec

AIRCON = "climate.aircon"
RADIATOR = "climate.radiator"
ROOM = "sensor.room"
SETTLE = 12


def ac(bench: Bench) -> Any:
    return bench.ac("Living room")


def services(device: Any) -> list[str]:
    return [call.service for call in device.calls]


async def aircon_off_with_memory(bench: Bench, *, swing: bool = False, **device: Any) -> Any:
    """An AC unit, cool discovered; the entity OFF, its memory for cool 24 / fan low."""
    values: dict[str, Any] = {"fan_modes": ["low", "auto"], "fan_mode": "auto", **device}
    if swing:
        values.update(swing_modes=["off", "vertical"], swing_mode="off")
    aircon = bench.device(AIRCON, ["cool", "dry"], **values)
    await bench.start([yaml_entry("Living room", cool_entity=AIRCON, dry_entity=AIRCON)])
    await aircon.set(hvac_mode="cool")  # cool discovered, on the device
    await ac(bench).set_temperature(temperature=24.0)
    await ac(bench).set_fan_mode("low")
    await aircon.set(hvac_mode="off")
    await aircon.set(temperature=20.0, fan_mode="auto")  # while off: not followed
    assert ac(bench).state == "off"
    aircon.clear_calls()
    return aircon


@spec("EXEC-1", "EXEC-2", "SRC-STATE-3", "SRC-REQ-2", "SRC-SET-3", "SRC-SET-14")
async def test_5_1_mode_change_by_the_user(bench: Bench) -> None:
    """The mode first; the settings once the device shows it; nothing at the end of SETTLE."""
    aircon = await aircon_off_with_memory(bench)
    await ac(bench).set_hvac_mode("cool")
    assert services(aircon) == ["set_hvac_mode", "set_temperature", "set_fan_mode"]
    assert aircon.temperatures_asked() == [{"temperature": 24.0}]
    assert aircon.values_asked("fan_mode") == ["low"]
    await bench.advance(SETTLE + 1)
    assert len(aircon.calls) == 3
    assert ac(bench).state == "cool"


@spec("EXEC-1", "EXEC-2", "SRC-STATE-5", "SRC-SET-11", "SRC-SET-13", "ENT-STATE-5", "ENT-SEND-2")
async def test_5_2_takeover_on_the_device(bench: Bench) -> None:
    aircon = await aircon_off_with_memory(bench)
    await aircon.set(hvac_mode="dry")  # dry discovered
    await ac(bench).set_hvac_mode("cool")
    await bench.advance(SETTLE + 1)
    aircon.clear_calls()
    await aircon.set(hvac_mode="dry", temperature=22.0, fan_mode="auto")  # the remote
    assert ac(bench).state == "dry"
    assert ac(bench).attr("temperature") == 22.0
    assert ac(bench).attr("fan_mode") == "auto"
    await bench.advance(3)
    await aircon.set(fan_mode="low")  # no settle time after a takeover
    assert ac(bench).attr("fan_mode") == "low"
    assert aircon.calls == []


@spec("SRC-SET-5", "SRC-SET-6", "SRC-SET-14")
async def test_5_3_own_value_during_the_settle_time(bench: Bench) -> None:
    aircon = await aircon_off_with_memory(bench, swing=True)
    await ac(bench).set_hvac_mode("cool")
    assert aircon.values_asked("swing_mode") == []  # off already shown
    await aircon.set(swing_mode="vertical")  # the device puts back its own swing
    assert ac(bench).attr("swing_mode") == "off"
    await bench.advance(SETTLE + 1)
    assert aircon.values_asked("swing_mode") == ["off"]
    assert aircon.swing_mode == "off"


@spec("EXEC-1", "EXEC-2", "ENT-CAP-5", "ENT-CAP-6", "SRC-SET-12", "ENT-FANV-5", "ENT-SEND-2")
async def test_5_4_discovery_of_a_mode(bench: Bench) -> None:
    """T 22; the device starts in dry at 25 / fan auto: the fan is adopted, T is sent."""
    aircon = bench.device(
        AIRCON,
        ["cool", "dry"],
        temperature=22.0,
        profiles={"dry": {"temperature": 25.0, "fan_modes": ["low", "auto"], "fan_mode": "auto"}},
    )
    await bench.start([yaml_entry("Living room", cool_entity=AIRCON, dry_entity=AIRCON)])
    await ac(bench).set_hvac_mode("dry")
    assert aircon.modes_asked() == ["dry"]
    assert aircon.temperatures_asked() == [{"temperature": 22.0}]
    assert aircon.values_asked("fan_mode") == []
    assert ac(bench).attr("fan_mode") == "auto"
    assert ac(bench).attr("temperature") == 22.0


@spec("EXEC-1", "ENT-PHASE-2", "ENT-SEND-3", "ENT-TGT-8")
async def test_5_5_target_change_switches_the_phase(bench: Bench) -> None:
    """Phase heat at 22 °C (19 / 24); the user sets 17 / 20: cool. The radiator only gets off."""
    radiator = bench.device(RADIATOR, ["heat"])
    aircon = bench.device(AIRCON, ["cool"], temperature=25.0)
    sensor = bench.sensor(ROOM, 21.0)
    await bench.start(
        [yaml_entry("Living room", heat_entity=RADIATOR, cool_entity=AIRCON, temperature_sensor=ROOM)]
    )
    await ac(bench).set_temperature(target_temp_low=19.0, target_temp_high=24.0)
    await ac(bench).set_hvac_mode("heat_cool")
    await sensor.set(22.0)
    assert ac(bench).attr("phase") == "heat"
    radiator.clear_calls()
    aircon.clear_calls()
    await ac(bench).set_temperature(target_temp_low=17.0, target_temp_high=20.0)
    assert ac(bench).attr("phase") == "cool"
    assert services(aircon) == ["set_hvac_mode", "set_temperature"]
    assert aircon.temperatures_asked() == [{"temperature": 20.0}]
    assert radiator.modes_asked() == ["off"]
    assert radiator.temperatures_asked() == []


async def cooling_at_24_low(bench: Bench) -> Any:
    aircon = bench.device(AIRCON, ["cool"], fan_modes=["low", "auto"], fan_mode="auto")
    await bench.start([yaml_entry("Living room", cool_entity=AIRCON)])
    await ac(bench).set_hvac_mode("cool")
    await ac(bench).set_temperature(temperature=24.0)
    await ac(bench).set_fan_mode("low")
    await bench.advance(SETTLE + 1)
    assert (aircon.temperature, aircon.fan_mode) == (24.0, "low")
    return aircon


@spec("EXEC-4", "SRC-STATE-3", "SRC-SET-13", "ENT-SEND-2", "SRC-DATA-4")
async def test_5_6_restart_source_entity_already_loaded(bench: Bench) -> None:
    """The fan set to auto while stopped: only the fan is sent; no settle time."""
    aircon = await cooling_at_24_low(bench)
    await bench.stop()
    aircon.fan_mode = "auto"
    aircon.clear_calls()
    await bench.start(bench.yaml)
    assert services(aircon) == ["set_fan_mode"]
    assert aircon.values_asked("fan_mode") == ["low"]
    await bench.advance(3)
    await aircon.set(fan_mode="auto")  # a change 3 s later: a takeover
    assert ac(bench).attr("fan_mode") == "auto"


@spec("SRC-STATE-7", "SRC-STATE-10", "SRC-SET-1", "SRC-SET-13", "ENT-NOSRC-1")
async def test_5_7_restart_source_entity_loaded_later(bench: Bench) -> None:
    aircon = await cooling_at_24_low(bench)
    await bench.stop()
    aircon.present = False
    aircon.fan_mode = "auto"
    await bench.start(bench.yaml)
    assert ac(bench).state == "unavailable"  # NO_SOURCE
    aircon.clear_calls()
    await aircon.appear()
    assert ac(bench).state == "cool"
    assert aircon.modes_asked() == []
    assert set(aircon.values_asked("fan_mode")) == {"low"}
    await bench.advance(SETTLE + 1)
    assert aircon.fan_mode == "low"
    assert ac(bench).attr("fan_mode") == "low"


@spec("EXEC-1", "EXEC-2", "ENT-TGT-4", "ENT-TGT-9", "ENT-SEND-3", "ENT-CAP-7")
async def test_5_8_one_update_changes_a_capability_and_a_target(bench: Bench) -> None:
    """Range 16–30, high 27; the device limits to 26 and shows 25 at once: 25, nothing sent."""
    aircon = bench.device(AIRCON, ["cool"], min_temp=16.0, max_temp=30.0)
    await bench.start([yaml_entry("Living room", cool_entity=AIRCON)])
    await ac(bench).set_hvac_mode("cool")
    await ac(bench).set_temperature(temperature=27.0)
    await bench.advance(SETTLE + 1)
    aircon.clear_calls()
    await aircon.set(max_temp=26.0, temperature=25.0)
    assert ac(bench).attr("temperature") == 25.0
    assert ac(bench).attr("max_temp") == 26.0
    await bench.advance(60)
    assert aircon.temperatures_asked() == []
