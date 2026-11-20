"""Spec §1.2.5 Setting request management (SRC-SET), CFG-TIMER-2 and MON-SRC-4.

The heater has a settle time of 12 s (default). "ACTIVE" below: after the
settle time, outside a mode request confirmation.
"""

from __future__ import annotations

from typing import Any

import pytest

from dev.spec.harness import Bench, warnings_logged, yaml_entry

spec = pytest.mark.spec

HEATER = "climate.heater"
AIRCON = "climate.aircon"
PUMP = "climate.heat_pump"
SETTLE = 12


def ac(bench: Bench) -> Any:
    return bench.ac("Living room")


async def start(bench: Bench, *, heater: dict[str, Any] | None = None, **options: Any) -> Any:
    """A heater (and an aircon, so that the entity keeps a source); returns the heater."""
    device = bench.device(HEATER, ["heat"], **(heater or {}))
    bench.device(AIRCON, ["cool"])
    await bench.start(
        [yaml_entry("Living room", heat_entity=HEATER, cool_entity=AIRCON, **options)]
    )
    return device


async def discover_heat(heater: Any) -> None:
    """The heater runs heat once on its own (heat discovered), then stops: the entity is OFF."""
    await heater.set(hvac_mode="heat")
    await heater.set(hvac_mode="off")


async def active_at(bench: Bench, temperature: float, **start_options: Any) -> Any:
    """The entity in heat at `temperature`, the heater ACTIVE and showing it."""
    heater = await start(bench, **start_options)
    await discover_heat(heater)
    await ac(bench).set_temperature(temperature=temperature)  # in OFF: T, the target of heat
    await ac(bench).set_hvac_mode("heat")
    await bench.advance(SETTLE + 1)
    heater.clear_calls()
    return heater


def not_applied(bench: Bench) -> bool:
    sensor = ac(bench).monitoring_sources
    return sensor.state == "on" and HEATER in str(sensor.attr("problems"))


# --- SRC-SET-1: kept settings ------------------------------------------------------------------


@spec("SRC-SET-1", "SRC-STATE-7", "SRC-SET-13")
async def test_src_set_1_kept_settings_survive_a_restart(bench: Bench) -> None:
    """Back after a restart where it was away, the device gets the settings kept."""
    heater = await active_at(bench, 22.0)
    assert heater.temperature == 22.0
    await bench.stop()
    heater.available = False
    await bench.start(bench.yaml)
    heater.clear_calls()
    await heater.set(available=True, temperature=25.0)
    assert {"temperature": 22.0} in heater.temperatures_asked()
    await bench.advance(SETTLE + 1)
    assert heater.temperature == 22.0
    assert ac(bench).attr("temperature") == 22.0


@spec("SRC-SET-1", "ENT-TGT-1")
async def test_src_set_1_settings_follow_the_mode(bench: Bench) -> None:
    """One device for heat (a single target) and heat_cool (low/high): each mode gets
    its own targets (ENT-FEAT-4)."""
    pump = bench.device(
        PUMP,
        ["heat", "heat_cool"],
        profiles={
            "heat": {"single_target": True, "range_target": False},
            "heat_cool": {
                "single_target": False, "range_target": True,
                "target_temp_low": 18.0, "target_temp_high": 25.0,
            },
        },
    )
    await bench.start([yaml_entry("Living room", heat_entity=PUMP, heat_cool_entity=PUMP)])
    await pump.set(hvac_mode="heat")
    await pump.set(hvac_mode="heat_cool")
    await ac(bench).set_temperature(target_temp_low=19.0, target_temp_high=24.0)
    await ac(bench).set_hvac_mode("heat")
    await ac(bench).set_temperature(temperature=21.0)  # T, in heat
    await bench.advance(SETTLE + 1)
    assert pump.temperature == 21.0
    await ac(bench).set_hvac_mode("heat_cool")
    await bench.advance(SETTLE + 1)
    assert (pump.target_temp_low, pump.target_temp_high) == (19.0, 24.0)


# --- SRC-SET-2, SRC-SET-3: sending --------------------------------------------------------------


@spec("SRC-SET-2")
async def test_src_set_2_settings_sent_at_once_in_active(bench: Bench) -> None:
    heater = await active_at(bench, 22.0)
    await ac(bench).set_temperature(temperature=23.0)
    assert heater.temperatures_asked() == [{"temperature": 23.0}]
    assert heater.temperature == 23.0


