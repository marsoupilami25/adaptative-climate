"""Spec §1.3.3 Mode management: mono/bi-source modes, phases, wanted phase
(ENT-TYPE, ENT-PHASE, ENT-WANT).

A bi-source heat_cool: the heater for heat, the aircon for cool, the room
sensor as reference temperature. Targets 19 / 24 °C, phase_hysteresis 1 °C.
"""

from __future__ import annotations

from typing import Any

from homeassistant.exceptions import HomeAssistantError
import pytest

from dev.spec.harness import Bench, yaml_entry

spec = pytest.mark.spec

HEATER = "climate.heater"
AIRCON = "climate.aircon"
PUMP = "climate.heat_pump"
ROOM = "sensor.room"


def ac(bench: Bench) -> Any:
    return bench.ac("Living room")


async def bi_source(
    bench: Bench,
    room: float | None = 21.0,
    *,
    heater: dict[str, Any] | None = None,
    aircon: dict[str, Any] | None = None,
    sensor: bool = True,
    **options: Any,
) -> tuple[Any, Any, Any]:
    """The heater, the aircon, the room sensor; targets 19 / 24. Returns the three."""
    h = bench.device(HEATER, ["heat", "heat_cool"], **(heater or {}))
    a = bench.device(AIRCON, ["cool"], **(aircon or {}))
    s = bench.sensor(ROOM, room) if sensor else None
    if sensor:
        options["temperature_sensor"] = ROOM
    await bench.start(
        [yaml_entry("Living room", heat_entity=HEATER, cool_entity=AIRCON, **options)]
    )
    if ac(bench).available:
        await ac(bench).set_temperature(target_temp_low=19.0, target_temp_high=24.0)
    return h, a, s


def phase(bench: Bench) -> Any:
    return ac(bench).attr("phase")


def clear(*devices: Any) -> None:
    for device in devices:
        device.clear_calls()


# --- ENT-TYPE: mono-source and bi-source --------------------------------------------------------


@spec("ENT-TYPE-1", "ENT-TYPE-2", "ENT-INIT-4")
async def test_ent_type_1_set_by_the_configuration(bench: Bench) -> None:
    heater = bench.device(HEATER, ["heat"])
    aircon = bench.device(AIRCON, ["cool"])
    pump = bench.device(PUMP, ["heat_cool"])
    bench.sensor(ROOM, 21.0)
    await bench.start()
    await bench.create_entry(
        name="Living room", heat_entity=HEATER, cool_entity=AIRCON, temperature_sensor=ROOM
    )
    await ac(bench).set_hvac_mode("heat_cool")
    assert phase(bench) is not None
    assert pump.calls == []
    await bench.change_options("Living room", heat_cool_entity=PUMP)
    await ac(bench).set_hvac_mode("heat_cool")
    assert pump.modes_asked() == ["heat_cool"]
    assert phase(bench) is None
    assert ac(bench).attr("active_entity_id") == PUMP


@spec("ENT-TYPE-3", "ENT-WANT-1", "ENT-PHASE-3")
async def test_ent_type_3_the_phase_source_runs_its_phase(bench: Bench) -> None:
    heater, aircon, _ = await bi_source(bench, 21.0)
    await ac(bench).set_hvac_mode("heat_cool")
    assert ac(bench).state == "heat_cool"
    assert phase(bench) == "heat"
    assert ac(bench).attr("active_entity_id") == HEATER
    assert heater.modes_asked() == ["heat"]
    assert aircon.modes_asked() == []
    await bench.advance(15)
    assert heater.temperature == 19.0  # the heat phase gets the low target


@spec("ENT-TYPE-3", "ENT-PHASE-3")
async def test_ent_type_3_one_device_for_both_phases(bench: Bench) -> None:
    """A heat pump for both: a phase switch changes its mode, without turning it off."""
    pump = bench.device(PUMP, ["heat", "cool"])
    sensor = bench.sensor(ROOM, 21.0)
    await bench.start(
        [yaml_entry("Living room", heat_entity=PUMP, cool_entity=PUMP, temperature_sensor=ROOM)]
    )
    await ac(bench).set_temperature(target_temp_low=19.0, target_temp_high=24.0)
    await ac(bench).set_hvac_mode("heat_cool")
    await sensor.set(26.0)
    assert phase(bench) == "cool"
    assert pump.modes_asked() == ["heat", "cool"]


