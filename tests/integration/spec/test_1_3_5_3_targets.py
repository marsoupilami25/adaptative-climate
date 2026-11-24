"""Spec §1.3.5.3 Temperature targets (ENT-TGT), ENT-SET.

Two setups:
- with low/high: heater for heat, aircon for cool (bi-source heat_cool shows low/high);
- without: the same, plus a heat pump with a single target for heat_cool (mono-source).

heat and cool on sources with a single target use T, the bi-source heat_cool low and
high (ENT-FEAT-4).
"""

from __future__ import annotations

from typing import Any

from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event as HassEvent, callback
from homeassistant.exceptions import HomeAssistantError
import pytest

from tests.integration.spec.harness import Bench, yaml_entry

spec = pytest.mark.spec

HEATER = "climate.heater"
AIRCON = "climate.aircon"
PUMP = "climate.heat_pump"
RADIATOR = "climate.radiator"
DRYER = "climate.dryer"
ROOM = "sensor.room"


def ac(bench: Bench) -> Any:
    return bench.ac("Living room")


def numbers_in(value: Any) -> list[float]:
    """Every number in an attribute, whatever its shape."""
    if isinstance(value, bool):
        return []
    if isinstance(value, int | float):
        return [float(value)]
    if isinstance(value, dict):
        return [n for item in value.values() for n in numbers_in(item)]
    if isinstance(value, list | tuple):
        return [n for item in value for n in numbers_in(item)]
    return []


def low_high(bench: Bench) -> tuple[Any, Any]:
    return (ac(bench).attr("target_temp_low"), ac(bench).attr("target_temp_high"))


async def discover(*devices_modes: tuple[Any, str]) -> None:
    for device, mode in devices_modes:
        await device.set(hvac_mode=mode)
        await device.set(hvac_mode="off")


async def with_low_high(
    bench: Bench, heater: dict[str, Any] | None = None, aircon: dict[str, Any] | None = None,
    **options: Any,
) -> tuple[Any, Any]:
    """Heater (19 °C) and aircon (25 °C), both discovered; the entity is OFF."""
    h = bench.device(HEATER, ["heat"], **{"temperature": 19.0, **(heater or {})})
    a = bench.device(AIRCON, ["cool"], **{"temperature": 25.0, **(aircon or {})})
    bench.sensor(ROOM, 21.0)
    await bench.start(
        [
            yaml_entry(
                "Living room",
                heat_entity=HEATER,
                cool_entity=AIRCON,
                temperature_sensor=ROOM,
                **options,
            )
        ]
    )
    await discover((h, "heat"), (a, "cool"))
    await ac(bench).set_hvac_mode("off")
    return h, a


async def without_low_high(
    bench: Bench, heater: dict[str, Any] | None = None
) -> tuple[Any, Any, Any]:
    h = bench.device(HEATER, ["heat"], **{"temperature": 19.0, **(heater or {})})
    a = bench.device(AIRCON, ["cool"], temperature=25.0)
    p = bench.device(PUMP, ["heat_cool"], temperature=21.0)
    await bench.start(
        [yaml_entry("Living room", heat_entity=HEATER, cool_entity=AIRCON, heat_cool_entity=PUMP)]
    )
    await discover((h, "heat"), (a, "cool"), (p, "heat_cool"))
    return h, a, p


# --- ENT-TGT-1, ENT-TGT-2: kept by the entity ------------------------------------------------------------


@spec("ENT-TGT-1", "ENT-TGT-2", "ENT-FEAT-4")
async def test_ent_tgt_1_targets_kept_across_modes(bench: Bench) -> None:
    """The source of the new mode gets the target: heat and cool share T. Low and high,
    used by the bi-source heat_cool, are kept apart."""
    heater, aircon = await with_low_high(bench)
    await ac(bench).set_hvac_mode("heat")
    await ac(bench).set_temperature(temperature=21.0)
    await ac(bench).set_hvac_mode("cool")
    assert ac(bench).attr("temperature") == 21.0
    await bench.advance(15)
    assert aircon.temperature == 21.0
    await ac(bench).set_temperature(temperature=26.0)
    await ac(bench).set_hvac_mode("heat")
    assert ac(bench).attr("temperature") == 26.0
    await bench.advance(15)
    assert heater.temperature == 26.0
    await ac(bench).set_hvac_mode("off")
    assert low_high(bench) == (19.0, 25.0)
    assert 26.0 in numbers_in(ac(bench).attr("saved_targets"))