@spec("SRC-SET-2", "SRC-SET-11")
async def test_src_set_2_setting_already_shown_is_not_sent(bench: Bench) -> None:
    heater = await active_at(bench, 22.0)
    await heater.set(temperature=23.0)  # taken over
    assert ac(bench).attr("temperature") == 23.0
    await ac(bench).set_temperature(temperature=23.0)
    assert heater.temperatures_asked() == []


@spec("SRC-SET-2")
async def test_src_set_2_low_and_high_go_together(bench: Bench) -> None:
    pump = bench.device(
        PUMP,
        ["heat_cool"],
        single_target=False,
        range_target=True,
        target_temp_low=19.0,
        target_temp_high=25.0,
    )
    await bench.start([yaml_entry("Living room", heat_cool_entity=PUMP)])
    await ac(bench).set_hvac_mode("heat_cool")
    await bench.advance(SETTLE + 1)
    pump.clear_calls()
    await ac(bench).set_temperature(target_temp_low=18.0, target_temp_high=25.0)
    assert pump.temperatures_asked() == [{"target_temp_low": 18.0, "target_temp_high": 25.0}]


@spec("SRC-SET-3", "ENT-SET-1", "SRC-STATE-7")
async def test_src_set_3_settings_while_unusable_are_sent_on_return(bench: Bench) -> None:
    heater = await active_at(bench, 22.0)
    await heater.set(available=False)
    await ac(bench).set_temperature(temperature=23.0)  # in WAITING(heat)
    assert heater.temperatures_asked() == []
    await heater.set(available=True)
    assert heater.temperatures_asked() == [{"temperature": 23.0}]


# --- SRC-SET-4: comparing ------------------------------------------------------------------------


@spec("SRC-SET-4", "SRC-SET-11")
async def test_src_set_4_fan_compared_ignoring_case(bench: Bench) -> None:
    heater = await active_at(bench, 22.0, heater={"fan_modes": ["Low", "High"], "fan_mode": "Low"})
    assert ac(bench).attr("fan_mode") == "Low"
    await heater.set(fan_mode="low")  # the same value, written otherwise
    assert ac(bench).attr("fan_mode") == "Low"
    await bench.advance(60)
    assert heater.values_asked("fan_mode") == []


@spec("SRC-SET-4")
async def test_src_set_4_fan_sent_as_the_device_spells_it(bench: Bench) -> None:
    heater = await active_at(bench, 22.0, heater={"fan_modes": ["Low", "High"], "fan_mode": "Low"})
    assert ac(bench).attr("fan_modes") == ["Low", "High"]
    await ac(bench).set_fan_mode("High")
    assert heater.values_asked("fan_mode") == ["High"]


@spec("SRC-SET-4", "SRC-SET-11")
@pytest.mark.parametrize(
    ("step", "same", "changed"),
    [
        pytest.param(None, 22.3, 23.0, id="no step: 0.5"),
        pytest.param(1.0, 22.6, 24.0, id="step 1"),
    ],
)
async def test_src_set_4_targets_the_same_within_one_step(
    bench: Bench, step: float | None, same: float, changed: float
) -> None:
    """Less than one step from the value sent: the same value (a rounding)."""
    heater = await active_at(
        bench, 22.0, monitoring_delay_timer=0, heater={"target_temp_step": step}
    )
    await heater.set(temperature=same)
    assert ac(bench).attr("temperature") == 22.0
    await bench.advance(60)
    assert heater.temperatures_asked() == []
    assert not not_applied(bench)
    # At least one step from the value sent and from the value shown before: a change
    await heater.set(temperature=changed)
    assert ac(bench).attr("temperature") == changed


# --- SRC-SET-5, SRC-SET-6, SRC-SET-14: the settle time ----------------------------------------------


async def entering_heat(bench: Bench, **start_options: Any) -> Any:
    """Heat asked with a target of 22 °C; the heater obeys and shows it: SETTLE starts."""
    heater = await start(bench, **start_options)
    await discover_heat(heater)
    await ac(bench).set_temperature(temperature=22.0)
    heater.clear_calls()
    await ac(bench).set_hvac_mode("heat")
    assert heater.temperatures_asked() == [{"temperature": 22.0}]
    assert heater.temperature == 22.0
    return heater


