"""Spec §1.3.5.2 External sensors (ENT-EXT, CFG-SENS-2)."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from dev.spec.harness import Bench, errors_logged, warnings_logged, yaml_entry

spec = pytest.mark.spec

HEATER = "climate.heater"
PUMP = "climate.heat_pump"
ROOM = "sensor.room"
TRV = "number.heater_external"


def ac(bench: Bench) -> Any:
    return bench.ac("Living room")


async def start(
    bench: Bench, room: Any = 21.0, *, external: dict[str, Any] | None = None, **options: Any
) -> tuple[Any, Any, Any]:
    """A heater whose valve takes an external temperature (5–35 °C, step 0.5)."""
    heater = bench.device(HEATER, ["heat"], current_temperature=25.0)
    sensor = bench.sensor(ROOM, room)
    trv = bench.external(TRV, **{"minimum": 5.0, "maximum": 35.0, "step": 0.5, **(external or {})})
    await bench.start(
        [
            yaml_entry(
                "Living room",
                heat_entity=HEATER,
                temperature_sensor=ROOM,
                heat_external_sensor=TRV,
                **options,
            )
        ]
    )
    return heater, sensor, trv


# --- ENT-EXT-1: writes -------------------------------------------------------------------------


@spec("ENT-EXT-1", "ENT-EXT-2")
async def test_ent_ext_1_written_at_start_rounded_to_its_step(bench: Bench) -> None:
    _, _, trv = await start(bench, 21.3)
    assert trv.values_written == [21.5]


@spec("ENT-EXT-1")
async def test_ent_ext_1_written_on_every_change_even_off(bench: Bench) -> None:
    _, sensor, trv = await start(bench, 21.0)
    assert ac(bench).state == "off"
    await sensor.set(22.0)
    await sensor.set(22.5)
    assert trv.values_written == [21.0, 22.0, 22.5]


@spec("ENT-EXT-1", "CFG-SENS-4")
async def test_ent_ext_1_one_entity_for_several_modes_written_once(bench: Bench) -> None:
    bench.device(PUMP, ["heat", "cool"])
    sensor = bench.sensor(ROOM, 21.0)
    trv = bench.external(TRV, minimum=5.0, maximum=35.0, step=0.5)
    await bench.start(
        [
            yaml_entry(
                "Living room",
                heat_entity=PUMP,
                cool_entity=PUMP,
                temperature_sensor=ROOM,
                heat_external_sensor=TRV,
                cool_external_sensor=TRV,
            )
        ]
    )
    await sensor.set(22.0)
    assert trv.values_written == [21.0, 22.0]


# --- ENT-EXT-2: conversion, range, errors ---------------------------------------------------------------


@spec("ENT-EXT-2")
async def test_ent_ext_2_converted_to_its_unit(bench: Bench) -> None:
    _, _, trv = await start(
        bench, 21.3, external={"unit": "°F", "minimum": 40.0, "maximum": 95.0, "step": 1.0}
    )
    assert trv.values_written == [70.0]


@spec("ENT-EXT-2")
async def test_ent_ext_2_out_of_its_range_not_written(
    bench: Bench, caplog: pytest.LogCaptureFixture
) -> None:
    """A warning when the value leaves the range, not again while out; back: info."""
    _, sensor, trv = await start(bench, 21.0, external={"maximum": 25.0})
    await sensor.set(26.0)
    await sensor.set(27.0)
    assert trv.values_written == [21.0]
    assert len(warnings_logged(caplog, TRV)) == 1
    await sensor.set(24.0)
    assert trv.values_written == [21.0, 24.0]
    infos = [r for r in caplog.records if r.levelno == logging.INFO and TRV in r.getMessage()]
    assert infos


@spec("ENT-EXT-2")
async def test_ent_ext_2_write_error_is_logged(
    bench: Bench, caplog: pytest.LogCaptureFixture
) -> None:
    _, sensor, trv = await start(bench, 21.0, external={"fail": True})
    await sensor.set(22.0)
    assert errors_logged(caplog, TRV) or warnings_logged(caplog, TRV)


@spec("ENT-EXT-2", "ENT-EXT-6")
async def test_ent_ext_2_not_written_while_not_usable(bench: Bench) -> None:
    _, sensor, trv = await start(bench, 21.0, external={"available": False})
    await sensor.set(22.0)
    assert trv.values_written == []
    await trv.set(available=True)  # usable again: the current value at once
    assert trv.values_written == [22.0]


@spec("ENT-EXT-6")
async def test_ent_ext_6_entity_appearing_gets_the_value(bench: Bench) -> None:
    _, _, trv = await start(bench, 21.0, external={"present": False})
    assert trv.values_written == []
    await trv.set(present=True)
    assert trv.values_written == [21.0]


# --- ENT-EXT-3: offset 0 ---------------------------------------------------------------------------


@spec("ENT-EXT-3", "CFG-SENS-2")
async def test_ent_ext_3_reading_of_the_source_without_offset(bench: Bench) -> None:
    """The heater reads 25 °C: with an external sensor, its offset is 0."""
    heater, sensor, _ = await start(bench, 21.0)
    await ac(bench).set_hvac_mode("heat")
    await sensor.set("unavailable")  # the reference falls back to the heater
    assert ac(bench).attr("current_temperature") == 25.0


# --- ENT-EXT-4, ENT-EXT-5: periodic rewrite, invalid sensor --------------------------------------------------


@spec("ENT-EXT-4")
async def test_ent_ext_4_written_again_every_resend_timer(bench: Bench) -> None:
    _, _, trv = await start(bench, 21.0, external_sensor_resend_timer=60)
    await bench.advance(59)
    assert trv.values_written == [21.0]
    await bench.advance(2)
    assert trv.values_written == [21.0, 21.0]
    await bench.advance(60)
    assert trv.values_written == [21.0, 21.0, 21.0]


@spec("ENT-EXT-5", "ENT-EXT-4")
async def test_ent_ext_5_invalid_sensor_stops_the_writes(bench: Bench) -> None:
    _, sensor, trv = await start(bench, 21.0, external_sensor_resend_timer=60)
    await sensor.set("unavailable")
    await bench.advance(200)
    assert trv.values_written == [21.0]
    await sensor.set(22.0)
    assert trv.values_written == [21.0, 22.0]


@spec("ENT-EXT-5", "ENT-EXT-1")
async def test_ent_ext_5_invalid_at_start(bench: Bench) -> None:
    _, sensor, trv = await start(bench, "unknown")
    assert trv.values_written == []
    await sensor.set(21.0)
    assert trv.values_written == [21.0]


@spec("ENT-EXT-1")
async def test_ent_ext_1_a_change_of_the_sensor_without_new_value(bench: Bench) -> None:
    """Only its attributes change: no new value, nothing written (T=>AC_temperature, §1.1.2)."""
    _, sensor, trv = await start(bench, 21.0)
    await sensor.set(device_class=None)
    assert trv.values_written == [21.0]
