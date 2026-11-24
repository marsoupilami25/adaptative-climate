"""Spec §1.3.5.1 Reference temperature (ENT-REF), offsets (CFG-SENS-1, CFG-SENS-6)."""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration.spec.harness import Bench, yaml_entry

spec = pytest.mark.spec

HEATER = "climate.heater"
AIRCON = "climate.aircon"
ROOM = "sensor.room"


def ac(bench: Bench) -> Any:
    return bench.ac("Living room")


def current(bench: Bench) -> Any:
    return ac(bench).attr("current_temperature")


async def start(
    bench: Bench,
    *,
    room: Any = ...,
    heater: dict[str, Any] | None = None,
    aircon: dict[str, Any] | None = None,
    **options: Any,
) -> tuple[Any, Any]:
    """Heater reading 19 °C, aircon reading 23 °C; with a room sensor if `room` is given."""
    h = bench.device(HEATER, ["heat"], **{"current_temperature": 19.0, **(heater or {})})
    a = bench.device(AIRCON, ["cool"], **{"current_temperature": 23.0, **(aircon or {})})
    if room is not ...:
        bench.sensor(ROOM, **room) if isinstance(room, dict) else bench.sensor(ROOM, room)
        options["temperature_sensor"] = ROOM
    await bench.start(
        [yaml_entry("Living room", heat_entity=HEATER, cool_entity=AIRCON, **options)]
    )
    return h, a


# --- ENT-REF-1: the temperature sensor ----------------------------------------------------------


@spec("ENT-REF-1", "ENT-REF-4", "CFG-SENS-6")
@pytest.mark.parametrize(
    ("room", "expected"),
    [
        pytest.param({"value": 21.5}, 21.5, id="°C"),
        pytest.param({"value": 68.0, "unit": "°F"}, 20.0, id="°F converted"),
        pytest.param({"value": 294.15, "unit": "K"}, 21.0, id="K converted"),
        pytest.param({"value": 21.0, "unit": None, "device_class": None}, 21.0, id="no unit"),
    ],
)
async def test_ent_ref_1_value_of_the_sensor(bench: Bench, room: Any, expected: float) -> None:
    await start(bench, room=room)
    assert current(bench) == pytest.approx(expected, abs=0.01)


@spec("ENT-REF-1", "ENT-REF-2", "ENT-REF-7")
@pytest.mark.parametrize(
    "invalid",
    [
        pytest.param({"value": "unavailable"}, id="unavailable"),
        pytest.param({"value": None}, id="unknown"),
        pytest.param({"value": "warm"}, id="text"),
        pytest.param({"value": "inf"}, id="infinite"),
        pytest.param({"unit": "%"}, id="not a temperature unit"),
    ],
)
async def test_ent_ref_1_invalid_value_falls_back_to_the_sources(
    bench: Bench, invalid: dict[str, Any]
) -> None:
    await start(bench, room=21.0)
    await ac(bench).set_hvac_mode("heat")
    assert current(bench) == 21.0
    await bench.sensors[ROOM].set(**invalid)
    assert current(bench) == 19.0
    await bench.sensors[ROOM].set(22.0, unit="°C")
    assert current(bench) == 22.0


# --- ENT-REF-2, ENT-REF-3: the readings of the sources -------------------------------------------------


@spec("ENT-REF-2", "ENT-REF-7")
async def test_ent_ref_2_active_source(bench: Bench) -> None:
    await start(bench)
    await ac(bench).set_hvac_mode("heat")
    assert current(bench) == 19.0
    await ac(bench).set_hvac_mode("cool")
    assert current(bench) == 23.0


@spec("ENT-REF-2")
async def test_ent_ref_2_last_used_source_in_off(bench: Bench) -> None:
    await start(bench)
    await ac(bench).set_hvac_mode("cool")
    await ac(bench).set_hvac_mode("off")
    assert current(bench) == 23.0


@spec("ENT-REF-2")
async def test_ent_ref_2_first_available_source_when_no_mode_was_used(bench: Bench) -> None:
    heater, aircon = await start(bench)
    assert current(bench) == 19.0
    await heater.set(available=False)
    assert current(bench) == 23.0


@spec("ENT-REF-2", "ENT-REF-3")
async def test_ent_ref_3_last_used_source_without_reading(bench: Bench) -> None:
    """Not a fallback: the last used source shows nothing, there is no reference."""
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("cool")
    await ac(bench).set_hvac_mode("off")
    await aircon.set(current_temperature=None)
    assert current(bench) is None


@spec("ENT-REF-4", "ENT-WAIT-2")
async def test_ent_ref_4_shown_while_waiting(bench: Bench) -> None:
    heater, aircon = await start(bench, room=21.0)
    await ac(bench).set_hvac_mode("heat")
    await heater.set(available=False)
    assert ac(bench).state == "unknown"
    assert current(bench) == 21.0


@spec("ENT-REF-2", "ENT-REF-3")
async def test_ent_ref_3_active_source_away_without_sensor(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await heater.set(available=False)
    assert current(bench) is None


# --- ENT-REF-5, CFG-SENS-1: offsets ---------------------------------------------------------------


@spec("ENT-REF-5", "CFG-SENS-1")
async def test_cfg_sens_1_reading_minus_the_offset(bench: Bench) -> None:
    await start(bench, heater={"current_temperature": 22.0}, heat_offset=2)
    await ac(bench).set_hvac_mode("heat")
    assert current(bench) == 20.0


@spec("CFG-SENS-1", "ENT-TGT-8", "ENT-TGT-9")
async def test_cfg_sens_1_target_sent_plus_the_offset_taken_minus_it(bench: Bench) -> None:
    heater, _ = await start(bench, heat_offset=2)
    await ac(bench).set_hvac_mode("heat")
    await ac(bench).set_temperature(temperature=21.0)
    await bench.advance(15)
    assert heater.temperature == 23.0
    assert ac(bench).attr("temperature") == 21.0
    await heater.set(temperature=25.0)  # changed on the device
    assert ac(bench).attr("temperature") == 23.0


@spec("CFG-SENS-1", "CFG-SENS-3", "CFG-CHECK-2")
async def test_cfg_sens_3_offset_of_a_mode_without_its_own_source(bench: Bench) -> None:
    """A heat_cool offset with a bi-source heat_cool: no effect, the heat offset applies."""
    heater, _ = await start(bench, room=21.0, heat_offset=1, heat_cool_offset=5)
    await ac(bench).set_temperature(target_temp_low=19.0, target_temp_high=24.0)
    await ac(bench).set_hvac_mode("heat_cool")
    await bench.advance(15)
    assert heater.temperature == 20.0