@spec("ENT-TGT-2", "ENT-DATA-1")
async def test_ent_tgt_2_targets_kept_across_restarts(bench: Bench) -> None:
    heater, _ = await with_low_high(bench)
    await ac(bench).set_hvac_mode("heat")
    await ac(bench).set_temperature(temperature=21.5)
    await ac(bench).set_hvac_mode("off")
    await bench.restart()
    await ac(bench).set_hvac_mode("heat")
    assert ac(bench).attr("temperature") == 21.5
    await bench.advance(15)
    assert heater.temperature == 21.5


# --- ENT-TGT-3, ENT-TGT-4: step, range ---------------------------------------------------------------


@spec("ENT-TGT-3")
async def test_ent_tgt_3_user_value_on_the_step(bench: Bench) -> None:
    await with_low_high(bench)
    await ac(bench).set_hvac_mode("heat")
    await ac(bench).set_temperature(temperature=21.3)
    assert ac(bench).attr("temperature") == 21.5


@spec("ENT-TGT-3", "ENT-TGT-9", "ENT-TGT-12", "ENT-TGT-13", "ENT-RANGE-3")
async def test_ent_tgt_3_value_taken_from_the_source_kept_beyond_the_limits(
    bench: Bench,
) -> None:
    """The source wins: 28 °C kept; shown within what heat can reach (max_temp 25)."""
    heater, _ = await with_low_high(bench, heater={"min_temp": 10.0, "max_temp": 30.0}, max_temp=25)
    await ac(bench).set_hvac_mode("heat")
    await bench.advance(15)
    heater.clear_calls()
    await heater.set(temperature=28.0)
    assert ac(bench).attr("temperature") == 25.0
    assert ac(bench).attr("target_gaps") == [
        {"attribute": "temperature", "saved": 28.0, "shown": 25.0}
    ]
    assert heater.temperatures_asked() == []


@spec("ENT-TGT-4", "ENT-CAP-7", "ENT-RANGE-5")
async def test_ent_tgt_4_takeover_does_not_survive_a_change_of_capabilities(
    bench: Bench,
) -> None:
    """Only heat uses T here. 28 °C taken from the heater; heat then narrows to 10–26:
    T is brought to 26, and sent."""
    heater = bench.device(HEATER, ["heat"], temperature=19.0, min_temp=10.0, max_temp=30.0)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    await ac(bench).set_hvac_mode("heat")
    await bench.advance(15)
    await heater.set(temperature=28.0)
    assert ac(bench).attr("temperature") == 28.0
    heater.clear_calls()
    await heater.set(max_temp=26.0)  # the range of heat changed
    assert ac(bench).attr("temperature") == 26.0
    assert ac(bench).attr("target_gaps") == []
    assert heater.temperatures_asked() == [{"temperature": 26.0}]


