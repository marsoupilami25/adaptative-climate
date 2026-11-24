"""Spec §1.3.2 Entity state management (ENT-STATE, ENT-SEND, ENT-INIT, ENT-OFF, ENT-ON,
ENT-WAIT, ENT-NOSRC).

A heater for heat, an aircon for cool (heat_cool is then bi-source, used in
test_1_3_3_modes_phases.py).
"""

from __future__ import annotations

from typing import Any

from homeassistant.exceptions import HomeAssistantError
import pytest

from tests.integration.spec.harness import Bench, warnings_logged, yaml_entry

spec = pytest.mark.spec

HEATER = "climate.heater"
AIRCON = "climate.aircon"
PUMP = "climate.heat_pump"


def ac(bench: Bench) -> Any:
    return bench.ac("Living room")


async def start(bench: Bench, *, heater: dict[str, Any] | None = None,
                aircon: dict[str, Any] | None = None, **options: Any) -> tuple[Any, Any]:
    """The heater and the aircon, and their entry; returns both devices."""
    h = bench.device(HEATER, ["heat"], **(heater or {}))
    a = bench.device(AIRCON, ["cool", "fan_only"], **(aircon or {}))
    await bench.start(
        [yaml_entry("Living room", heat_entity=HEATER, cool_entity=AIRCON, **options)]
    )
    return h, a


def clear(*devices: Any) -> None:
    for device in devices:
        device.clear_calls()


# --- ENT-STATE-1, ENT-STATE-2: stored mode, last used mode ----------------------------------------


@spec("ENT-STATE-1", "ENT-NOSRC-1", "ENT-NOSRC-2")
async def test_ent_state_1_stored_mode_kept_through_no_source(bench: Bench) -> None:
    heater = bench.device(HEATER, ["heat"])
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    await ac(bench).set_hvac_mode("heat")
    await heater.set(available=False)
    assert ac(bench).state == "unavailable"  # NO_SOURCE
    await bench.restart()
    assert ac(bench).state == "unavailable"
    await heater.set(available=True, hvac_mode="off")
    assert ac(bench).state == "heat"
    assert heater.hvac_mode == "heat"