@spec("ENT-TYPE-4", "ENT-HVAC-3", "ENT-PHASE-5", "ENT-STATE-7")
async def test_ent_type_4_available_with_one_phase_source(bench: Bench) -> None:
    heater, aircon, _ = await bi_source(bench, 21.0)
    await heater.set(available=False)
    assert "heat_cool" not in ac(bench).attr("unavailable_modes")
    await ac(bench).set_hvac_mode("heat_cool")
    # The heat phase is wanted; its source is away: WAITING_PHASE(heat)
    assert ac(bench).state == "heat_cool"
    assert phase(bench) == "heat"
    assert ac(bench).attr("hvac_action") is None
    clear(heater)
    await heater.set(available=True)
    assert heater.modes_asked() == ["heat"]


@spec("ENT-TYPE-4", "ENT-HVAC-3", "ENT-STATE-4")
async def test_ent_type_4_refused_without_phase_source(bench: Bench) -> None:
    bench.device("climate.dryer", ["dry"])
    heater = bench.device(HEATER, ["heat"])
    aircon = bench.device(AIRCON, ["cool"])
    bench.sensor(ROOM, 21.0)
    await bench.start(
        [
            yaml_entry(
                "Living room",
                heat_entity=HEATER,
                cool_entity=AIRCON,
                dry_entity="climate.dryer",
                temperature_sensor=ROOM,
            )
        ]
    )
    await heater.set(available=False)
    await aircon.set(available=False)
    assert "heat_cool" in ac(bench).attr("unavailable_modes")
    with pytest.raises(HomeAssistantError):
        await ac(bench).set_hvac_mode("heat_cool")


@spec("ENT-TYPE-5", "ENT-PHASE-4")
async def test_ent_type_5_phase_source_set_to_its_mode_is_a_takeover(bench: Bench) -> None:
    """Phase heat, the aircon set to cool on its remote: the entity goes to cool."""
    heater, aircon, _ = await bi_source(bench, 21.0)
    await ac(bench).set_hvac_mode("heat_cool")
    clear(heater, aircon)
    await aircon.set(hvac_mode="cool")
    assert ac(bench).state == "cool"
    assert phase(bench) is None
    assert heater.modes_asked() == ["off"]
    assert aircon.calls == []


@spec("ENT-TYPE-5", "ENT-STATE-5")
async def test_ent_type_5_phase_source_set_to_heat_cool_is_foreign(bench: Bench) -> None:
    heater, aircon, _ = await bi_source(bench, 21.0)
    await ac(bench).set_hvac_mode("heat_cool")
    await bench.advance(15)
    clear(heater, aircon)
    await heater.set(hvac_mode="heat_cool")  # the active source leaves for a foreign mode
    assert ac(bench).state == "off"
    assert ac(bench).attr("foreign_modes") == {HEATER: "heat_cool"}
    assert heater.calls == []


@spec("ENT-PHASE-4", "ENT-STATE-5")
async def test_ent_phase_4_phase_source_turned_off(bench: Bench) -> None:
    heater, aircon, _ = await bi_source(bench, 21.0)
    await ac(bench).set_hvac_mode("heat_cool")
    await bench.advance(15)
    await heater.set(hvac_mode="off")
    assert ac(bench).state == "off"


# --- ENT-WANT-1: entering heat_cool ----------------------------------------------------------------


@spec("ENT-WANT-1")
@pytest.mark.parametrize(
    ("room", "expected"),
    [
        pytest.param(20.0, "heat", id="closest to low"),
        pytest.param(21.5, "heat", id="tie: heat"),
        pytest.param(22.0, "cool", id="closest to high"),
        pytest.param(30.0, "cool", id="above high"),
    ],
)
async def test_ent_want_1_closest_target(bench: Bench, room: float, expected: str) -> None:
    await bi_source(bench, room)
    await ac(bench).set_hvac_mode("heat_cool")
    assert phase(bench) == expected


@spec("ENT-WANT-1")
async def test_ent_want_1_without_reference_heat(bench: Bench) -> None:
    await bi_source(
        bench,
        sensor=False,
        heater={"current_temperature": None},
        aircon={"current_temperature": None},
    )
    await ac(bench).set_hvac_mode("heat_cool")
    assert phase(bench) == "heat"