@spec("ENT-TGT-4", "ENT-CAP-7", "ENT-RANGE-3")
async def test_ent_tgt_4_range_change_hidden_by_the_limits_still_counts(bench: Bench) -> None:
    """Heat at 10–30, max_temp 25: 28 °C taken from the heater is kept. The heater
    goes to 10–29: the range shown stays 10–25, but the range read on the source
    changed: T is brought to 25, and sent."""
    heater = bench.device(HEATER, ["heat"], temperature=19.0, min_temp=10.0, max_temp=30.0)
    aircon = bench.device(AIRCON, ["cool"], temperature=25.0)
    pump = bench.device(PUMP, ["heat_cool"], temperature=21.0)
    await bench.start(
        [
            yaml_entry(
                "Living room",
                heat_entity=HEATER,
                cool_entity=AIRCON,
                heat_cool_entity=PUMP,
                max_temp=25,
            )
        ]
    )
    await discover((heater, "heat"), (aircon, "cool"), (pump, "heat_cool"))
    await ac(bench).set_hvac_mode("heat")
    await bench.advance(15)
    await heater.set(temperature=28.0)
    assert ac(bench).attr("target_gaps") == [
        {"attribute": "temperature", "saved": 28.0, "shown": 25.0}
    ]
    heater.clear_calls()
    await heater.set(max_temp=29.0)
    assert ac(bench).attr("target_gaps") == []
    assert ac(bench).attr("temperature") == 25.0
    assert heater.temperatures_asked() == [{"temperature": 25.0}]


@spec("ENT-TGT-4", "ENT-RANGE-6", "ENT-TGT-12")
async def test_ent_tgt_4_kept_when_another_mode_still_reaches_it(bench: Bench) -> None:
    """T is used by cool too (7–35): 28 °C is kept, shown 26 in heat."""
    heater, _ = await with_low_high(bench, heater={"min_temp": 10.0, "max_temp": 30.0})
    await ac(bench).set_hvac_mode("heat")
    await bench.advance(15)
    await heater.set(temperature=28.0)
    await heater.set(max_temp=26.0)
    assert ac(bench).attr("temperature") == 26.0
    assert ac(bench).attr("target_gaps") == [
        {"attribute": "temperature", "saved": 28.0, "shown": 26.0}
    ]


# --- ENT-TGT-5, ENT-TGT-6: the gap ------------------------------------------------------------------


@spec("ENT-TGT-5", "ENT-TGT-6")
@pytest.mark.parametrize(
    ("asked", "kept"),
    [
        pytest.param({"target_temp_low": 23.5, "target_temp_high": 24.0}, (23.5, 24.5), id="both: high moves"),
        pytest.param({"target_temp_low": 22.0, "target_temp_high": 22.0}, (22.0, 23.0), id="equal: high moves"),
    ],
)
async def test_ent_tgt_6_both_set_high_moves(
    bench: Bench, asked: dict[str, float], kept: tuple[float, float]
) -> None:
    await with_low_high(bench)
    await ac(bench).set_temperature(**asked)
    assert low_high(bench) == kept


@spec("ENT-FEAT-4", "ENT-TGT-5")
async def test_ent_feat_4_t_never_moves_low_and_high(bench: Bench) -> None:
    """heat and cool set T: low and high stay as they are."""
    await with_low_high(bench)
    await ac(bench).set_temperature(target_temp_low=19.0, target_temp_high=24.0)
    await ac(bench).set_hvac_mode("heat")
    await ac(bench).set_temperature(temperature=23.5)
    assert low_high(bench) == (None, None)  # heat shows T
    await ac(bench).set_hvac_mode("cool")
    await ac(bench).set_temperature(temperature=18.0)
    await ac(bench).set_hvac_mode("off")
    assert low_high(bench) == (19.0, 24.0)


@spec("ENT-TGT-5", "ENT-TGT-6")
async def test_ent_tgt_6_min_gap(bench: Bench) -> None:
    await with_low_high(bench, min_gap=2)
    await ac(bench).set_temperature(target_temp_low=22.0, target_temp_high=23.0)
    assert low_high(bench) == (22.0, 24.0)


@spec("ENT-TGT-6")
async def test_ent_tgt_6_the_target_set_gives_way_at_the_end_of_the_range(bench: Bench) -> None:
    """High cannot go up to 30.5 (the end of its range, 5–30): low gives way."""
    await with_low_high(bench, aircon={"min_temp": 16.0, "max_temp": 30.0},
                        heater={"min_temp": 5.0, "max_temp": 30.0})
    await ac(bench).set_temperature(target_temp_low=29.5, target_temp_high=30.0)
    assert low_high(bench) == (29.0, 30.0)


