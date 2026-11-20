"""Spec §1.2.4 Mode request confirmation (SRC-REQ), and MON-SRC-3 (out of sync).

Short timers: confirmation 10 s, retry 20 s; the monitoring reports at once.
"""

from __future__ import annotations

from typing import Any

import pytest

from dev.spec.harness import Bench, errors_logged, logged, yaml_entry

spec = pytest.mark.spec

HEATER = "climate.heater"
AIRCON = "climate.aircon"
TIMERS = {"request_confirmation_timer": 10, "request_retry_timer": 20, "monitoring_delay_timer": 0}


async def start(bench: Bench, **device: Any) -> Any:
    """A heater (that may not obey) and its entry; returns the heater."""
    heater = bench.device(HEATER, ["heat", "fan_only"], **device)
    bench.device(AIRCON, ["cool"])
    await bench.start(
        [yaml_entry("Living room", heat_entity=HEATER, cool_entity=AIRCON, **TIMERS)]
    )
    return heater


def ac(bench: Bench) -> Any:
    return bench.ac("Living room")


def out_of_sync(bench: Bench) -> bool:
    """The monitoring reports the heater (the only problem these tests can raise)."""
    sensor = ac(bench).monitoring_sources
    return sensor.state == "on" and HEATER in str(sensor.attr("problems"))


@spec("SRC-REQ-1", "SRC-STATE-5")
async def test_src_req_1_changes_not_showing_the_request_are_ignored(bench: Bench) -> None:
    heater = await start(bench, obey=False)
    await ac(bench).set_hvac_mode("heat")
    await heater.set(hvac_mode="fan_only")  # passing through another mode
    assert ac(bench).state == "heat"
    await heater.set(hvac_mode="heat")
    assert ac(bench).state == "heat"
    await bench.advance(30)
    assert not out_of_sync(bench)
    assert heater.modes_asked() == ["heat"]


@spec("SRC-REQ-2", "SRC-SET-3", "SRC-SET-5")
async def test_src_req_2_settings_sent_once_the_mode_is_shown(bench: Bench) -> None:
    """While the device does not show the mode, the settings wait; then they are sent."""
    heater = await start(bench, delay=5)
    await heater.set(hvac_mode="heat")  # heat discovered: the entity shows a single target
    await heater.set(hvac_mode="off")
    await ac(bench).set_hvac_mode("heat")
    await ac(bench).set_temperature(temperature=23.0)
    assert heater.temperatures_asked() == []
    await bench.advance(6)
    assert heater.hvac_mode == "heat"
    assert heater.temperatures_asked() == [{"temperature": 23.0}]


@spec("SRC-REQ-3", "SRC-REQ-5", "MON-SRC-3")
async def test_src_req_3_failed_call_is_logged_and_confirmed_until_its_timeout(
    bench: Bench, caplog: pytest.LogCaptureFixture
) -> None:
    heater = await start(bench, fail={"set_hvac_mode"})
    await ac(bench).set_hvac_mode("heat")  # the user gets no error: the call is not awaited
    assert ac(bench).state == "heat"
    assert errors_logged(caplog, HEATER) or logged(caplog, 30, HEATER)
    await bench.advance(9)
    assert not out_of_sync(bench)
    await bench.advance(2)
    assert out_of_sync(bench)


@spec("SRC-REQ-4", "SRC-REQ-5", "SRC-STATE-2")
async def test_src_req_4_new_request_replaces_the_previous_one(bench: Bench) -> None:
    """heat not followed, then off: off is sent, and confirmed at its timeout."""
    heater = await start(bench, obey=False)
    await ac(bench).set_hvac_mode("heat")
    await bench.advance(3)
    await ac(bench).set_hvac_mode("off")
    assert heater.modes_asked() == ["heat", "off"]
    await bench.advance(60)
    # The device shows off: confirmed at the timeout, never out of sync, no retry
    assert not out_of_sync(bench)
    assert heater.modes_asked() == ["heat", "off"]