@spec("ENT-WANT-1")
async def test_ent_want_1_without_reference_the_phase_already_running(bench: Bench) -> None:
    heater, aircon, _ = await bi_source(
        bench,
        sensor=False,
        heater={"current_temperature": None},
        aircon={"current_temperature": None},
    )
    await ac(bench).set_hvac_mode("cool")
    clear(heater, aircon)
    await ac(bench).set_hvac_mode("heat_cool")
    assert phase(bench) == "cool"
    assert aircon.modes_asked() == []
    assert heater.modes_asked() == []


@spec("ENT-WANT-1", "ENT-PHASE-7", "ENT-PHASE-2")
async def test_ent_want_1_undiscovered_phase_source_never_chosen(bench: Bench) -> None:
    """Cool wanted, the aircon never seen: heat; its discovery lets the switch happen."""
    heater, aircon, _ = await bi_source(bench, 26.0, aircon={"present": False})
    await ac(bench).set_hvac_mode("heat_cool")
    assert phase(bench) == "heat"
    await aircon.appear()
    assert phase(bench) == "cool"
    assert aircon.modes_asked()[-1] == "cool"


@spec("ENT-WANT-1", "ENT-PHASE-1")
async def test_ent_want_1_chosen_again_after_a_restart(bench: Bench) -> None:
    """Phase heat at 21; at 22 it is kept (hysteresis); after a restart, cool is closest."""
    _, _, sensor = await bi_source(bench, 21.0)
    await ac(bench).set_hvac_mode("heat_cool")
    await sensor.set(22.0)
    assert phase(bench) == "heat"
    await bench.restart()
    assert ac(bench).state == "heat_cool"
    assert phase(bench) == "cool"


# --- ENT-WANT-3, ENT-PHASE-2: switching --------------------------------------------------------------


@spec("ENT-WANT-3", "ENT-PHASE-2", "ENT-PHASE-3")
async def test_ent_want_3_heat_to_cool_beyond_the_hysteresis(bench: Bench) -> None:
    heater, aircon, sensor = await bi_source(bench, 21.0)
    await ac(bench).set_hvac_mode("heat_cool")
    clear(heater, aircon)
    await sensor.set(25.0)  # high + h, not above
    assert phase(bench) == "heat"
    await sensor.set(25.5)
    assert phase(bench) == "cool"
    assert ac(bench).attr("active_entity_id") == AIRCON
    assert aircon.modes_asked() == ["cool"]
    assert heater.modes_asked() == ["off"]
    await bench.advance(15)
    assert aircon.temperature == 24.0  # the cool phase gets the high target


@spec("ENT-WANT-3", "ENT-PHASE-2")
async def test_ent_want_3_cool_to_heat_beyond_the_hysteresis(bench: Bench) -> None:
    _, _, sensor = await bi_source(bench, 23.0)
    await ac(bench).set_hvac_mode("heat_cool")
    assert phase(bench) == "cool"
    await sensor.set(18.0)
    assert phase(bench) == "cool"
    await sensor.set(17.5)
    assert phase(bench) == "heat"


@spec("ENT-WANT-3")
async def test_ent_want_3_kept_without_local_temperature(bench: Bench) -> None:
    _, _, sensor = await bi_source(
        bench, 21.0, heater={"current_temperature": None}, aircon={"current_temperature": None}
    )
    await ac(bench).set_hvac_mode("heat_cool")
    await sensor.set("unavailable")
    assert phase(bench) == "heat"


@spec("ENT-WANT-3", "CFG-CHECK-1")
async def test_ent_want_3_zero_hysteresis(bench: Bench) -> None:
    _, _, sensor = await bi_source(bench, 21.0, phase_hysteresis=0)
    await ac(bench).set_hvac_mode("heat_cool")
    await sensor.set(24.5)
    assert phase(bench) == "cool"


@spec("ENT-PHASE-2", "ENT-WANT-3", "ENT-TGT-7")
async def test_ent_phase_2_targets_changed_switch_without_hysteresis(bench: Bench) -> None:
    await bi_source(bench, 21.0)
    await ac(bench).set_hvac_mode("heat_cool")
    assert phase(bench) == "heat"
    await ac(bench).set_temperature(target_temp_low=17.0, target_temp_high=20.5)
    assert phase(bench) == "cool"