async def gap_pump(bench: Bench, low: float, high: float) -> Any:
    """heat_cool on a source with low/high at 16–30 °C, `min_gap` 2, running at low / high."""
    pump = bench.device(
        PUMP, ["heat_cool"], min_temp=16.0, max_temp=30.0, single_target=False,
        range_target=True, target_temp_low=low, target_temp_high=high,
    )
    await bench.start([yaml_entry("Living room", heat_cool_entity=PUMP, min_gap=2)])
    await ac(bench).set_hvac_mode("heat_cool")
    await bench.advance(15)
    assert low_high(bench) == (low, high)
    pump.clear_calls()
    return pump


@spec("ENT-TGT-5", "ENT-TGT-6")
@pytest.mark.parametrize(
    ("start", "asked", "kept"),
    [
        pytest.param((22.0, 24.0), (22.0, 23.0), (21.0, 23.0), id="high lowered: low moves down"),
        pytest.param((22.0, 24.0), (23.0, 24.0), (23.0, 25.0), id="low raised: high moves up"),
        pytest.param((28.0, 30.0), (29.0, 30.0), (28.0, 30.0), id="high at the end: low gives way"),
        pytest.param((16.0, 18.0), (16.0, 17.0), (16.0, 18.0), id="low at the end: high gives way"),
    ],
)
async def test_ent_tgt_6_one_changed_the_other_moves(
    bench: Bench, start: tuple[float, float], asked: tuple[float, float],
    kept: tuple[float, float],
) -> None:
    """The card changes one target: it is kept, the other one moves; else it gives way."""
    pump = await gap_pump(bench, *start)
    await ac(bench).set_temperature(target_temp_low=asked[0], target_temp_high=asked[1])
    assert low_high(bench) == kept
    assert (pump.target_temp_low, pump.target_temp_high) == kept


@spec("ENT-TGT-7", "ENT-TGT-6")
async def test_ent_tgt_7_state_written_when_not_kept_as_asked(bench: Bench) -> None:
    """From 28 / 30, low raised to 29 stays 28 / 30: the state is written all the same,
    so that the card drops the 29 it shows; a request kept as asked writes nothing."""
    await gap_pump(bench, 28.0, 30.0)
    written: list[HassEvent] = []

    @callback
    def listener(event: HassEvent) -> None:
        if event.data["entity_id"] == ac(bench).entity_id:
            written.append(event)

    bench.hass.bus.async_listen(EVENT_STATE_CHANGED, listener)
    await ac(bench).set_temperature(target_temp_low=29.0, target_temp_high=30.0)
    await bench.settle()
    assert low_high(bench) == (28.0, 30.0)
    assert len(written) == 1
    await ac(bench).set_temperature(target_temp_low=28.0, target_temp_high=30.0)
    await bench.settle()
    assert len(written) == 1


@spec("ENT-FEAT-4", "ENT-TGT-1")
async def test_ent_feat_4_modes_with_a_single_target_share_t(bench: Bench) -> None:
    heater, aircon, pump = await without_low_high(bench)
    await ac(bench).set_hvac_mode("heat")
    await ac(bench).set_temperature(temperature=22.0)
    await ac(bench).set_hvac_mode("cool")
    assert ac(bench).attr("temperature") == 22.0
    await ac(bench).set_temperature(temperature=21.0)
    await ac(bench).set_hvac_mode("heat_cool")
    assert ac(bench).attr("temperature") == 21.0
    await bench.advance(15)
    assert pump.temperature == 21.0
    await ac(bench).set_hvac_mode("heat")
    assert ac(bench).attr("temperature") == 21.0


# --- ENT-TGT-7: set by the user ----------------------------------------------------------------------


@spec("ENT-TGT-7")
async def test_ent_tgt_7_single_target_sets_t(bench: Bench) -> None:
    await without_low_high(bench)
    await ac(bench).set_hvac_mode("heat_cool")
    await ac(bench).set_temperature(temperature=20.5)
    await ac(bench).set_hvac_mode("heat")
    assert ac(bench).attr("temperature") == 20.5


