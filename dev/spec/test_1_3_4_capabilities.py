"""Spec §1.3.4 Capabilities management (ENT-CAP, ENT-FEAT, ENT-STEP, ENT-RANGE, ENT-FAN).

ENT-HVAC is checked with the modes listed (test_3_configuration.py) and the
source states (test_1_2_3_source_state.py).
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import ClimateEntityFeature as F
from homeassistant.exceptions import HomeAssistantError
import pytest

from dev.spec.harness import Bench, warnings_logged, yaml_entry

spec = pytest.mark.spec

HEATER = "climate.heater"
AIRCON = "climate.aircon"
PUMP = "climate.heat_pump"
RADIATOR = "climate.radiator"
DRYER = "climate.dryer"
ROOM = "sensor.room"


def ac(bench: Bench) -> Any:
    return bench.ac("Living room")


def shown_range(bench: Bench) -> tuple[float, float]:
    return (ac(bench).attr("min_temp"), ac(bench).attr("max_temp"))


async def entry(bench: Bench, **options: Any) -> None:
    await bench.start([yaml_entry("Living room", **options)])


async def discover(*devices_modes: tuple[Any, str]) -> None:
    """Each device runs the mode once on its own, then stops (takeovers)."""
    for device, mode in devices_modes:
        await device.set(hvac_mode=mode)
        await device.set(hvac_mode="off")


# --- ENT-CAP: modes not discovered yet, changes -------------------------------------------------------


@spec("ENT-CAP-4", "ENT-FEAT-5", "ENT-RANGE-1")
async def test_ent_cap_4_mode_not_discovered_has_no_capability(bench: Bench) -> None:
    """Asked, not shown yet by its device: no target, no fan, 7–35 °C."""
    heater = bench.device(
        HEATER, ["heat"], obey=False, min_temp=10.0, max_temp=30.0, fan_modes=["low", "high"]
    )
    aircon = bench.device(AIRCON, ["cool"])
    await entry(bench, heat_entity=HEATER, cool_entity=AIRCON)
    await discover((aircon, "cool"))
    await ac(bench).set_hvac_mode("heat")
    assert ac(bench).state == "heat"
    assert ac(bench).attr("temperature") is None
    assert not ac(bench).attr("fan_modes")
    assert shown_range(bench) == (7.0, 35.0)


@spec("ENT-CAP-5", "ENT-CAP-6", "ENT-FEAT-5", "ENT-TGT-7")
async def test_ent_cap_6_target_set_before_the_discovery_is_sent_at_it(bench: Bench) -> None:
    heater = bench.device(HEATER, ["heat"], obey=False)
    aircon = bench.device(AIRCON, ["cool"])
    await entry(bench, heat_entity=HEATER, cool_entity=AIRCON)
    await discover((aircon, "cool"))  # the entity declares TARGET_TEMPERATURE
    await ac(bench).set_hvac_mode("heat")
    await ac(bench).set_temperature(temperature=23.0)  # T, kept, not sent
    assert heater.temperatures_asked() == []
    await heater.set(hvac_mode="heat")  # heat discovered
    assert heater.temperatures_asked() == [{"temperature": 23.0}]
    assert ac(bench).attr("temperature") == 23.0


@spec("ENT-CAP-6", "ENT-TGT-4", "ENT-RANGE-5")
async def test_ent_cap_6_target_brought_in_line_at_the_discovery(bench: Bench) -> None:
    """T set at 8 °C while heat counted 7–35; heat found at 10–30: 10 is shown and sent.
    T stays at 8: cool (7–35) reaches it."""
    heater = bench.device(HEATER, ["heat"], min_temp=10.0, max_temp=30.0, obey=False)
    aircon = bench.device(AIRCON, ["cool"], min_temp=7.0, max_temp=35.0)
    await entry(bench, heat_entity=HEATER, cool_entity=AIRCON)
    await discover((aircon, "cool"))
    await ac(bench).set_hvac_mode("heat")  # not shown yet: heat not discovered, 7–35
    await ac(bench).set_temperature(temperature=8.0)
    await heater.set(hvac_mode="heat")  # discovered at 10–30
    assert ac(bench).attr("temperature") == 10.0
    assert heater.temperatures_asked() == [{"temperature": 10.0}]
    assert ac(bench).attr("target_gaps") == [
        {"attribute": "temperature", "saved": 8.0, "shown": 10.0}
    ]


@spec("ENT-CAP-5", "ENT-FEAT-1", "ENT-CAP-2")
async def test_ent_cap_5_capabilities_of_another_mode_never_used(bench: Bench) -> None:
    """The pump has a target in cool, none in dry: nothing is ever sent in dry."""
    pump = bench.device(
        PUMP,
        ["cool", "dry"],
        profiles={"dry": {"single_target": False}, "cool": {"single_target": True}},
    )
    await entry(bench, cool_entity=PUMP, dry_entity=PUMP)
    await discover((pump, "cool"))
    await ac(bench).set_temperature(temperature=24.0)
    await ac(bench).set_hvac_mode("dry")
    await bench.advance(15)
    assert ac(bench).attr("temperature") is None
    assert pump.temperatures_asked() == []


async def heat_without_target(bench: Bench) -> Any:
    """Heat discovered on a heater without target; the entity keeps a T of 22 °C."""
    heater = bench.device(HEATER, ["heat"], single_target=False)
    aircon = bench.device(AIRCON, ["cool"])
    await entry(bench, heat_entity=HEATER, cool_entity=AIRCON)
    await discover((aircon, "cool"))  # the entity declares TARGET_TEMPERATURE
    await ac(bench).set_hvac_mode("heat")
    await ac(bench).set_temperature(temperature=22.0)  # T: kept, heat shows none
    assert ac(bench).attr("temperature") is None
    assert heater.temperatures_asked() == []
    return heater


@spec("ENT-CAP-7", "ENT-FEAT-3", "SRC-SET-5")
async def test_ent_cap_7_feature_appearing_during_the_settle_time_gets_the_target(
    bench: Bench,
) -> None:
    """A target the mode now uses, never sent: it is sent; the source ignores its own value."""
    heater = await heat_without_target(bench)
    await bench.advance(3)
    await heater.set(single_target=True)
    assert heater.temperatures_asked() == [{"temperature": 22.0}]
    assert ac(bench).attr("temperature") == 22.0


@spec("ENT-CAP-7", "SRC-SET-11", "ENT-TGT-9")
async def test_ent_cap_7_feature_appearing_later_brings_the_value_of_the_device(
    bench: Bench,
) -> None:
    """Outside the settle time, the value the device starts to show is a takeover: it wins."""
    heater = await heat_without_target(bench)
    await bench.advance(15)
    await heater.set(single_target=True, temperature=20.0)
    assert ac(bench).attr("temperature") == 20.0
    assert heater.temperatures_asked() == []


@spec("ENT-CAP-1", "ENT-CAP-7")
async def test_ent_cap_7_capabilities_rebuilt_while_the_entity_is_off(bench: Bench) -> None:
    heater = bench.device(HEATER, ["heat"], min_temp=10.0, max_temp=30.0)
    aircon = bench.device(AIRCON, ["cool"], min_temp=16.0, max_temp=32.0)
    await entry(bench, heat_entity=HEATER, cool_entity=AIRCON)
    await discover((heater, "heat"), (aircon, "cool"))
    assert shown_range(bench) == (10.0, 32.0)
    await heater.set(hvac_mode="heat", min_temp=8.0)  # a takeover; heat now 8–30
    await ac(bench).set_hvac_mode("off")
    assert shown_range(bench) == (8.0, 32.0)


# --- ENT-FEAT ---------------------------------------------------------------------------------


@spec("ENT-FEAT-3", "ENT-FEAT-5")
async def test_ent_feat_3_features_follow_what_the_modes_show(bench: Bench) -> None:
    heater = bench.device(HEATER, ["heat"])
    await entry(bench, heat_entity=HEATER)
    features = ac(bench).features
    assert features & F.TURN_ON and features & F.TURN_OFF
    assert not features & F.TARGET_TEMPERATURE  # heat not discovered yet
    assert not features & F.TARGET_TEMPERATURE_RANGE
    await ac(bench).set_hvac_mode("heat")
    assert ac(bench).features & F.TARGET_TEMPERATURE
    await ac(bench).set_hvac_mode("off")
    assert ac(bench).features & F.TARGET_TEMPERATURE  # not changed by the mode


@spec("ENT-FEAT-3", "ENT-FEAT-5")
async def test_ent_feat_5_bi_source_heat_cool_always_shows_low_high(bench: Bench) -> None:
    bench.device(HEATER, ["heat"])
    bench.device(AIRCON, ["cool"])
    await entry(bench, heat_entity=HEATER, cool_entity=AIRCON)
    assert ac(bench).features & F.TARGET_TEMPERATURE_RANGE
    await ac(bench).set_temperature(target_temp_low=19.0, target_temp_high=24.0)
    assert (ac(bench).attr("target_temp_low"), ac(bench).attr("target_temp_high")) == (19.0, 24.0)


@spec("ENT-FEAT-4", "ENT-FEAT-3", "ENT-TGT-8")
async def test_ent_feat_4_heat_on_a_low_high_source_uses_low_and_high(bench: Bench) -> None:
    """heat shows the low/high of its source and sends them as a pair, gap kept."""
    pump = bench.device(
        PUMP,
        ["heat"],
        single_target=False,
        range_target=True,
        target_temp_low=19.0,
        target_temp_high=25.0,
    )
    await entry(bench, heat_entity=PUMP)
    await ac(bench).set_hvac_mode("heat")
    await bench.advance(15)
    assert ac(bench).attr("temperature") is None
    assert (ac(bench).attr("target_temp_low"), ac(bench).attr("target_temp_high")) == (19.0, 25.0)
    assert ac(bench).features & F.TARGET_TEMPERATURE_RANGE
    assert not ac(bench).features & F.TARGET_TEMPERATURE
    pump.clear_calls()
    await ac(bench).set_temperature(target_temp_low=24.5, target_temp_high=25.0)
    assert pump.temperatures_asked() == [{"target_temp_low": 24.5, "target_temp_high": 25.5}]


@spec("ENT-FEAT-4", "ENT-FEAT-2", "ENT-TGT-4")
async def test_ent_feat_4_mode_starting_to_show_low_high_does_not_take_t(bench: Bench) -> None:
    """A source with both features shows low/high in heat for the first time: heat now
    shows low and high, with the values of the source (a takeover, ENT-CAP-7), not T."""
    pump = bench.device(PUMP, ["heat"], range_target=True, temperature=21.0)
    await entry(bench, heat_entity=PUMP)
    await ac(bench).set_hvac_mode("heat")
    await bench.advance(15)
    await ac(bench).set_temperature(temperature=23.0)
    assert ac(bench).attr("temperature") == 23.0
    await bench.advance(15)
    await pump.set(target_temp_low=18.0, target_temp_high=26.0)
    assert ac(bench).attr("temperature") is None
    assert (ac(bench).attr("target_temp_low"), ac(bench).attr("target_temp_high")) == (18.0, 26.0)
    assert 23.0 in ac(bench).attr("saved_targets").values()


# --- ENT-STEP --------------------------------------------------------------------------------------


@spec("ENT-STEP-1")
@pytest.mark.parametrize(
    ("heater_step", "aircon_step", "step"),
    [
        pytest.param(0.5, 1.0, 0.5, id="0.5 and 1"),
        pytest.param(0.5, 0.2, 0.1, id="0.5 and 0.2"),
        pytest.param(None, 1.0, 0.5, id="none counts 0.5"),
    ],
)
async def test_ent_step_1_largest_step_dividing_every_step(
    bench: Bench, heater_step: float | None, aircon_step: float, step: float
) -> None:
    heater = bench.device(HEATER, ["heat"], target_temp_step=heater_step)
    aircon = bench.device(AIRCON, ["cool"], target_temp_step=aircon_step)
    await entry(bench, heat_entity=HEATER, cool_entity=AIRCON)
    await discover((heater, "heat"), (aircon, "cool"))
    assert ac(bench).attr("target_temp_step") == pytest.approx(step)


@spec("ENT-STEP-1")
async def test_ent_step_1_no_step_known_yet(bench: Bench) -> None:
    bench.device(HEATER, ["heat"], target_temp_step=1.0)
    await entry(bench, heat_entity=HEATER)
    assert ac(bench).attr("target_temp_step") == 0.5


@spec("ENT-STEP-2")
async def test_ent_step_2_the_same_in_every_mode(bench: Bench) -> None:
    heater = bench.device(HEATER, ["heat"], target_temp_step=0.5)
    aircon = bench.device(AIRCON, ["cool"], target_temp_step=1.0)
    await entry(bench, heat_entity=HEATER, cool_entity=AIRCON)
    await discover((heater, "heat"), (aircon, "cool"))
    for mode in ("heat", "cool", "off"):
        await ac(bench).set_hvac_mode(mode)
        assert ac(bench).attr("target_temp_step") == 0.5


# --- ENT-RANGE ------------------------------------------------------------------------------------


@spec("ENT-RANGE-1", "CFG-SENS-1")
async def test_ent_range_1_range_minus_the_offset(bench: Bench) -> None:
    bench.device(HEATER, ["heat"], min_temp=10.0, max_temp=30.0)
    await entry(bench, heat_entity=HEATER, heat_offset=2)
    await ac(bench).set_hvac_mode("heat")
    assert shown_range(bench) == (8.0, 28.0)


@spec("ENT-RANGE-1")
async def test_ent_range_1_bi_source_heat_cool(bench: Bench) -> None:
    """From the minimum of the heat source to the maximum of the cool source."""
    heater = bench.device(HEATER, ["heat"], min_temp=5.0, max_temp=30.0)
    aircon = bench.device(AIRCON, ["cool"], min_temp=16.0, max_temp=32.0)
    bench.sensor(ROOM, 21.0)
    await entry(bench, heat_entity=HEATER, cool_entity=AIRCON, temperature_sensor=ROOM)
    await discover((heater, "heat"), (aircon, "cool"))
    await ac(bench).set_hvac_mode("heat_cool")
    assert shown_range(bench) == (5.0, 32.0)


@spec("ENT-RANGE-3")
@pytest.mark.parametrize(
    ("limits", "expected"),
    [
        pytest.param({"max_temp": 25}, (10.0, 25.0), id="narrows"),
        pytest.param({"min_temp": 5, "max_temp": 25}, (10.0, 25.0), id="never widens"),
        pytest.param({"min_temp": 31, "max_temp": 40}, (10.0, 30.0), id="outside: ignored"),
        pytest.param({"heat_offset": 2, "max_temp": 25}, (8.0, 25.0), id="before the offset"),
    ],
)
async def test_ent_range_3_limits(bench: Bench, limits: dict[str, Any], expected: Any) -> None:
    bench.device(HEATER, ["heat"], min_temp=10.0, max_temp=30.0)
    await entry(bench, heat_entity=HEATER, **limits)
    await ac(bench).set_hvac_mode("heat")
    assert shown_range(bench) == expected


async def radiator_and_pump(bench: Bench) -> tuple[Any, Any]:
    """A radiator at 5–30 °C for heat, a heat pump at 18–30 °C (low/high) for heat_cool."""
    radiator = bench.device(RADIATOR, ["heat"], min_temp=5.0, max_temp=30.0)
    pump = bench.device(
        PUMP,
        ["heat_cool"],
        min_temp=18.0,
        max_temp=30.0,
        single_target=False,
        range_target=True,
        target_temp_low=20.0,
        target_temp_high=24.0,
    )
    await entry(bench, heat_entity=RADIATOR, heat_cool_entity=PUMP)
    await discover((radiator, "heat"), (pump, "heat_cool"))
    return radiator, pump


@spec("ENT-RANGE-4", "ENT-RANGE-5", "ENT-RANGE-6", "ENT-TGT-12", "ENT-TGT-13")
async def test_ent_range_6_a_target_is_not_lost_because_one_mode_cannot_reach_it(
    bench: Bench,
) -> None:
    """A radiator at 5–30 °C for heat and an AC unit at 16–30 °C for cool share T:
    14 °C is kept; the radiator gets 14, the AC unit 16."""
    radiator = bench.device(RADIATOR, ["heat"], min_temp=5.0, max_temp=30.0)
    aircon = bench.device(AIRCON, ["cool"], min_temp=16.0, max_temp=30.0)
    await entry(bench, heat_entity=RADIATOR, cool_entity=AIRCON)
    await discover((radiator, "heat"), (aircon, "cool"))
    await ac(bench).set_hvac_mode("heat")
    await ac(bench).set_temperature(temperature=14.0)
    await bench.advance(15)
    assert radiator.temperature == 14.0
    await ac(bench).set_hvac_mode("cool")
    await bench.advance(15)
    assert aircon.temperature == 16.0
    assert ac(bench).attr("temperature") == 16.0
    assert ac(bench).attr("target_gaps") == [
        {"attribute": "temperature", "saved": 14.0, "shown": 16.0}
    ]
    await ac(bench).set_hvac_mode("heat")
    assert ac(bench).attr("temperature") == 14.0
    assert ac(bench).attr("target_gaps") == []


@spec("ENT-RANGE-5", "ENT-TGT-7")
async def test_ent_range_5_brought_into_the_range_of_its_target(bench: Bench) -> None:
    """In OFF (5–30 shown), low 6 / high 10: low and high are only used by heat_cool,
    18–30: both brought to 18, then the gap moves high to 19."""
    await radiator_and_pump(bench)
    await ac(bench).set_temperature(target_temp_low=6.0, target_temp_high=10.0)
    assert ac(bench).attr("target_temp_low") == 18.0
    assert ac(bench).attr("target_temp_high") == 19.0


@spec("ENT-TGT-7", "ENT-RANGE-2")
async def test_ent_tgt_7_outside_the_range_shown_is_refused(bench: Bench) -> None:
    await radiator_and_pump(bench)
    await ac(bench).set_hvac_mode("heat_cool")  # 18–30 shown
    with pytest.raises(HomeAssistantError):
        await ac(bench).set_temperature(target_temp_low=14.0, target_temp_high=24.0)


# --- ENT-FAN: options -------------------------------------------------------------------------------


def fan_devices(bench: Bench) -> tuple[Any, Any]:
    heater = bench.device(HEATER, ["heat"], fan_modes=["low", "high"], fan_mode="low")
    aircon = bench.device(
        AIRCON, ["cool"], fan_modes=["Auto", "Low", "High"], fan_mode="Auto"
    )
    return heater, aircon


@spec("ENT-FAN-1", "ENT-FAN-3")
async def test_ent_fan_1_options_of_the_current_mode(bench: Bench) -> None:
    heater, aircon = fan_devices(bench)
    await entry(bench, heat_entity=HEATER, cool_entity=AIRCON)
    await ac(bench).set_hvac_mode("heat")
    assert ac(bench).attr("fan_modes") == ["low", "high"]
    await ac(bench).set_hvac_mode("cool")
    assert ac(bench).attr("fan_modes") == ["Auto", "Low", "High"]
    await ac(bench).set_hvac_mode("off")
    assert not ac(bench).attr("fan_modes")  # not every mode synchronized: none


@spec("ENT-FAN-1", "ENT-FAN-3", "ENT-FAN-8")
async def test_ent_fan_1_options_of_the_current_phase(bench: Bench) -> None:
    heater, aircon = fan_devices(bench)
    sensor = bench.sensor(ROOM, 21.0)
    await entry(bench, heat_entity=HEATER, cool_entity=AIRCON, temperature_sensor=ROOM)
    await discover((heater, "heat"), (aircon, "cool"))
    await ac(bench).set_temperature(target_temp_low=19.0, target_temp_high=24.0)
    await ac(bench).set_hvac_mode("heat_cool")
    assert ac(bench).attr("fan_modes") == ["low", "high"]
    await sensor.set(26.0)
    assert ac(bench).attr("fan_modes") == ["Auto", "Low", "High"]


@spec("ENT-FAN-2")
async def test_ent_fan_2_feature_declared_once_one_mode_has_it(bench: Bench) -> None:
    heater = bench.device(HEATER, ["heat"], fan_modes=["low", "high"], fan_mode="low")
    aircon = bench.device(AIRCON, ["cool"])
    await entry(bench, heat_entity=HEATER, cool_entity=AIRCON)
    assert not ac(bench).features & F.FAN_MODE
    await ac(bench).set_hvac_mode("heat")
    assert ac(bench).features & F.FAN_MODE
    await ac(bench).set_hvac_mode("cool")  # the aircon has no fan: still declared
    assert ac(bench).features & F.FAN_MODE


@spec("ENT-FAN-4")
async def test_ent_fan_4_setting_not_discovered_is_refused(bench: Bench) -> None:
    heater = bench.device(HEATER, ["heat"], fan_modes=["low", "high"], fan_mode="low")
    bench.device(AIRCON, ["cool"])
    await entry(bench, heat_entity=HEATER, cool_entity=AIRCON)
    await ac(bench).set_hvac_mode("heat")
    await ac(bench).set_hvac_mode("cool")  # FAN_MODE declared, cool has no fan
    with pytest.raises(HomeAssistantError):
        await ac(bench).set_fan_mode("low")


@spec("ENT-FAN-4")
async def test_ent_fan_4_only_an_option_shown(bench: Bench) -> None:
    heater = bench.device(HEATER, ["heat"], fan_modes=["low", "high"], fan_mode="low")
    await entry(bench, heat_entity=HEATER)
    await ac(bench).set_hvac_mode("heat")
    with pytest.raises(HomeAssistantError):
        await ac(bench).set_fan_mode("turbo")
    with pytest.raises(HomeAssistantError):
        await ac(bench).set_fan_mode("LOW")
    assert heater.values_asked("fan_mode") == []


@spec("ENT-FAN-3", "ENT-FAN-5", "ENT-FAN-6")
async def test_ent_fan_6_shared_options_of_the_synchronized_modes(bench: Bench) -> None:
    """Offered by all, ignoring case, written as the first synchronized mode writes them."""
    heater, aircon = fan_devices(bench)
    await entry(bench, heat_entity=HEATER, cool_entity=AIRCON, sync_modes=["heat", "cool"])
    await discover((heater, "heat"))
    assert ac(bench).attr("fan_modes") == ["low", "high"]  # cool not discovered: left out
    await discover((aircon, "cool"))
    assert ac(bench).attr("fan_modes") == ["low", "high"]


@spec("ENT-FAN-7", "CFG-FAN-1", "CFG-CHECK-3")
async def test_ent_fan_7_synchronized_mode_without_the_setting(
    bench: Bench, caplog: pytest.LogCaptureFixture
) -> None:
    heater = bench.device(HEATER, ["heat"])  # no fan
    aircon = bench.device(AIRCON, ["cool"], fan_modes=["low", "high"], fan_mode="low")
    await entry(bench, heat_entity=HEATER, cool_entity=AIRCON, sync_modes=["heat", "cool"])
    await discover((heater, "heat"))
    assert bench.issues() == []  # no synchronized mode has a fan yet
    await discover((aircon, "cool"))
    assert len(bench.issues()) == 1
    assert warnings_logged(caplog, "heat")
    caplog.clear()
    await heater.set(fan_modes=["low", "high"], fan_mode="low", hvac_mode="heat")
    assert bench.issues() == []
    assert [r for r in caplog.records if r.levelno == logging.INFO and "heat" in r.getMessage()]


@spec("ENT-FAN-7", "CFG-FAN-1", "CFG-CHECK-3")
async def test_ent_fan_7_bi_source_heat_cool_in_sync_modes(bench: Bench) -> None:
    bench.device(HEATER, ["heat"])
    bench.device(AIRCON, ["cool"])
    await entry(bench, heat_entity=HEATER, cool_entity=AIRCON, sync_modes=["heat", "heat_cool"])
    assert len(bench.issues()) == 1


@spec("ENT-FAN-8", "CFG-FAN-2")
async def test_ent_fan_8_phase_source_without_the_setting(bench: Bench) -> None:
    heater = bench.device(HEATER, ["heat"])  # no fan
    aircon = bench.device(AIRCON, ["cool"], fan_modes=["low", "high"], fan_mode="low")
    await entry(bench, heat_entity=HEATER, cool_entity=AIRCON, bi_source_sync=True)
    await discover((heater, "heat"), (aircon, "cool"))
    assert len(bench.issues()) == 1