@spec("SRC-SET-5", "SRC-SET-6", "SRC-SET-13")
async def test_src_set_5_own_value_during_the_settle_time_is_ignored_then_corrected(
    bench: Bench,
) -> None:
    heater = await entering_heat(bench)
    await bench.advance(3)
    await heater.set(temperature=25.0)  # the device reports its own value
    assert ac(bench).attr("temperature") == 22.0
    assert len(heater.temperatures_asked()) == 1
    await bench.advance(SETTLE)
    assert heater.temperatures_asked() == [{"temperature": 22.0}, {"temperature": 22.0}]
    assert heater.temperature == 22.0
    assert ac(bench).attr("temperature") == 22.0


@spec("SRC-SET-6")
async def test_src_set_6_nothing_sent_again_when_nothing_else_was_shown(bench: Bench) -> None:
    heater = await entering_heat(bench)
    await bench.advance(SETTLE + 5)
    assert heater.temperatures_asked() == [{"temperature": 22.0}]


@spec("SRC-SET-14")
async def test_src_set_14_settle_lasts_its_whole_timer(bench: Bench) -> None:
    """The device shows the value sent at once, then its own one 10 s later: still ignored."""
    heater = await entering_heat(bench)
    await bench.advance(10)
    await heater.set(temperature=25.0)
    assert ac(bench).attr("temperature") == 22.0
    await bench.advance(3)
    assert heater.temperature == 22.0


# --- SRC-SET-7, CFG-TIMER-2: retry on error ---------------------------------------------------------


@spec("SRC-SET-7", "CFG-TIMER-2", "SRC-SET-10")
async def test_src_set_7_failed_call_retried_once_after_5_s(
    bench: Bench, caplog: pytest.LogCaptureFixture
) -> None:
    heater = await active_at(bench, 22.0)
    heater.fail = {"set_temperature"}
    await ac(bench).set_temperature(temperature=23.0)
    assert len(heater.temperatures_asked()) == 1
    await bench.advance(4)
    assert len(heater.temperatures_asked()) == 1
    await bench.advance(2)
    assert len(heater.temperatures_asked()) == 2
    assert warnings_logged(caplog, HEATER)
    await bench.advance(300, step=5)
    assert len(heater.temperatures_asked()) == 2  # no new retry: the resync takes over
    assert ac(bench).attr("temperature") == 23.0


@spec("SRC-SET-7")
async def test_src_set_7_retry_that_succeeds(bench: Bench) -> None:
    heater = await active_at(bench, 22.0)
    heater.fail = {"set_temperature"}
    await ac(bench).set_temperature(temperature=23.0)
    heater.fail = set()
    await bench.advance(6)
    assert heater.temperature == 23.0


@spec("SRC-SET-7", "SRC-SET-1")
async def test_src_set_7_mode_change_cancels_the_retry(bench: Bench) -> None:
    heater = await active_at(bench, 22.0)
    heater.fail = {"set_temperature"}
    await ac(bench).set_temperature(temperature=23.0)
    await ac(bench).set_hvac_mode("off")
    await bench.advance(10)
    assert len(heater.temperatures_asked()) == 1


# --- SRC-SET-8, SRC-SET-9, SRC-SET-10: setting not applied ------------------------------------------------


@spec("SRC-SET-8", "SRC-SET-10", "CFG-TIMER-2")
async def test_src_set_8_resync_every_30_min(bench: Bench) -> None:
    """A device that takes the call but keeps its value gets it again every 30 min."""
    heater = await active_at(bench, 22.0)
    heater.ignore = {"set_temperature"}
    await ac(bench).set_temperature(temperature=23.0)
    assert len(heater.temperatures_asked()) == 1
    # The resync timer runs from the start of the entry (13 s ago)
    await bench.advance(1800 - SETTLE - 6, step=10)
    assert len(heater.temperatures_asked()) == 1
    await bench.advance(10, step=1)
    assert heater.temperatures_asked() == [{"temperature": 23.0}, {"temperature": 23.0}]
    assert ac(bench).attr("temperature") == 23.0