@spec("ENT-TGT-7", "ENT-FEAT-4")
async def test_ent_tgt_7_single_target_in_a_mode_with_low_high_sets_t(bench: Bench) -> None:
    """The bi-source heat_cool shows low/high: a `temperature` sets T, kept, not sent."""
    heater, aircon = await with_low_high(bench)
    await ac(bench).set_hvac_mode("heat_cool")
    await bench.advance(15)
    await ac(bench).set_temperature(temperature=22.0)
    assert low_high(bench) == (19.0, 25.0)
    assert {"temperature": 22.0} not in heater.temperatures_asked() + aircon.temperatures_asked()
    await ac(bench).set_hvac_mode("heat")
    assert ac(bench).attr("temperature") == 22.0


@spec("ENT-TGT-7", "ENT-TGT-11", "ENT-STATE-2")
async def test_ent_tgt_7_in_off_sets_t(bench: Bench) -> None:
    await without_low_high(bench)  # heat_cool used last (discovered by a takeover)
    await ac(bench).set_hvac_mode("off")
    await ac(bench).set_temperature(temperature=18.0)
    assert ac(bench).attr("temperature") == 18.0
    await ac(bench).turn_on()
    assert ac(bench).state == "heat_cool"
    assert ac(bench).attr("temperature") == 18.0
    await ac(bench).set_hvac_mode("heat")
    assert ac(bench).attr("temperature") == 18.0


@spec("ENT-TGT-7")
async def test_ent_tgt_7_low_above_high_is_refused(bench: Bench) -> None:
    await with_low_high(bench)
    with pytest.raises(HomeAssistantError):
        await ac(bench).set_temperature(target_temp_low=25.0, target_temp_high=20.0)
    assert low_high(bench) == (19.0, 25.0)


@spec("ENT-TGT-7", "ENT-FEAT-3")
async def test_ent_tgt_7_single_target_refused_without_the_feature(bench: Bench) -> None:
    """A new entry whose sources show no single target, even off: only low/high (the
    bi-source heat_cool) can be set."""
    bench.device(HEATER, ["heat"], single_target=False)
    bench.device(AIRCON, ["cool"], single_target=False)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER, cool_entity=AIRCON)])
    with pytest.raises(HomeAssistantError):
        await ac(bench).set_temperature(temperature=21.0)


@spec("ENT-TGT-7", "ENT-CAP-4", "ENT-CAP-5", "ENT-FEAT-5")
async def test_ent_tgt_7_new_entry_takes_the_target_its_sources_show(bench: Bench) -> None:
    """A new entry, nothing discovered: the heater shows a single target, off, so the
    entity has one; set, it is kept and not sent until heat is discovered."""
    heater = bench.device(HEATER, ["heat"])
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    await ac(bench).set_temperature(temperature=21.5)
    assert ac(bench).attr("temperature") == 21.5
    assert heater.temperatures_asked() == []
    await ac(bench).set_hvac_mode("heat")
    await bench.advance(15)
    assert heater.temperature == 21.5


@spec("ENT-TGT-7", "ENT-FEAT-3")
async def test_ent_tgt_7_low_high_refused_without_the_feature(bench: Bench) -> None:
    heater = bench.device(HEATER, ["heat"])
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    await ac(bench).set_hvac_mode("heat")
    with pytest.raises(HomeAssistantError):
        await ac(bench).set_temperature(target_temp_low=19.0, target_temp_high=24.0)
    assert heater.temperatures_asked() == []


@spec("ENT-TGT-7", "ENT-STATE-4")
async def test_ent_tgt_7_mode_refused_refuses_the_targets(bench: Bench) -> None:
    heater, aircon = await with_low_high(bench)
    await aircon.set(available=False)
    with pytest.raises(HomeAssistantError):
        await bench.hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": ac(bench).entity_id, "hvac_mode": "cool", "temperature": 27.0},
            blocking=True,
        )
    assert 27.0 not in numbers_in(ac(bench).attr("saved_targets"))


