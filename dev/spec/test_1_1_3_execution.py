"""Spec §1.1.2 Events and §1.1.3 Execution model: what can be seen from outside (EVT, EXEC).

The inside of the actors (queues, steps) is in not_observable.md; its effects
on the order of the calls are replayed in test_5_sequences.py.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from dev.spec.harness import Bench, yaml_entry

spec = pytest.mark.spec

HEATER = "climate.heater"
AIRCON = "climate.aircon"


def ac(bench: Bench) -> Any:
    return bench.ac("Living room")


async def start(bench: Bench) -> tuple[Any, Any]:
    heater = bench.device(HEATER, ["heat"])
    aircon = bench.device(AIRCON, ["cool"])
    await bench.start([yaml_entry("Living room", heat_entity=HEATER, cool_entity=AIRCON)])
    return heater, aircon


@spec("EVT-1", "EXEC-3")
async def test_evt_1_calls_to_the_source_entities_are_not_waited_for(bench: Bench) -> None:
    """A slow device: the user request ends before its call; its effect comes back later."""
    heater, _ = await start(bench)
    hold = heater.hold = asyncio.Event()
    try:
        await asyncio.wait_for(
            bench.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": ac(bench).entity_id, "hvac_mode": "heat"},
                blocking=True,
            ),
            timeout=5,
        )
        assert ac(bench).state == "heat"
        for _ in range(100):  # the call starts in a task, a few loop iterations later
            if heater.calls:
                break
            await asyncio.sleep(0)
        assert heater.modes_asked() == ["heat"]  # the call is on its way, held by the device
        assert heater.hvac_mode == "off"
    finally:
        heater.hold = None
        hold.set()  # the device answers: never left waiting, even when the test fails
    await bench.settle()
    assert heater.hvac_mode == "heat"
    assert ac(bench).state == "heat"


@spec("EXEC-3")
@pytest.mark.parametrize("first", [HEATER, AIRCON])
async def test_exec_3_two_sources_changed_at_once(bench: Bench, first: str) -> None:
    """Two stimuli, one after the other: the last takeover wins, the other is turned off."""
    heater, aircon = await start(bench)
    devices = {HEATER: (heater, "heat"), AIRCON: (aircon, "cool")}
    second = AIRCON if first == HEATER else HEATER
    devices[first][0].change(hvac_mode=devices[first][1])
    devices[second][0].change(hvac_mode=devices[second][1])
    await bench.settle()
    assert ac(bench).state == devices[second][1]
    assert devices[first][0].modes_asked() == ["off"]
    assert devices[second][0].calls == []