@spec("ENT-STATE-2", "ENT-STATE-8")
async def test_ent_state_2_turn_on_asks_for_the_last_used_mode(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("cool")
    await ac(bench).turn_off()
    clear(heater, aircon)
    await ac(bench).turn_on()
    assert ac(bench).state == "cool"
    assert aircon.modes_asked() == ["cool"]
    assert heater.calls == []


@spec("ENT-STATE-2", "ENT-STATE-8")
async def test_ent_state_2_turn_on_without_last_used_mode_asks_the_first_mode(
    bench: Bench,
) -> None:
    heater, aircon = await start(bench)
    await ac(bench).turn_on()
    assert ac(bench).state == "heat"
    assert heater.modes_asked() == ["heat"]


@spec("ENT-STATE-2", "ENT-DATA-1")
async def test_ent_state_2_last_used_mode_saved_across_restarts(bench: Bench) -> None:
    await start(bench)
    await ac(bench).set_hvac_mode("cool")
    await ac(bench).turn_off()
    await bench.restart()
    await ac(bench).turn_on()
    assert ac(bench).state == "cool"


@spec("ENT-STATE-2", "ENT-INIT-4", "ENT-DATA-1")
async def test_ent_state_2_last_used_mode_no_longer_configured_counts_as_none(
    bench: Bench,
) -> None:
    bench.device(HEATER, ["heat"])
    bench.device(AIRCON, ["cool"])
    bench.device("climate.dryer", ["dry"])
    await bench.start()
    await bench.create_entry(
        name="Living room", heat_entity=HEATER, cool_entity=AIRCON, dry_entity="climate.dryer"
    )
    await ac(bench).set_hvac_mode("dry")
    await ac(bench).turn_off()
    await bench.change_options("Living room", dry_entity=None)
    await ac(bench).turn_on()
    assert ac(bench).state == "heat"


# --- ENT-STATE-3, ENT-STATE-4: who changes the mode ----------------------------------------------------


@spec("ENT-STATE-3", "ENT-STATE-5", "ENT-SEND-2")
async def test_ent_state_3_change_from_a_source_is_followed(bench: Bench) -> None:
    """Takeover by the aircon: nothing sent to it, the heater is turned off."""
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    clear(heater, aircon)
    await aircon.set(hvac_mode="cool")
    assert ac(bench).state == "cool"
    assert aircon.calls == []
    assert heater.modes_asked() == ["off"]


@spec("ENT-STATE-3")
async def test_ent_state_3_change_asked_by_the_user_is_sent(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    clear(heater, aircon)
    await ac(bench).set_hvac_mode("cool")
    assert aircon.modes_asked() == ["cool"]
    assert heater.modes_asked() == ["off"]


@spec("ENT-STATE-4", "ENT-HVAC-4")
async def test_ent_state_4_mode_whose_source_is_not_available_is_refused(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await aircon.set(available=False)
    with pytest.raises(HomeAssistantError):
        await ac(bench).set_hvac_mode("cool")
    assert ac(bench).state == "off"
    assert aircon.calls == []


@spec("ENT-STATE-4")
async def test_ent_state_4_off_always_accepted(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await aircon.set(available=False)
    await ac(bench).set_hvac_mode("off")
    assert ac(bench).state == "off"


@spec("ENT-STATE-4")
async def test_ent_state_4_request_for_the_current_mode_does_nothing(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await aircon.set(hvac_mode="fan_only")  # tolerated in a foreign mode
    clear(heater, aircon)
    await ac(bench).set_hvac_mode("heat")
    assert heater.calls == []
    assert aircon.calls == []
    assert aircon.hvac_mode == "fan_only"
    await ac(bench).set_hvac_mode("off")
    clear(heater, aircon)
    await ac(bench).set_hvac_mode("off")
    assert heater.calls == []
    assert aircon.calls == []


# --- ENT-STATE-5: source mode changes ----------------------------------------------------------------


@spec("ENT-STATE-5")
async def test_ent_state_5_active_source_leaving_for_a_foreign_mode(bench: Bench) -> None:
    """The entity goes OFF; nothing is sent, the source keeps running."""
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("cool")
    await bench.advance(15)
    clear(heater, aircon)
    await aircon.set(hvac_mode="fan_only")
    assert ac(bench).state == "off"
    assert aircon.calls == []
    assert aircon.hvac_mode == "fan_only"
    assert ac(bench).attr("foreign_modes") == {AIRCON: "fan_only"}


@spec("ENT-STATE-5", "SRC-STATE-5")
async def test_ent_state_5_active_source_turned_off(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await bench.advance(15)
    await heater.set(hvac_mode="off")
    assert ac(bench).state == "off"


@spec("ENT-STATE-5")
async def test_ent_state_5_other_source_in_a_foreign_mode_is_tolerated(
    bench: Bench, caplog: pytest.LogCaptureFixture
) -> None:
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    clear(heater, aircon)
    await aircon.set(hvac_mode="fan_only")
    assert ac(bench).state == "heat"
    assert ac(bench).attr("foreign_modes") == {AIRCON: "fan_only"}
    assert aircon.calls == []
    assert warnings_logged(caplog, AIRCON)


@spec("ENT-STATE-5", "ENT-SEND-2")
async def test_ent_state_5_foreign_source_turned_off_at_the_next_request(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await aircon.set(hvac_mode="fan_only")
    clear(heater, aircon)
    await ac(bench).set_hvac_mode("off")
    assert aircon.modes_asked() == ["off"]
    assert ac(bench).attr("foreign_modes") == {}


@spec("ENT-STATE-5", "SRC-STATE-7")
async def test_ent_state_5_foreign_source_back_from_unusable_resends_its_mode(
    bench: Bench,
) -> None:
    """No request meanwhile: its stored state is the foreign mode, resent."""
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await aircon.set(hvac_mode="fan_only")
    await aircon.set(available=False)
    clear(aircon)
    await aircon.set(available=True, hvac_mode="off")
    assert aircon.modes_asked() == ["fan_only"]


@spec("ENT-STATE-5", "SRC-STATE-4", "SRC-STATE-7")
async def test_ent_state_5_foreign_source_back_after_a_request_is_turned_off(
    bench: Bench,
) -> None:
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await aircon.set(hvac_mode="fan_only")
    await aircon.set(available=False)
    await ac(bench).set_hvac_mode("off")  # off asked while it is away: stored
    clear(aircon)
    await aircon.set(available=True)
    assert aircon.modes_asked() == ["off"]


# --- ENT-STATE-6: NO_SOURCE wins -----------------------------------------------------------------------


@spec("ENT-STATE-6", "ENT-NOSRC-1", "ENT-NOSRC-2")
async def test_ent_state_6_no_source_available_from_waiting(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await heater.set(available=False)
    assert ac(bench).state == "unknown"  # WAITING(heat)
    await aircon.set(available=False)
    assert ac(bench).state == "unavailable"  # NO_SOURCE
    await aircon.set(available=True)
    # Back through resume: the stored mode (heat) still has no source: WAITING(heat)
    assert ac(bench).state == "unknown"
    await heater.set(available=True)
    assert ac(bench).state == "heat"


# --- ENT-STATE-8: turn_on ------------------------------------------------------------------------------


@spec("ENT-STATE-8")
async def test_ent_state_8_turn_on_does_nothing_when_on(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("cool")
    clear(heater, aircon)
    await ac(bench).turn_on()
    assert ac(bench).state == "cool"
    assert heater.calls == []
    assert aircon.calls == []


@spec("ENT-STATE-8", "ENT-WAIT-1")
async def test_ent_state_8_turn_on_does_nothing_while_waiting(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("cool")
    await aircon.set(available=False)
    clear(heater, aircon)
    await ac(bench).turn_on()
    assert ac(bench).state == "unknown"
    assert heater.calls == []


# --- ENT-SEND: what is sent, when --------------------------------------------------------------------------


@spec("ENT-SEND-1", "ENT-SEND-3", "ENT-TGT-7")
async def test_ent_send_3_mode_and_targets_in_one_request(bench: Bench) -> None:
    """set_temperature with hvac_mode: the new source gets its mode, then its target;
    the source left gets only off."""
    heater, aircon = await start(bench)
    await aircon.set(hvac_mode="cool")  # cool discovered
    await ac(bench).set_hvac_mode("heat")
    await bench.advance(15)
    clear(heater, aircon)
    await bench.hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": ac(bench).entity_id, "hvac_mode": "cool", "temperature": 24.0},
        blocking=True,
    )
    await bench.settle()
    assert [call.service for call in aircon.calls] == ["set_hvac_mode", "set_temperature"]
    assert aircon.temperatures_asked() == [{"temperature": 24.0}]
    assert heater.modes_asked() == ["off"]
    assert heater.temperatures_asked() == []


@spec("ENT-SEND-3", "SRC-STATE-8")
async def test_ent_send_3_undiscovered_source_gets_nothing(bench: Bench) -> None:
    heater, aircon = await start(bench, aircon={"present": False, "hvac_mode": "cool"})
    await ac(bench).set_hvac_mode("heat")
    assert aircon.calls == []
    await aircon.appear()  # discovered while it runs: its own entry turns it off
    assert aircon.modes_asked() == ["off"]
    assert ac(bench).state == "heat"


@spec("ENT-SEND-2", "SRC-STATE-10")
async def test_ent_send_2_everything_sent_again_at_start(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await ac(bench).set_temperature(temperature=22.0)
    await bench.advance(15)
    await bench.stop()
    heater.temperature = 19.0  # changed on the device while Home Assistant was stopped
    aircon.hvac_mode = "cool"
    clear(heater, aircon)
    await bench.start(bench.yaml)
    assert heater.temperatures_asked() == [{"temperature": 22.0}]
    assert aircon.modes_asked() == ["off"]


# --- ENT-INIT: start ----------------------------------------------------------------------------------


@spec("ENT-INIT-1", "ENT-TGT-4")
async def test_ent_init_1_targets_brought_in_line_with_a_new_step(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await ac(bench).set_temperature(temperature=21.5)
    await bench.stop()
    heater.target_temp_step = 1.0  # a new step, seen at the next start
    aircon.target_temp_step = 1.0
    await bench.start(bench.yaml)
    shown = ac(bench).attr("temperature")
    assert shown in (21.0, 22.0)
    assert ac(bench).attr("target_temp_step") == 1.0


@spec("ENT-INIT-4")
async def test_ent_init_4_source_removed_from_the_configuration_keeps_running(
    bench: Bench,
) -> None:
    heater = bench.device(HEATER, ["heat"])
    aircon = bench.device(AIRCON, ["cool"])
    await bench.start()
    await bench.create_entry(name="Living room", heat_entity=HEATER, cool_entity=AIRCON)
    await ac(bench).set_hvac_mode("cool")
    clear(heater, aircon)
    await bench.change_options("Living room", cool_entity=None)
    assert ac(bench).state == "off"
    assert aircon.calls == []
    assert aircon.hvac_mode == "cool"


# --- ENT-ON, ENT-WAIT -----------------------------------------------------------------------------------


@spec("ENT-ON-1", "ENT-ON-2")
async def test_ent_on_2_action_of_the_active_source_only(bench: Bench) -> None:
    heater, aircon = await start(bench, heater={"hvac_action": "heating"})
    await ac(bench).set_hvac_mode("heat")
    assert ac(bench).attr("hvac_action") == "heating"
    await aircon.set(hvac_action="cooling")
    assert ac(bench).attr("hvac_action") == "heating"
    await heater.set(hvac_action=None)
    assert ac(bench).attr("hvac_action") is None


@spec("ENT-ON-2")
async def test_ent_on_2_action_read_when_the_active_source_changes(bench: Bench) -> None:
    heater, aircon = await start(
        bench, heater={"hvac_action": "idle"}, aircon={"hvac_action": "cooling"}
    )
    await ac(bench).set_hvac_mode("heat")
    assert ac(bench).attr("hvac_action") == "idle"
    await ac(bench).set_hvac_mode("cool")
    assert ac(bench).attr("hvac_action") == "cooling"


@spec("ENT-WAIT-1", "ENT-WAIT-2", "ENT-TGT-2")
async def test_ent_wait_2_waiting_shows_the_mode_as_last_known(bench: Bench) -> None:
    heater, aircon = await start(bench, heater={"min_temp": 10.0, "max_temp": 30.0})
    await ac(bench).set_hvac_mode("heat")
    await ac(bench).set_temperature(temperature=22.0)
    await heater.set(available=False)
    shown = ac(bench)
    assert shown.available
    assert shown.state == "unknown"
    assert shown.attr("hvac_action") is None
    assert shown.attr("temperature") == 22.0
    assert (shown.attr("min_temp"), shown.attr("max_temp")) == (10.0, 30.0)


@spec("ENT-WAIT-1")
async def test_ent_wait_1_left_when_the_source_is_back(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await heater.set(available=False)
    await heater.set(available=True)
    assert ac(bench).state == "heat"


@spec("ENT-WAIT-1", "ENT-SET-1")
async def test_ent_wait_1_targets_set_while_waiting_are_sent_on_return(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await heater.set(available=False)
    await ac(bench).set_temperature(temperature=23.0)
    assert ac(bench).attr("temperature") == 23.0
    await heater.set(available=True)
    assert heater.temperatures_asked()[-1] == {"temperature": 23.0}


@spec("ENT-WAIT-1")
@pytest.mark.parametrize("exit_to", ["cool", "off"])
async def test_ent_wait_1_left_on_a_user_request(bench: Bench, exit_to: str) -> None:
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await heater.set(available=False)
    await ac(bench).set_hvac_mode(exit_to)
    assert ac(bench).state == exit_to


@spec("ENT-WAIT-1", "ENT-STATE-5")
async def test_ent_wait_1_left_on_a_takeover_by_another_source(bench: Bench) -> None:
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await heater.set(available=False)
    await aircon.set(hvac_mode="cool")
    assert ac(bench).state == "cool"


@spec("ENT-WAIT-1", "ENT-STATE-4")
async def test_ent_wait_1_same_mode_asked_while_waiting(bench: Bench) -> None:
    """No error, nothing sent: the entity is already in heat and waits for its source."""
    heater, aircon = await start(bench)
    await ac(bench).set_hvac_mode("heat")
    await heater.set(available=False)
    clear(heater, aircon)
    await ac(bench).set_hvac_mode("heat")
    assert ac(bench).state == "unknown"
    assert aircon.calls == []


# --- ENT-NOSRC ---------------------------------------------------------------------------------------


@spec("ENT-NOSRC-1", "ENT-NOSRC-2")
async def test_ent_nosrc_1_left_through_resume(bench: Bench) -> None:
    """Back from NO_SOURCE, the sources are resynchronized."""
    heater = bench.device(HEATER, ["heat"])
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    await ac(bench).set_hvac_mode("heat")
    await heater.set(available=False)
    assert ac(bench).state == "unavailable"
    clear(heater)
    await heater.set(available=True, hvac_mode="off")
    assert heater.modes_asked() == ["heat"]
    assert ac(bench).state == "heat"


@spec("ENT-NOSRC-3")
async def test_ent_nosrc_3_no_user_request_while_unavailable(bench: Bench) -> None:
    """Home Assistant skips a service call on an unavailable entity, without error."""
    heater = bench.device(HEATER, ["heat"])
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    await heater.set(available=False)
    clear(heater)
    await ac(bench).set_hvac_mode("heat")
    await ac(bench).turn_on()
    await heater.set(available=True)
    assert ac(bench).state == "off"
    assert heater.modes_asked() == []


@spec("ENT-NOSRC-4", "SRC-UNUS-2")
async def test_ent_nosrc_4_source_discovered_unusable_keeps_no_source(bench: Bench) -> None:
    heater = bench.device(HEATER, ["cool"], present=False)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    assert ac(bench).state == "unavailable"
    await heater.appear()
    assert ac(bench).state == "unavailable"
    assert len(bench.issues()) == 1


@spec("ENT-INIT-3", "EXEC-4")
async def test_ent_init_3_init_shown_unavailable(bench: Bench) -> None:
    """The states written while the entry starts: unavailable in INIT, then the mode."""
    bench.device(HEATER, ["heat"])
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)], setup=False)
    written: list[Any] = []

    def record(event: Any) -> None:
        if event.data["entity_id"] == "climate.living_room" and event.data["new_state"]:
            written.append(event.data["new_state"])

    bench.hass.bus.async_listen("state_changed", record)
    await bench.setup_integration()
    states = [state.state for state in written]
    assert states[-1] == "off"
    for state in written[:-1]:
        assert state.state == "unavailable"
        assert "hvac_mode" not in state.attributes