# --- ENT-TGT-8: sent to the source -----------------------------------------------------------------------


@spec("ENT-TGT-8")
async def test_ent_tgt_8_rounded_to_the_step_of_the_source(bench: Bench) -> None:
    """A target of 24.5 °C stays 24.5 in the entity; an AC at step 1 gets 25."""
    _, aircon = await with_low_high(bench, aircon={"target_temp_step": 1.0})
    await ac(bench).set_hvac_mode("cool")
    await ac(bench).set_temperature(temperature=24.5)
    assert ac(bench).attr("temperature") == 24.5
    await bench.advance(15)
    assert aircon.temperature == 25.0


@spec("ENT-TGT-8", "ENT-RANGE-4")
async def test_ent_tgt_8_gap_applied_again_on_the_values_sent(bench: Bench) -> None:
    """A heat_cool source at 16–28, min_gap 2: kept 27 / 29, it gets 26 / 28."""
    radiator = bench.device(RADIATOR, ["heat"], min_temp=5.0, max_temp=32.0)
    aircon = bench.device(AIRCON, ["cool"], min_temp=5.0, max_temp=32.0)
    pump = bench.device(
        PUMP, ["heat_cool"], min_temp=16.0, max_temp=28.0, single_target=False,
        range_target=True, target_temp_low=20.0, target_temp_high=24.0,
    )
    await bench.start(
        [
            yaml_entry(
                "Living room",
                heat_entity=RADIATOR,
                cool_entity=AIRCON,
                heat_cool_entity=PUMP,
                min_gap=2,
            )
        ]
    )
    await discover((radiator, "heat"), (aircon, "cool"), (pump, "heat_cool"))
    await ac(bench).set_temperature(target_temp_low=27.0, target_temp_high=29.0)
    await ac(bench).set_hvac_mode("heat_cool")
    await bench.advance(15)
    assert (pump.target_temp_low, pump.target_temp_high) == (26.0, 28.0)


# --- ENT-TGT-9: taken from the source ---------------------------------------------------------------------


async def range_pump(bench: Bench) -> Any:
    pump = bench.device(
        PUMP, ["heat_cool"], single_target=False, range_target=True,
        target_temp_low=19.0, target_temp_high=24.0,
    )
    await bench.start([yaml_entry("Living room", heat_cool_entity=PUMP)])
    await ac(bench).set_hvac_mode("heat_cool")
    await bench.advance(15)
    return pump


@spec("ENT-TGT-9", "ENT-TGT-5")
async def test_ent_tgt_9_both_changed_are_taken_as_they_are(bench: Bench) -> None:
    pump = await range_pump(bench)
    await pump.set(target_temp_low=20.0, target_temp_high=20.5)
    # Both changed on the device: taken as they are, gap included
    assert low_high(bench) == (20.0, 20.5)
    assert pump.temperatures_asked() == []


@spec("ENT-TGT-9", "ENT-TGT-5")
async def test_ent_tgt_9_low_taken_pushes_high(bench: Bench) -> None:
    pump = await range_pump(bench)
    pump.clear_calls()
    await pump.set(target_temp_low=23.5)
    assert low_high(bench) == (23.5, 24.5)
    # The target moved is sent, with the one taken as the source shows it
    assert pump.temperatures_asked() == [{"target_temp_low": 23.5, "target_temp_high": 24.5}]
    assert (pump.target_temp_low, pump.target_temp_high) == (23.5, 24.5)


@spec("ENT-TGT-9", "ENT-TGT-5", "ENT-TGT-6")
async def test_ent_tgt_9_high_taken_pushes_low(bench: Bench) -> None:
    pump = await gap_pump(bench, 22.0, 26.0)
    await pump.set(target_temp_high=23.0)
    assert low_high(bench) == (21.0, 23.0)
    assert pump.temperatures_asked() == [{"target_temp_low": 21.0, "target_temp_high": 23.0}]


