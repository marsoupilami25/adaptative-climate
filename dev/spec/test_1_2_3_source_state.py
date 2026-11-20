"""Spec §1.2.3 Source state management (SRC-STATE, SRC-UNDISC, SRC-ON, SRC-UNUS).

The state of a source is local: it is seen through the AC entity (its
state, `unavailable_modes`, `foreign_modes`, `active_entity_id`...) and
through the calls its device receives.
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


async def start(bench: Bench, **options: Any) -> None:
    await bench.start([yaml_entry("Living room", **options)])


def ac(bench: Bench) -> Any:
    return bench.ac("Living room")


async def heating(bench: Bench, **device: Any) -> None:
    """A heater, its entry in heat; the heater runs heat."""
    bench.device(HEATER, ["heat"], **device)
    await start(bench, heat_entity=HEATER)
    await ac(bench).set_hvac_mode("heat")


async def heating_with_aircon(bench: Bench, **device: Any) -> None:
    """The same, with an aircon for cool: the entity keeps a source when the heater goes."""
    bench.device(HEATER, ["heat"], **device)
    bench.device(AIRCON, ["cool"])
    await start(bench, heat_entity=HEATER, cool_entity=AIRCON)
    await ac(bench).set_hvac_mode("heat")


# --- SRC-STATE-1: first state ---------------------------------------------------------------


@spec("SRC-STATE-1", "SRC-STATE-8", "SRC-DATA-4", "ENT-INIT-1")
async def test_src_state_1_first_start_turns_a_running_device_off(bench: Bench) -> None:
    """No stored state: OFF, whose entry turns the device off."""
    heater = bench.device(HEATER, ["heat"], hvac_mode="heat")
    await start(bench, heat_entity=HEATER)
    assert heater.modes_asked() == ["off"]
    assert heater.hvac_mode == "off"
    assert ac(bench).state == "off"


@spec("SRC-STATE-1", "SRC-STATE-8", "ENT-HVAC-2")
async def test_src_state_1_never_seen_source_is_undiscovered(bench: Bench) -> None:
    """A source never seen is UNDISCOVERED: its mode is not available, it gets nothing."""
    bench.device(HEATER, ["heat"], present=False)
    aircon = bench.device(AIRCON, ["cool"])
    await start(bench, heat_entity=HEATER, cool_entity=AIRCON)
    assert ac(bench).state == "off"
    assert "heat" in ac(bench).attr("unavailable_modes")
    await ac(bench).set_hvac_mode("cool")
    assert aircon.modes_asked() == ["cool"]
    assert bench.devices[HEATER].calls == []


@spec("SRC-STATE-1", "SRC-UNUS-1", "SRC-UNUS-3")
async def test_src_state_1_known_source_not_usable_at_start_is_unusable(bench: Bench) -> None:
    heater = bench.device(HEATER, ["heat"])
    aircon = bench.device(AIRCON, ["cool"])
    await start(bench, heat_entity=HEATER, cool_entity=AIRCON)
    await bench.stop()
    heater.available = False
    heater.clear_calls()
    await bench.start(bench.yaml)
    assert "heat" in ac(bench).attr("unavailable_modes")
    await ac(bench).set_hvac_mode("cool")
    assert aircon.modes_asked()[-1] == "cool"
    assert heater.calls == []


@spec("SRC-STATE-1", "SRC-STATE-3", "SRC-SET-13")
async def test_src_state_1_restored_in_its_mode_sends_nothing(bench: Bench) -> None:
    """Stored ON(heat), the device still in heat: nothing is sent to it."""
    await heating(bench)
    heater = bench.devices[HEATER]
    await bench.stop()
    heater.clear_calls()
    await bench.start(bench.yaml)
    assert ac(bench).state == "heat"
    assert heater.modes_asked() == []


# --- SRC-STATE-2, SRC-STATE-3: requests ---------------------------------------------------------


@spec("SRC-STATE-2", "SRC-STATE-3")
async def test_src_state_3_request_moves_the_state_at_once(bench: Bench) -> None:
    """The source is in the state asked at once, even before its device shows it."""
    await heating(bench, obey=False)
    assert bench.devices[HEATER].modes_asked() == ["heat"]
    assert ac(bench).state == "heat"
    assert ac(bench).attr("active_entity_id") == HEATER


@spec("SRC-STATE-2")
async def test_src_state_2_request_during_a_confirmation_is_always_sent(bench: Bench) -> None:
    """request(heat), then request(off) while the device still shows off: off is sent."""
    await heating(bench, obey=False)
    heater = bench.devices[HEATER]
    assert heater.hvac_mode == "off"
    await ac(bench).set_hvac_mode("off")
    assert heater.modes_asked() == ["heat", "off"]


@spec("SRC-STATE-2", "SRC-STATE-5")
async def test_src_state_2_state_entered_from_the_device_sends_nothing(bench: Bench) -> None:
    heater = bench.device(HEATER, ["heat"])
    await start(bench, heat_entity=HEATER)
    await heater.set(hvac_mode="heat")
    assert ac(bench).state == "heat"
    assert heater.modes_asked() == []


# --- SRC-STATE-4: requests while UNUSABLE --------------------------------------------------------


@spec("SRC-STATE-4", "SRC-STATE-7", "SRC-UNUS-3", "SRC-STATE-10")
async def test_src_state_4_request_while_unusable_is_stored_then_sent_on_return(
    bench: Bench,
) -> None:
    heater = bench.device(HEATER, ["heat"])
    aircon = bench.device(AIRCON, ["cool"])
    await start(bench, heat_entity=HEATER, cool_entity=AIRCON)
    await ac(bench).set_hvac_mode("cool")
    await aircon.set(available=False)
    assert ac(bench).hvac_mode is None  # WAITING(cool)
    aircon.clear_calls()
    await ac(bench).set_hvac_mode("heat")  # the aircon is asked off, while UNUSABLE
    assert aircon.calls == []
    assert heater.hvac_mode == "heat"
    # Back, still running cool on its own: its stored state (off) wins
    await aircon.set(available=True)
    assert aircon.modes_asked() == ["off"]
    assert aircon.hvac_mode == "off"
    assert ac(bench).state == "heat"


# --- SRC-STATE-5: takeover -------------------------------------------------------------------


@spec("SRC-STATE-5", "ENT-STATE-5")
async def test_src_state_5_device_turned_on_is_followed(bench: Bench) -> None:
    heater = bench.device(HEATER, ["heat"])
    await start(bench, heat_entity=HEATER)
    await heater.set(hvac_mode="heat")
    assert ac(bench).state == "heat"
    assert heater.calls == []


@spec("SRC-STATE-5", "ENT-STATE-5")
async def test_src_state_5_device_turned_off_is_followed(bench: Bench) -> None:
    await heating(bench)
    heater = bench.devices[HEATER]
    heater.clear_calls()
    await bench.advance(15)
    await heater.set(hvac_mode="off")
    assert ac(bench).state == "off"
    assert heater.calls == []


@spec("SRC-STATE-5", "SRC-REQ-1")
async def test_src_state_5_change_not_showing_the_request_is_ignored_while_confirming(
    bench: Bench,
) -> None:
    """In CONFIRMING(heat), the device going through another mode is not followed."""
    heater = bench.device(HEATER, ["heat", "fan_only"], obey=False)
    await start(bench, heat_entity=HEATER)
    await ac(bench).set_hvac_mode("heat")
    await heater.set(hvac_mode="fan_only")
    assert ac(bench).state == "heat"
    assert ac(bench).attr("foreign_modes") == {}
    await heater.set(hvac_mode="heat")
    assert ac(bench).state == "heat"


@spec("SRC-STATE-5", "SRC-REQ-8")
async def test_src_state_5_change_during_the_retry_wait_is_followed(bench: Bench) -> None:
    heater = bench.device(HEATER, ["heat", "fan_only"], obey=False)
    await start(bench, heat_entity=HEATER, request_confirmation_timer=10, request_retry_timer=60)
    await ac(bench).set_hvac_mode("heat")
    await bench.advance(11)  # retry wait
    await heater.set(hvac_mode="fan_only")  # changed on the device: followed
    assert ac(bench).state == "off"  # the active source left for a foreign mode
    assert ac(bench).attr("foreign_modes") == {HEATER: "fan_only"}
    heater.clear_calls()
    await bench.advance(130)
    assert heater.modes_asked() == []


@spec("SRC-STATE-5", "SRC-SET-5")
async def test_src_state_5_mode_change_during_settle_is_followed(bench: Bench) -> None:
    await heating(bench)
    heater = bench.devices[HEATER]
    await bench.advance(3)  # within the settle time
    await heater.set(hvac_mode="off")
    assert ac(bench).state == "off"


# --- SRC-STATE-6, SRC-STATE-7: UNUSABLE and back ------------------------------------------------


@spec("SRC-STATE-6", "ENT-WAIT-1")
@pytest.mark.parametrize(
    "change",
    [pytest.param({"available": False}, id="unavailable"), pytest.param({"hvac_mode": None}, id="unknown")],
)
async def test_src_state_6_device_not_usable_makes_the_source_unusable(
    bench: Bench, change: dict[str, Any]
) -> None:
    await heating_with_aircon(bench)
    await bench.devices[HEATER].set(**change)
    assert ac(bench).available
    assert ac(bench).hvac_mode is None  # WAITING(heat)
    assert "heat" in ac(bench).attr("unavailable_modes")


@spec("SRC-STATE-6", "SRC-REQ-1", "SRC-REQ-7")
async def test_src_state_6_unusable_ends_the_confirmation(bench: Bench) -> None:
    """No retry while the device is away."""
    heater = bench.device(HEATER, ["heat"], obey=False)
    await start(bench, heat_entity=HEATER, request_confirmation_timer=10, request_retry_timer=20)
    await ac(bench).set_hvac_mode("heat")
    await heater.set(available=False)
    heater.clear_calls()
    await bench.advance(100)
    assert heater.calls == []


@spec("SRC-STATE-6", "SRC-DATA-10", "SRC-UNUS-2", "ENT-HVAC-5")
async def test_src_state_6_served_mode_lost_after_its_removal_confirmation(bench: Bench) -> None:
    await heating_with_aircon(bench)
    heater = bench.devices[HEATER]
    await bench.advance(15)
    await heater.set(hvac_modes=["off", "cool"], hvac_mode="off")
    # Followed as a takeover first; the mode lost is confirmed after 60 s
    await bench.advance(59)
    assert "heat" not in ac(bench).attr("unavailable_modes")
    await bench.advance(2)
    assert "heat" in ac(bench).attr("unavailable_modes")
    assert len(bench.issues()) == 1


@spec("ENT-HVAC-5", "SRC-UNUS-2")
async def test_ent_hvac_5_issue_removed_when_the_mode_is_offered_again(
    bench: Bench, caplog: pytest.LogCaptureFixture
) -> None:
    """Raised with a warning; removed, with an info, once the device offers heat again."""
    await heating_with_aircon(bench)
    heater = bench.devices[HEATER]
    await bench.advance(15)
    await heater.set(hvac_modes=["off", "cool"], hvac_mode="off")
    await bench.advance(61)
    assert len(bench.issues()) == 1
    assert warnings_logged(caplog, HEATER, "heat")
    caplog.clear()
    await heater.set(hvac_modes=["off", "heat", "cool"])
    assert bench.issues() == []
    assert [
        r for r in caplog.records
        if r.levelno == logging.INFO and HEATER in r.getMessage() and "heat" in r.getMessage()
    ]


@spec("SRC-STATE-7", "SRC-STATE-10", "SRC-SET-13")
async def test_src_state_7_back_from_unusable_goes_to_the_stored_state(bench: Bench) -> None:
    """Home Assistant wins: the device, turned off while away, is turned on again."""
    await heating(bench)
    heater = bench.devices[HEATER]
    await bench.advance(15)
    await heater.set(available=False)
    heater.clear_calls()
    await heater.set(available=True, hvac_mode="off")
    assert heater.modes_asked() == ["heat"]
    assert ac(bench).state == "heat"


@spec("SRC-STATE-7", "SRC-SET-5", "SRC-SET-6", "SRC-SET-13")
async def test_src_state_7_back_in_its_mode_settles(bench: Bench) -> None:
    """Back in ON(heat), already in heat: its settings are sent, its own values ignored."""
    await heating(bench)
    heater = bench.devices[HEATER]
    await ac(bench).set_temperature(temperature=22.0)
    await bench.advance(15)
    assert heater.temperature == 22.0
    await heater.set(available=False)
    heater.clear_calls()
    await heater.set(available=True, temperature=25.0)  # reconnects with its own value
    assert heater.modes_asked() == []
    assert heater.temperatures_asked() == [{"temperature": 22.0}]
    await heater.set(temperature=24.0)  # reported during the settle time: ignored
    assert ac(bench).attr("temperature") == 22.0
    await bench.advance(13)
    assert heater.temperatures_asked()[-1] == {"temperature": 22.0}
    assert heater.temperature == 22.0
    assert ac(bench).attr("temperature") == 22.0


@spec("SRC-STATE-7", "SRC-UNUS-2", "SRC-DATA-6")
async def test_src_state_7_mode_missing_keeps_the_source_unusable(bench: Bench) -> None:
    await heating_with_aircon(bench)
    heater = bench.devices[HEATER]
    await bench.advance(15)
    await heater.set(hvac_modes=["off", "cool"], hvac_mode="off")
    await bench.advance(61)
    assert "heat" in ac(bench).attr("unavailable_modes")
    await heater.set(hvac_mode="cool")  # usable, still without heat
    assert "heat" in ac(bench).attr("unavailable_modes")
    heater.clear_calls()
    await heater.set(hvac_modes=["off", "heat", "cool"])  # heat offered again
    assert "heat" not in ac(bench).attr("unavailable_modes")
    assert bench.issues() == []


# --- SRC-STATE-8, SRC-UNDISC: discovery ------------------------------------------------------------


@spec("SRC-STATE-8", "SRC-UNDISC-1", "ENT-NOSRC-1")
async def test_src_state_8_discovered_source_goes_off(bench: Bench) -> None:
    """Seen for the first time while it runs: OFF, its entry turns the device off."""
    heater = bench.device(HEATER, ["heat"], present=False, hvac_mode="heat")
    await start(bench, heat_entity=HEATER)
    assert not ac(bench).available
    await heater.appear()
    assert ac(bench).state == "off"
    assert heater.modes_asked() == ["off"]


@spec("SRC-STATE-8", "SRC-UNDISC-1", "SRC-UNUS-2", "ENT-HVAC-5")
async def test_src_state_8_discovered_without_its_mode_is_unusable(bench: Bench) -> None:
    heater = bench.device(HEATER, ["cool"], present=False)
    aircon = bench.device(AIRCON, ["cool"])
    await start(bench, heat_entity=HEATER, cool_entity=AIRCON)
    await heater.appear()
    assert "heat" in ac(bench).attr("unavailable_modes")
    assert len(bench.issues()) == 1
    assert heater.calls == []
    assert aircon.calls == []


@spec("SRC-UNDISC-2", "ENT-STEP-1")
async def test_src_undisc_2_undiscovered_source_offers_nothing(bench: Bench) -> None:
    """Not counted for the step until discovered."""
    heater = bench.device(HEATER, ["heat"], present=False)
    bench.device(AIRCON, ["cool"], target_temp_step=1.0, temperature=24.0)
    await start(bench, heat_entity=HEATER, cool_entity=AIRCON)
    await ac(bench).set_hvac_mode("cool")  # the cool mode is discovered, step 1
    assert ac(bench).attr("target_temp_step") == 1.0
    await heater.appear()  # discovered, heat not yet: still not counted
    assert ac(bench).attr("target_temp_step") == 1.0
    await ac(bench).set_hvac_mode("heat")  # heat discovered, without step: counts 0.5
    assert ac(bench).attr("target_temp_step") == 0.5


# --- SRC-STATE-9: stored state -------------------------------------------------------------------


@spec("SRC-STATE-9", "SRC-STATE-10")
async def test_src_state_9_takeover_state_is_stored(bench: Bench) -> None:
    """A state taken from the device is stored, and resynchronized at the next start."""
    heater = bench.device(HEATER, ["heat"])
    await start(bench, heat_entity=HEATER)
    await heater.set(hvac_mode="heat")
    await bench.stop()
    heater.hvac_mode = "off"
    heater.clear_calls()
    await bench.start(bench.yaml)
    assert heater.modes_asked() == ["heat"]
    assert ac(bench).state == "heat"


# --- SRC-STATE-11, SRC-STATE-12: temperature and action ----------------------------------------


@spec("SRC-STATE-11", "ENT-REF-2")
async def test_src_state_11_current_temperature_is_reported(bench: Bench) -> None:
    await heating(bench)
    heater = bench.devices[HEATER]
    assert ac(bench).attr("current_temperature") == 20.0
    await heater.set(current_temperature=21.5)
    assert ac(bench).attr("current_temperature") == 21.5
    await heater.set(current_temperature=None)
    assert ac(bench).attr("current_temperature") is None


@spec("SRC-STATE-12", "ENT-ON-2")
async def test_src_state_12_action_is_reported(bench: Bench) -> None:
    await heating(bench, hvac_action="idle")
    heater = bench.devices[HEATER]
    assert ac(bench).attr("hvac_action") == "idle"
    await heater.set(hvac_action="heating")
    assert ac(bench).attr("hvac_action") == "heating"


@spec("SRC-STATE-12", "ENT-ON-2")
async def test_src_state_12_action_shown_as_is_during_the_confirmation(bench: Bench) -> None:
    """The device may still show the action of its previous mode."""
    await heating(bench, obey=False, hvac_action="off")
    assert ac(bench).state == "heat"
    assert ac(bench).attr("hvac_action") == "off"


# --- SRC-ON-1, SRC-UNUS: what the source judges ----------------------------------------------------


@spec("SRC-ON-1", "ENT-STATE-5")
async def test_src_on_1_foreign_mode_is_judged_by_the_entity(bench: Bench) -> None:
    pump = bench.device(PUMP, ["heat", "cool"])
    await start(bench, heat_entity=PUMP)
    await pump.set(hvac_mode="cool")
    assert ac(bench).state == "off"
    assert ac(bench).attr("foreign_modes") == {PUMP: "cool"}
    assert pump.calls == []


@spec("SRC-UNUS-1", "ENT-CAP-1", "SRC-DATA-7")
async def test_src_unus_1_capabilities_kept_while_not_usable(bench: Bench) -> None:
    await heating_with_aircon(bench, min_temp=10.0, max_temp=30.0)
    assert (ac(bench).attr("min_temp"), ac(bench).attr("max_temp")) == (10.0, 30.0)
    await bench.devices[HEATER].set(available=False)
    assert ac(bench).hvac_mode is None
    assert (ac(bench).attr("min_temp"), ac(bench).attr("max_temp")) == (10.0, 30.0)


@spec("SRC-UNUS-2")
async def test_src_unus_2_source_of_several_modes_is_unusable_for_all(bench: Bench) -> None:
    """Losing one served mode makes the source unusable for every mode it serves."""
    pump = bench.device(PUMP, ["heat", "cool"])
    bench.device(AIRCON, ["dry"])
    await start(
        bench, heat_entity=PUMP, cool_entity=PUMP, dry_entity=AIRCON, removal_confirmation_timer=0
    )
    await pump.set(hvac_modes=["off", "cool"])
    unavailable = ac(bench).attr("unavailable_modes")
    assert "heat" in unavailable
    assert "cool" in unavailable