@spec("ENT-PHASE-2", "ENT-TGT-9")
async def test_ent_phase_2_target_taken_over_is_judged_without_hysteresis(bench: Bench) -> None:
    """At 24.5 °C, within the hysteresis, heat is kept; a low target taken from the heater
    is a change of the targets: judged without hysteresis, 24.5 is above 24: cool."""
    heater, aircon, sensor = await bi_source(bench, 21.0)
    await ac(bench).set_hvac_mode("heat_cool")
    await bench.advance(15)
    await sensor.set(24.5)
    assert phase(bench) == "heat"
    await heater.set(temperature=20.0)
    assert ac(bench).attr("target_temp_low") == 20.0
    assert phase(bench) == "cool"


@spec("ENT-WANT-2", "ENT-REF-6", "ENT-REF-2")
async def test_ent_want_2_local_temperatures_from_two_sources(bench: Bench) -> None:
    """No sensor: the mean is shown; cool only when even the lowest reading is above."""
    heater, aircon, _ = await bi_source(
        bench, sensor=False, heater={"current_temperature": 20.0},
        aircon={"current_temperature": 22.0},
    )
    await ac(bench).set_hvac_mode("heat_cool")
    assert ac(bench).attr("current_temperature") == 21.0
    assert phase(bench) == "heat"
    await aircon.set(current_temperature=27.0)  # one reading above high + h: not enough
    assert phase(bench) == "heat"
    await heater.set(current_temperature=25.5)  # both above: cool
    assert phase(bench) == "cool"


# --- ENT-PHASE-1: stored with the mode -------------------------------------------------------------


@spec("ENT-PHASE-1", "ENT-STATE-7")
async def test_ent_phase_1_forgotten_when_leaving_heat_cool(bench: Bench) -> None:
    await bi_source(bench, 23.0)
    await ac(bench).set_hvac_mode("heat_cool")
    assert phase(bench) == "cool"
    await ac(bench).set_hvac_mode("off")
    assert phase(bench) is None


# --- ENT-PHASE-5, ENT-PHASE-6, ENT-PHASE-7: phase sources away ------------------------------------------


@spec("ENT-PHASE-5", "ENT-PHASE-7")
async def test_ent_phase_5_switch_toward_an_unusable_source(bench: Bench) -> None:
    """Cool wanted, the aircon away: the phase switches and waits for it."""
    heater, aircon, sensor = await bi_source(bench, 21.0)
    await ac(bench).set_hvac_mode("heat_cool")
    await aircon.set(available=False)
    clear(heater, aircon)
    await sensor.set(26.0)
    assert ac(bench).state == "heat_cool"
    assert phase(bench) == "cool"
    assert heater.modes_asked() == ["off"]
    await aircon.set(available=True)
    assert aircon.modes_asked() == ["cool"]


@spec("ENT-PHASE-5")
async def test_ent_phase_5_current_phase_source_unusable(bench: Bench) -> None:
    heater, aircon, _ = await bi_source(bench, 21.0)
    await ac(bench).set_hvac_mode("heat_cool")
    await heater.set(available=False)
    assert ac(bench).state == "heat_cool"
    assert phase(bench) == "heat"
    await heater.set(available=True, hvac_mode="off")
    assert heater.hvac_mode == "heat"


@spec("ENT-PHASE-6", "ENT-WAIT-1")
async def test_ent_phase_6_no_phase_source_available(bench: Bench) -> None:
    bench.device("climate.dryer", ["dry"])
    heater = bench.device(HEATER, ["heat"])
    aircon = bench.device(AIRCON, ["cool"])
    bench.sensor(ROOM, 21.0)
    await bench.start(
        [
            yaml_entry(
                "Living room",
                heat_entity=HEATER,
                cool_entity=AIRCON,
                dry_entity="climate.dryer",
                temperature_sensor=ROOM,
            )
        ]
    )
    await ac(bench).set_temperature(target_temp_low=19.0, target_temp_high=24.0)
    await ac(bench).set_hvac_mode("heat_cool")
    await heater.set(available=False)
    await aircon.set(available=False)
    assert ac(bench).state == "unknown"  # WAITING(heat_cool)
    assert phase(bench) == "heat"
    await aircon.set(available=True)
    assert ac(bench).state == "heat_cool"


@spec("ENT-PHASE-7")
async def test_ent_phase_7_undiscovered_source_blocks_the_switch(bench: Bench) -> None:
    heater, aircon, sensor = await bi_source(bench, 21.0, aircon={"present": False})
    await ac(bench).set_hvac_mode("heat_cool")
    await sensor.set(28.0)
    assert phase(bench) == "heat"
    assert heater.hvac_mode == "heat"


# --- More paths of the phase management --------------------------------------------------------------