@spec("ENT-TGT-9", "ENT-TGT-5")
async def test_ent_tgt_9_taken_at_the_end_breaks_the_gap(bench: Bench) -> None:
    """High at the end of its range cannot move: the gap is broken, nothing is sent."""
    pump = await gap_pump(bench, 26.0, 30.0)
    await pump.set(target_temp_low=29.5)
    assert low_high(bench) == (29.5, 30.0)
    assert pump.temperatures_asked() == []


# --- ENT-TGT-10, ENT-TGT-11: first targets, shown ---------------------------------------------------------------


@spec("ENT-TGT-10", "ENT-TGT-11", "ENT-DATA-1")
async def test_ent_tgt_10_first_targets_taken_from_the_sources(bench: Bench) -> None:
    """T from the first source; low and high from the phase sources of heat_cool."""
    bench.device(HEATER, ["heat"], temperature=19.0)
    bench.device(AIRCON, ["cool"], temperature=25.0)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER, cool_entity=AIRCON)])
    assert low_high(bench) == (19.0, 25.0)
    assert sorted(numbers_in(ac(bench).attr("saved_targets"))) == [19.0, 19.0, 25.0]


@spec("ENT-TGT-10")
async def test_ent_tgt_10_low_high_of_the_heat_cool_source(bench: Bench) -> None:
    bench.device(HEATER, ["heat"], temperature=19.0)
    bench.device(
        PUMP, ["heat_cool"], single_target=False, range_target=True,
        target_temp_low=18.0, target_temp_high=26.0,
    )
    await bench.start([yaml_entry("Living room", heat_entity=HEATER, heat_cool_entity=PUMP)])
    pump = bench.devices[PUMP]
    await ac(bench).set_hvac_mode("heat_cool")  # discovered: the targets kept are shown
    await bench.advance(15)
    assert low_high(bench) == (18.0, 26.0)
    assert pump.temperatures_asked() == []


@spec("ENT-TGT-10")
async def test_ent_tgt_10_nothing_shown_middle_of_the_range(bench: Bench) -> None:
    bench.device(HEATER, ["heat"], single_target=False, temperature=None)
    bench.device(AIRCON, ["cool"], single_target=False, temperature=None)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER, cool_entity=AIRCON)])
    assert low_high(bench) == (20.0, 22.0)


@spec("ENT-TGT-11", "ENT-STATE-2")
async def test_ent_tgt_11_without_low_high_off_shows_the_target_of_turn_on(bench: Bench) -> None:
    await without_low_high(bench)
    await ac(bench).set_hvac_mode("cool")
    await ac(bench).set_temperature(temperature=24.0)
    await ac(bench).set_hvac_mode("off")
    assert ac(bench).attr("temperature") == 24.0
    assert low_high(bench) == (None, None)


# --- ENT-SET-2: settings from another source ---------------------------------------------------------------


@spec("ENT-SET-2")
async def test_ent_set_2_settings_of_a_source_not_active_are_ignored(bench: Bench) -> None:
    heater, aircon = await with_low_high(bench)
    await ac(bench).set_hvac_mode("heat")
    await aircon.set(temperature=18.0)
    assert ac(bench).attr("temperature") == 25.0
    await ac(bench).set_hvac_mode("off")
    assert low_high(bench) == (19.0, 25.0)


# --- More paths of the sending and the gap -----------------------------------------------------------


