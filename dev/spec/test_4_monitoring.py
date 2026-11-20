"""Spec §4 Monitoring (MON-ROLE, MON-SENS, MON-SRC, MON-TEMP, MON-SEND, MON-LIFE).

monitoring_delay_timer is 60 s unless said otherwise. Out of sync (MON-SRC-3)
and setting not applied (MON-SRC-4) are checked with the sources
(test_1_2_4_mode_confirmation.py, test_1_2_5_setting_requests.py).
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from dev.spec.harness import Bench, warnings_logged, yaml_entry

spec = pytest.mark.spec

HEATER = "climate.heater"
AIRCON = "climate.aircon"
PUMP = "climate.heat_pump"
DRYER = "climate.dryer"
ROOM = "sensor.room"
DELAY = 60


def ac(bench: Bench) -> Any:
    return bench.ac("Living room")


def sources(bench: Bench) -> Any:
    return ac(bench).monitoring_sources


def temperatures(bench: Bench) -> Any:
    return ac(bench).monitoring_temperatures


def reports(sensor: Any, text: str) -> bool:
    """The sensor is on, with a problem about `text` (an entity id...)."""
    return sensor.state == "on" and text in str(sensor.attr("problems"))


async def start(
    bench: Bench,
    *,
    room: Any = None,
    heater: dict[str, Any] | None = None,
    aircon: dict[str, Any] | None = None,
    **options: Any,
) -> tuple[Any, Any]:
    """Heater and aircon reading 21 °C; a room sensor when `room` is given."""
    h = bench.device(HEATER, ["heat"], **{"current_temperature": 21.0, **(heater or {})})
    a = bench.device(AIRCON, ["cool"], **{"current_temperature": 21.0, **(aircon or {})})
    if room is not None:
        bench.sensor(ROOM, room)
        options["temperature_sensor"] = ROOM
    options.setdefault("monitoring_delay_timer", DELAY)
    await bench.start(
        [yaml_entry("Living room", heat_entity=HEATER, cool_entity=AIRCON, **options)]
    )
    return h, a


async def heater_only(bench: Bench, room: Any = 21.0, current: float = 21.0) -> Any:
    """One source and the room sensor: a single comparison."""
    heater = bench.device(HEATER, ["heat"], current_temperature=current)
    bench.sensor(ROOM, room)
    await bench.start(
        [
            yaml_entry(
                "Living room",
                heat_entity=HEATER,
                temperature_sensor=ROOM,
                monitoring_delay_timer=DELAY,
            )
        ]
    )
    return heater


# --- MON-SENS: the two sensors ---------------------------------------------------------------------


@spec("MON-SENS-1", "MON-SENS-2")
async def test_mon_sens_2_attributes_without_problem(bench: Bench) -> None:
    await start(bench, room=21.0, monitoring_gap=1.5)
    assert sources(bench).state == "off"
    assert sources(bench).attr("problems") == []
    assert temperatures(bench).state == "off"
    assert temperatures(bench).attr("problems") == []
    assert temperatures(bench).attr("max_gap") == 1.5
    assert "max_gap" not in sources(bench).attributes


@spec("MON-SENS-1", "MON-SENS-2", "MON-SENS-3")
async def test_mon_sens_3_each_problem_keeps_its_own_delay(bench: Bench) -> None:
    """The aircon away from t0, a gap from t30: reported at t60 and t90."""
    heater, aircon = await start(bench, room=21.0)
    await ac(bench).set_hvac_mode("cool")
    await aircon.set(available=False)
    await bench.advance(30)
    await heater.set(current_temperature=25.0)
    await bench.advance(31)
    assert reports(sources(bench), AIRCON)
    assert temperatures(bench).state == "off"
    await bench.advance(30)
    assert reports(temperatures(bench), HEATER)
    assert len(sources(bench).attr("problems")) == 1


@spec("MON-SENS-4", "ENT-NOSRC-2")
async def test_mon_sens_4_never_unavailable_while_loaded(bench: Bench) -> None:
    bench.device(HEATER, ["heat"])
    bench.sensor(ROOM, 21.0)
    await bench.start(
        [
            yaml_entry(
                "Living room", heat_entity=HEATER, temperature_sensor=ROOM,
                monitoring_delay_timer=DELAY,
            )
        ]
    )
    await ac(bench).set_hvac_mode("heat")
    await bench.devices[HEATER].set(available=False)
    assert ac(bench).state == "unavailable"
    assert sources(bench).available
    assert temperatures(bench).available
    await bench.sensors[ROOM].set(None)
    await bench.advance(DELAY + 1)
    assert reports(temperatures(bench), ROOM)  # it still reports, the entity unavailable


# --- MON-SRC-1, MON-SRC-2: source unusable -------------------------------------------------------------


@spec("MON-SRC-1", "MON-LIFE-1")
async def test_mon_src_1_source_of_the_mode_unusable(bench: Bench) -> None:
    heater, _ = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await heater.set(available=False)  # WAITING(heat)
    await bench.advance(DELAY - 1)
    assert sources(bench).state == "off"
    await bench.advance(2)
    assert reports(sources(bench), HEATER)
    await heater.set(available=True)
    assert sources(bench).state == "off"


@spec("MON-SRC-1")
async def test_mon_src_1_ends_when_the_mode_no_longer_uses_it(bench: Bench) -> None:
    heater, _ = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await heater.set(available=False)
    await bench.advance(DELAY + 1)
    assert reports(sources(bench), HEATER)
    await ac(bench).set_hvac_mode("cool")
    assert sources(bench).state == "off"


@spec("MON-SRC-2", "ENT-NOSRC-2")
async def test_mon_src_2_not_in_no_source(bench: Bench) -> None:
    """Its only source unusable: the entity is unavailable, which already says it."""
    heater = bench.device(HEATER, ["heat"])
    await bench.start([yaml_entry("Living room", heat_entity=HEATER, monitoring_delay_timer=DELAY)])
    await ac(bench).set_hvac_mode("heat")
    await heater.set(available=False)
    assert ac(bench).state == "unavailable"
    await bench.advance(3 * DELAY)
    assert sources(bench).state == "off"


@spec("MON-SRC-1", "MON-SRC-2")
async def test_mon_src_2_ends_when_no_source_is_left(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await heater.set(available=False)  # WAITING(heat): the aircon is still available
    await bench.advance(DELAY + 1)
    assert reports(sources(bench), HEATER)
    await aircon.set(available=False)  # NO_SOURCE
    assert ac(bench).state == "unavailable"
    assert sources(bench).state == "off"


@spec("MON-SRC-1", "MON-SRC-2")
async def test_mon_src_1_bi_source_only_the_source_of_the_current_phase(bench: Bench) -> None:
    """A dryer keeps a source available: without phase source, WAITING(heat_cool)."""
    bench.device(DRYER, ["dry"], current_temperature=21.0)
    heater, aircon = await start(bench, room=21.0, dry_entity=DRYER)
    await ac(bench).set_temperature(target_temp_low=19.0, target_temp_high=24.0)
    await ac(bench).set_hvac_mode("heat_cool")  # phase heat
    await aircon.set(available=False)  # the other phase: may be stopped for the season
    await bench.advance(DELAY + 1)
    assert sources(bench).state == "off"
    await heater.set(available=False)  # no phase source left: WAITING(heat_cool)
    await bench.advance(DELAY + 1)
    assert reports(sources(bench), HEATER)
    assert reports(sources(bench), AIRCON)


@spec("MON-SRC-2")
async def test_mon_src_2_never_while_off(bench: Bench) -> None:
    heater, _ = await start(bench)
    await heater.set(available=False)
    await bench.advance(3 * DELAY)
    assert sources(bench).state == "off"


@spec("MON-SRC-2")
async def test_mon_src_2_other_sources_not_reported(bench: Bench) -> None:
    heater, _ = await start(bench)
    await ac(bench).set_hvac_mode("cool")
    await heater.set(available=False)
    await bench.advance(3 * DELAY)
    assert sources(bench).state == "off"


# --- MON-SRC-5: source not discovered ---------------------------------------------------------------------


@spec("MON-SRC-5")
async def test_mon_src_5_source_never_seen(bench: Bench) -> None:
    """Reported in OFF too; it ends at the discovery."""
    heater, _ = await start(bench, heater={"present": False})
    assert ac(bench).state == "off"
    await bench.advance(DELAY - 1)
    assert sources(bench).state == "off"
    await bench.advance(2)
    assert reports(sources(bench), HEATER)
    await heater.appear()
    assert sources(bench).state == "off"
    assert bench.problem_events(status="ended")


@spec("MON-SRC-5", "MON-LIFE-1")
async def test_mon_src_5_source_loaded_late_is_not_reported(bench: Bench) -> None:
    heater, _ = await start(bench, heater={"present": False})
    await bench.advance(DELAY - 10)
    await heater.appear()
    await bench.advance(3 * DELAY)
    assert sources(bench).state == "off"
    assert bench.problem_events() == []


# --- MON-TEMP ---------------------------------------------------------------------------------


@spec("MON-TEMP-1", "MON-TEMP-3", "MON-TEMP-5")
async def test_mon_temp_1_gap_between_the_sensor_and_a_source(bench: Bench) -> None:
    """There from the start, the entity OFF, nothing changing: reported after the delay."""
    await start(bench, room=21.0, heater={"current_temperature": 23.5})
    await bench.advance(DELAY - 1)
    assert temperatures(bench).state == "off"
    await bench.advance(2)
    assert reports(temperatures(bench), HEATER)
    await bench.devices[HEATER].set(current_temperature=22.0)
    assert temperatures(bench).state == "off"


@spec("MON-TEMP-1")
async def test_mon_temp_1_gap_between_two_sources(bench: Bench) -> None:
    await start(bench, heater={"current_temperature": 19.0}, aircon={"current_temperature": 23.0})
    await bench.advance(DELAY + 1)
    assert reports(temperatures(bench), HEATER)
    assert reports(temperatures(bench), AIRCON)


@spec("MON-TEMP-1", "MON-TEMP-2")
async def test_mon_temp_1_a_source_entity_is_not_compared_with_itself(bench: Bench) -> None:
    bench.device(PUMP, ["heat", "cool"], current_temperature=21.0)
    await bench.start(
        [yaml_entry("Living room", heat_entity=PUMP, cool_entity=PUMP, monitoring_delay_timer=0)]
    )
    await bench.advance(5)
    assert temperatures(bench).state == "off"


@spec("MON-TEMP-2", "CFG-SENS-1")
async def test_mon_temp_2_a_well_set_offset_clears_the_problem(bench: Bench) -> None:
    await start(bench, room=21.0, heater={"current_temperature": 24.0}, heat_offset=3)
    await bench.advance(DELAY + 1)
    assert temperatures(bench).state == "off"


@spec("MON-TEMP-2")
@pytest.mark.parametrize(
    "heater", [{"available": False}, {"current_temperature": None}], ids=["unusable", "no reading"]
)
async def test_mon_temp_2_source_without_reading_is_not_compared(
    bench: Bench, heater: dict[str, Any]
) -> None:
    device, _ = await start(bench, room=21.0, heater={"current_temperature": 26.0})
    await device.set(**heater)
    await bench.advance(DELAY + 1)
    assert temperatures(bench).state == "off"


@spec("MON-TEMP-4", "MON-TEMP-5")
async def test_mon_temp_4_sensor_without_valid_value(bench: Bench) -> None:
    await start(bench, room="unavailable")
    await bench.advance(DELAY - 1)
    assert temperatures(bench).state == "off"
    await bench.advance(2)
    assert reports(temperatures(bench), ROOM)
    await bench.sensors[ROOM].set(21.0)
    assert temperatures(bench).state == "off"


# --- MON-SEND, MON-LIFE: lifecycle, logs, events ------------------------------------------------------------


@spec("MON-SEND-1")
async def test_mon_send_1_a_problem_that_lasts_is_told_once(bench: Bench) -> None:
    await heater_only(bench, current=25.0)
    for value in (21.5, 20.5, 21.0, 20.0):
        await bench.advance(20)
        await bench.sensors[ROOM].set(value)
    await bench.advance(DELAY)
    assert len(bench.problem_events(status="started")) == 1


@spec("MON-LIFE-1")
async def test_mon_life_1_a_problem_back_starts_from_zero(bench: Bench) -> None:
    heater = await heater_only(bench, current=25.0)
    await bench.advance(DELAY - 10)
    await heater.set(current_temperature=21.0)
    await bench.advance(5)
    await heater.set(current_temperature=25.0)
    await bench.advance(DELAY - 1)
    assert temperatures(bench).state == "off"
    await bench.advance(2)
    assert temperatures(bench).state == "on"


@spec("MON-LIFE-2", "MON-LIFE-3", "MON-SEND-2")
async def test_mon_life_3_events_and_logs(bench: Bench, caplog: pytest.LogCaptureFixture) -> None:
    heater = await heater_only(bench, current=25.0)
    await bench.advance(DELAY + 1)
    entry_id = bench.entry("Living room").entry_id
    [started] = bench.problem_events(status="started")
    assert started["entry_id"] == entry_id
    assert started["name"] == "Living room"
    assert started["entity_id"] == temperatures(bench).entity_id
    assert started["problem"] in temperatures(bench).attr("problems")
    assert started["message"]
    assert warnings_logged(caplog, started["message"])
    await heater.set(current_temperature=21.0)
    [ended] = bench.problem_events(status="ended")
    assert ended["entity_id"] == temperatures(bench).entity_id
    infos = [r for r in caplog.records if r.levelno == logging.INFO and r.getMessage() == ended["message"]]
    assert infos


@spec("MON-ROLE-1")
@pytest.mark.parametrize("delay", [0, 900])
async def test_mon_role_1_nothing_depends_on_the_monitoring(bench: Bench, delay: int) -> None:
    """The sources behave the same whatever the monitoring reports."""
    heater, _ = await start(
        bench,
        heater={"obey": False},
        monitoring_delay_timer=delay,
        request_confirmation_timer=10,
        request_retry_timer=20,
    )
    await ac(bench).set_hvac_mode("heat")
    await bench.advance(100)
    assert heater.modes_asked() == ["heat", "heat", "heat", "heat"]
    assert ac(bench).state == "heat"