@spec("SRC-SET-9", "SRC-SET-10", "MON-SRC-4", "CFG-TIMER-2")
async def test_src_set_9_setting_not_applied_reported_after_30_s(bench: Bench) -> None:
    heater = await active_at(bench, 22.0, monitoring_delay_timer=0)
    heater.ignore = {"set_temperature"}
    await ac(bench).set_temperature(temperature=23.0)
    await bench.advance(29)
    assert not not_applied(bench)
    await bench.advance(2)
    assert not_applied(bench)
    assert ac(bench).attr("temperature") == 23.0  # the entity keeps its value


@spec("SRC-SET-9", "MON-SRC-4")
async def test_src_set_9_problem_ends_when_the_device_shows_the_setting(bench: Bench) -> None:
    heater = await active_at(bench, 22.0, monitoring_delay_timer=0)
    heater.ignore = {"set_temperature"}
    await ac(bench).set_temperature(temperature=23.0)
    await bench.advance(31)
    assert not_applied(bench)
    heater.ignore = set()
    await heater.set(temperature=23.0)
    assert not not_applied(bench)


@spec("SRC-SET-9", "MON-SRC-4")
async def test_src_set_9_problem_ends_when_the_source_leaves_active(bench: Bench) -> None:
    heater = await active_at(bench, 22.0, monitoring_delay_timer=0)
    heater.ignore = {"set_temperature"}
    await ac(bench).set_temperature(temperature=23.0)
    await bench.advance(31)
    assert not_applied(bench)
    await ac(bench).set_hvac_mode("off")
    assert not not_applied(bench)


@spec("SRC-SET-9")
async def test_src_set_9_not_judged_during_the_settle_time(bench: Bench) -> None:
    """A setting not shown during SETTLE is no problem yet."""
    heater = await start(bench, monitoring_delay_timer=0)
    await discover_heat(heater)
    await ac(bench).set_temperature(temperature=22.0)
    heater.ignore = {"set_temperature"}
    await ac(bench).set_hvac_mode("heat")
    await bench.advance(SETTLE - 1)
    assert not not_applied(bench)


# --- SRC-SET-11, SRC-SET-12, SRC-SET-13: takeover --------------------------------------------------------------


@spec("SRC-SET-11", "ENT-TGT-9", "ENT-SET-2")
async def test_src_set_11_setting_changed_on_the_device_is_adopted(bench: Bench) -> None:
    heater = await active_at(bench, 22.0)
    await heater.set(temperature=25.0)
    assert ac(bench).attr("temperature") == 25.0
    await bench.advance(60)
    assert heater.temperatures_asked() == []


@spec("SRC-SET-11", "SRC-SET-13", "ENT-STATE-5")
async def test_src_set_11_mode_changed_on_the_device_brings_its_settings(bench: Bench) -> None:
    heater = await start(bench, heater={"fan_modes": ["low", "high"], "fan_mode": "low"})
    await discover_heat(heater)
    await ac(bench).set_temperature(temperature=22.0)
    await heater.set(hvac_mode="heat", temperature=24.0, fan_mode="high")
    assert ac(bench).state == "heat"
    assert ac(bench).attr("temperature") == 24.0
    assert ac(bench).attr("fan_mode") == "high"
    # No settle time after a takeover: a value reported just after is adopted too
    await bench.advance(3)
    await heater.set(temperature=26.0)
    assert ac(bench).attr("temperature") == 26.0
    assert heater.temperatures_asked() == []


@spec("SRC-SET-12", "ENT-FANV-5", "ENT-CAP-6")
async def test_src_set_12_fan_of_a_mode_discovered_now_is_followed_during_settle(
    bench: Bench,
) -> None:
    """Heat discovered by the request itself: no fan remembered, the device's is taken."""
    heater = await start(bench, heater={"fan_modes": ["low", "high"], "fan_mode": "low"})
    await ac(bench).set_hvac_mode("heat")
    assert ac(bench).attr("fan_mode") == "low"
    await bench.advance(3)
    await heater.set(fan_mode="high")  # within the settle time: followed at once
    assert ac(bench).attr("fan_mode") == "high"
    assert heater.values_asked("fan_mode") == []


@spec("SRC-SET-13", "SRC-SET-2")
async def test_src_set_13_no_settle_at_start_in_the_mode_already_shown(bench: Bench) -> None:
    heater = await active_at(bench, 22.0)
    await bench.restart()
    await bench.advance(3)
    await heater.set(temperature=24.0)
    assert ac(bench).attr("temperature") == 24.0