@spec("SRC-REQ-5", "MON-SRC-3")
async def test_src_req_5_out_of_sync_at_the_confirm_timeout(bench: Bench) -> None:
    await start(bench, obey=False)
    await ac(bench).set_hvac_mode("heat")
    await bench.advance(9)
    assert not out_of_sync(bench)
    await bench.advance(2)
    assert out_of_sync(bench)
    assert bench.problem_events(status="started")


@spec("SRC-REQ-6")
async def test_src_req_6_sent_again_every_retry_wait(bench: Bench) -> None:
    """Sent at 0, then after each confirmation (10 s) and retry wait (20 s)."""
    heater = await start(bench, obey=False)
    await ac(bench).set_hvac_mode("heat")
    await bench.advance(29)
    assert heater.modes_asked() == ["heat"]
    await bench.advance(2)
    assert heater.modes_asked() == ["heat", "heat"]
    await bench.advance(28)
    assert heater.modes_asked() == ["heat", "heat"]
    await bench.advance(2)
    assert heater.modes_asked() == ["heat", "heat", "heat"]


@spec("SRC-REQ-7", "SRC-REQ-2", "MON-SRC-3")
async def test_src_req_7_retries_stop_when_the_device_shows_the_mode(bench: Bench) -> None:
    heater = await start(bench, obey=False)
    await ac(bench).set_hvac_mode("heat")
    await bench.advance(15)  # retry wait, out of sync
    assert out_of_sync(bench)
    await heater.set(hvac_mode="heat")
    assert not out_of_sync(bench)
    assert bench.problem_events(status="ended")
    heater.clear_calls()
    await bench.advance(100)
    assert heater.modes_asked() == []
    assert ac(bench).state == "heat"


@spec("SRC-REQ-7", "SRC-REQ-4", "SRC-REQ-9")
async def test_src_req_7_new_request_ends_the_retries(bench: Bench) -> None:
    """A new request starts a confirmation that is not out of sync before its own timeout."""
    heater = await start(bench, obey=False)
    await ac(bench).set_hvac_mode("heat")
    await bench.advance(15)
    assert out_of_sync(bench)
    await ac(bench).set_hvac_mode("off")
    assert not out_of_sync(bench)
    await bench.advance(100)
    assert heater.modes_asked() == ["heat", "off"]
    assert not out_of_sync(bench)


@spec("SRC-REQ-8", "SRC-REQ-7")
async def test_src_req_8_device_master_during_the_retry_wait(bench: Bench) -> None:
    heater = await start(bench, obey=False)
    await ac(bench).set_hvac_mode("heat")
    await bench.advance(15)  # retry wait
    await heater.set(hvac_mode="fan_only")
    assert ac(bench).state == "off"
    assert not out_of_sync(bench)
    heater.clear_calls()
    await bench.advance(100)
    assert heater.modes_asked() == []


@spec("SRC-REQ-9", "MON-SRC-3")
async def test_src_req_9_out_of_sync_stays_during_the_retries(bench: Bench) -> None:
    await start(bench, obey=False)
    await ac(bench).set_hvac_mode("heat")
    for _ in range(6):
        await bench.advance(10)
        assert out_of_sync(bench)
    assert len(bench.problem_events(status="started")) == 1


@spec("SRC-REQ-1", "SRC-STATE-6", "MON-SRC-3")
async def test_src_req_1_unavailable_ends_the_retries_and_the_problem(bench: Bench) -> None:
    heater = await start(bench, obey=False)
    await ac(bench).set_hvac_mode("heat")
    await bench.advance(15)
    assert ac(bench).monitoring_sources.state == "on"
    await heater.set(available=False)
    # The source is now unusable (another problem, after its own delay): no longer out of sync
    problems = str(ac(bench).monitoring_sources.attr("problems"))
    assert "sync" not in problems.casefold()
    heater.clear_calls()
    await bench.advance(100)
    assert heater.calls == []