@spec("ENT-TGT-4", "ENT-TGT-9", "ENT-TGT-5", "ENT-FEAT-4")
async def test_ent_tgt_4_low_moves_when_high_is_at_the_end_of_its_range(bench: Bench) -> None:
    """Phase heat of the bi-source heat_cool: low taken at 30 °C from the heater, high
    at its maximum 30: the gap is broken. A change of the capabilities applies it
    again: high cannot move, low goes down to 29."""
    heater, aircon = await with_low_high(
        bench, heater={"min_temp": 5.0, "max_temp": 30.0},
        aircon={"min_temp": 16.0, "max_temp": 30.0},
    )
    await ac(bench).set_temperature(target_temp_low=19.0, target_temp_high=30.0)
    await ac(bench).set_hvac_mode("heat_cool")
    assert ac(bench).attr("phase") == "heat"
    await bench.advance(15)
    await heater.set(temperature=30.0)
    assert low_high(bench) == (30.0, 30.0)
    await heater.set(min_temp=6.0)
    assert low_high(bench) == (29.0, 30.0)


@spec("ENT-TGT-8")
async def test_ent_tgt_8_value_sent_never_leaves_the_range_of_the_source(bench: Bench) -> None:
    """Limits not on the step: rounding toward the inside."""
    heater = bench.device(HEATER, ["heat"], min_temp=15.4, max_temp=30.0, target_temp_step=1.0)
    aircon = bench.device(AIRCON, ["cool"], min_temp=16.0, max_temp=25.6, target_temp_step=1.0)
    await bench.start(
        [
            yaml_entry(
                "Living room",
                heat_entity=HEATER,
                cool_entity=AIRCON,
                heat_offset=-0.6,
                cool_offset=0.6,
            )
        ]
    )
    await discover((heater, "heat"), (aircon, "cool"))
    await ac(bench).set_hvac_mode("cool")
    await ac(bench).set_temperature(temperature=25.0)  # 25.6 for the aircon: 26 is out
    await bench.advance(15)
    assert aircon.temperature == 25.0
    await ac(bench).set_hvac_mode("heat")
    await ac(bench).set_temperature(temperature=16.0)  # 15.4 for the heater: 15 is out
    await bench.advance(15)
    assert heater.temperature == 16.0


@spec("ENT-TGT-8", "ENT-TGT-5")
async def test_ent_tgt_8_range_narrower_than_the_gap(bench: Bench) -> None:
    """A heat_cool source at 20–21 °C, min_gap 2: it gets the two ends of its range."""
    bench.device(RADIATOR, ["heat"], min_temp=5.0, max_temp=30.0)
    pump = bench.device(
        PUMP, ["heat_cool"], min_temp=20.0, max_temp=21.0, single_target=False,
        range_target=True, target_temp_low=20.5, target_temp_high=21.0,
    )
    await bench.start(
        [yaml_entry("Living room", heat_entity=RADIATOR, heat_cool_entity=PUMP, min_gap=2)]
    )
    await discover((bench.devices[RADIATOR], "heat"), (pump, "heat_cool"))
    await ac(bench).set_temperature(target_temp_low=18.0, target_temp_high=21.0)
    await ac(bench).set_hvac_mode("heat_cool")
    await bench.advance(15)
    assert (pump.target_temp_low, pump.target_temp_high) == (20.0, 21.0)


@spec("ENT-FEAT-4", "ENT-TGT-8", "ENT-TGT-6")
async def test_ent_feat_4_cool_on_a_low_high_source_uses_low_and_high(bench: Bench) -> None:
    """cool shows the low/high of its source; the gap moves high (ENT-TGT-6)."""
    aircon = bench.device(
        AIRCON, ["cool"], min_temp=16.0, max_temp=30.0, single_target=False,
        range_target=True, target_temp_low=19.0, target_temp_high=25.0,
    )
    await bench.start([yaml_entry("Living room", cool_entity=AIRCON)])
    await ac(bench).set_hvac_mode("cool")
    await bench.advance(15)
    assert low_high(bench) == (19.0, 25.0)
    assert ac(bench).attr("temperature") is None
    aircon.clear_calls()
    await ac(bench).set_temperature(target_temp_low=19.5, target_temp_high=19.5)
    assert low_high(bench) == (19.5, 20.5)
    assert aircon.temperatures_asked()[-1] == {"target_temp_low": 19.5, "target_temp_high": 20.5}