async def bi_source_with_dryer(
    bench: Bench, *, heater: dict[str, Any] | None = None, aircon: dict[str, Any] | None = None,
    sensor: bool = True,
) -> tuple[Any, Any]:
    """The bi-source heat_cool, and a dryer so that the entity keeps a source."""
    h = bench.device(HEATER, ["heat"], **(heater or {}))
    a = bench.device(AIRCON, ["cool"], **(aircon or {}))
    bench.device("climate.dryer", ["dry"])
    options: dict[str, Any] = {}
    if sensor:
        bench.sensor(ROOM, 21.0)
        options["temperature_sensor"] = ROOM
    await bench.start(
        [
            yaml_entry(
                "Living room",
                heat_entity=HEATER,
                cool_entity=AIRCON,
                dry_entity="climate.dryer",
                **options,
            )
        ]
    )
    await ac(bench).set_temperature(target_temp_low=19.0, target_temp_high=24.0)
    return h, a


@spec("ENT-WAIT-1", "ENT-PHASE-6", "ENT-PHASE-2")
async def test_ent_wait_1_waiting_heat_cool_left_when_a_phase_source_is_discovered(
    bench: Bench,
) -> None:
    """The heater away, the aircon never seen: WAITING(heat_cool) until the aircon shows up."""
    heater, aircon = await bi_source_with_dryer(bench, aircon={"present": False})
    await ac(bench).set_hvac_mode("heat_cool")
    await heater.set(available=False)
    assert ac(bench).state == "unknown"
    await aircon.appear()
    assert ac(bench).state == "heat_cool"


@spec("ENT-WANT-1")
async def test_ent_want_1_without_reference_the_heat_phase_already_running(bench: Bench) -> None:
    heater, aircon = await bi_source_with_dryer(
        bench, sensor=False, heater={"current_temperature": None},
        aircon={"current_temperature": None},
    )
    await ac(bench).set_hvac_mode("heat")
    clear(heater, aircon)
    await ac(bench).set_hvac_mode("heat_cool")
    assert phase(bench) == "heat"
    assert heater.modes_asked() == []


@spec("ENT-WANT-1", "ENT-PHASE-5")
async def test_ent_want_1_an_unusable_source_counts_with_its_stored_state(bench: Bench) -> None:
    """No reference; the aircon away while it ran cool: the cool phase is chosen, and waits."""
    heater, aircon = await bi_source_with_dryer(
        bench, sensor=False, heater={"current_temperature": None},
        aircon={"current_temperature": None},
    )
    await ac(bench).set_hvac_mode("cool")
    await aircon.set(available=False)
    await ac(bench).set_hvac_mode("heat_cool")
    assert ac(bench).state == "heat_cool"
    assert phase(bench) == "cool"


@spec("ENT-WANT-3", "ENT-TGT-9")
async def test_ent_want_3_low_above_high_keeps_the_phase(bench: Bench) -> None:
    """Low taken at 26 °C on the heater, high stuck at the maximum 25: the phase is kept."""
    heater, aircon = await bi_source_with_dryer(
        bench, heater={"min_temp": 5.0, "max_temp": 30.0},
        aircon={"min_temp": 16.0, "max_temp": 25.0, "temperature": 24.0},
    )
    await aircon.set(hvac_mode="cool")  # cool discovered: high cannot go above 25
    await ac(bench).set_hvac_mode("heat_cool")
    await bench.advance(15)
    assert phase(bench) == "heat"
    await heater.set(temperature=26.0)
    saved = list(ac(bench).attr("saved_targets").values())
    assert 26.0 in saved and 25.0 in saved  # kept: low 26 above high 25
    await bench.sensors[ROOM].set(30.0)
    assert phase(bench) == "heat"


@spec("ENT-PHASE-1", "ENT-PHASE-6")
async def test_ent_phase_1_no_phase_after_a_restart_waiting_heat_cool(bench: Bench) -> None:
    """The `phase` attribute: None until a phase source comes back (§2.2)."""
    heater, aircon = await bi_source_with_dryer(bench)
    await ac(bench).set_hvac_mode("heat_cool")
    assert phase(bench) == "heat"
    await bench.stop()
    heater.available = aircon.available = False
    await bench.start(bench.yaml)
    assert ac(bench).state == "unknown"  # WAITING(heat_cool)
    assert phase(bench) is None
    await heater.set(available=True)
    assert phase(bench) is not None
