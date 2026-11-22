"""Spec §2 Entities and attributes, and the Home Assistant versions (ENT-HA)."""

from __future__ import annotations

from homeassistant.components.climate import ClimateEntityFeature
import pytest

from dev.spec.harness import Bench, yaml_entry

spec = pytest.mark.spec

HEATER = "climate.heater"
PUMP = "climate.heat_pump"
ROOM = "sensor.room"


def heater(bench: Bench, **values: object) -> None:
    bench.device(HEATER, ["heat"], **values)


def range_pump(bench: Bench) -> None:
    """A heat pump that shows low/high in heat_cool."""
    bench.device(
        PUMP,
        ["heat", "cool", "heat_cool"],
        target_temp_low=19.0,
        target_temp_high=25.0,
        profiles={
            "heat_cool": {"single_target": False, "range_target": True},
            "heat": {"single_target": True, "range_target": False},
            "cool": {"single_target": True, "range_target": False},
        },
    )


# --- §2.1 Entities created -------------------------------------------------------------------


async def test_entities_of_an_entry_are_named_after_it(bench: Bench) -> None:
    """One AC entity and two monitoring binary sensors per entry (§2.1)."""
    heater(bench)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    ac = bench.ac("Living room")
    assert ac.entity_id == "climate.living_room"
    assert ac.exists
    for sensor in (ac.monitoring_sources, ac.monitoring_temperatures):
        assert sensor.exists
        assert sensor.attr("device_class") == "problem"


async def test_entity_ids_do_not_follow_the_language(bench: Bench) -> None:
    """Home Assistant in French: the names shown are translated, not the entity ids (§2.1)."""
    heater(bench)
    await bench.start()
    bench.hass.config.language = "fr"
    result = await bench.create_entry(name="Living room", heat_entity=HEATER)
    assert result["type"] == "create_entry"
    ac = bench.ac("Living room")
    assert ac.exists
    for sensor in (ac.monitoring_sources, ac.monitoring_temperatures):
        assert sensor.exists, sensor.entity_id


async def test_each_entry_has_its_own_entities(bench: Bench) -> None:
    heater(bench)
    bench.device("climate.aircon", ["cool"])
    await bench.start(
        [
            yaml_entry("Living room", heat_entity=HEATER),
            yaml_entry("Office", cool_entity="climate.aircon"),
        ]
    )
    for name in ("Living room", "Office"):
        ac = bench.ac(name)
        assert ac.exists
        assert ac.monitoring_sources.exists
        assert ac.monitoring_temperatures.exists


@spec("MON-SENS-4", "ENT-NOSRC-2")
async def test_monitoring_sensors_available_while_the_ac_entity_is_not(bench: Bench) -> None:
    """No source ever seen: the AC entity is unavailable, its monitoring sensors are not."""
    await bench.start([yaml_entry("Living room", heat_entity="climate.not_loaded")])
    ac = bench.ac("Living room")
    assert ac.state == "unavailable"
    assert ac.monitoring_sources.available
    assert ac.monitoring_temperatures.available


# --- §2.2 Attributes of the AC entity ------------------------------------------------------------


@spec("ENT-OFF-1", "ENT-HVAC-1")
async def test_attributes_shown_in_off(bench: Bench) -> None:
    heater(bench)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    ac = bench.ac("Living room")
    assert ac.state == "off"
    assert ac.attr("hvac_modes") == ["off", "heat"]
    assert ac.attr("hvac_action") == "off"
    assert ac.attr("active_entity_id") is None
    assert ac.attr("phase") is None
    assert ac.attr("mode_entity_ids") == {"heat": HEATER}
    assert ac.attr("unavailable_modes") == []
    assert ac.attr("foreign_modes") == {}
    for extra in ("saved_targets", "saved_settings", "target_gaps", "min_gap"):
        assert extra in ac.attributes, extra
    assert ac.attr("min_gap") == 1.0  # the default (§3.1.6)


@spec("ENT-ON-1")
async def test_active_entity_id_is_the_source_of_the_mode(bench: Bench) -> None:
    heater(bench, hvac_action="heating")
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    ac = bench.ac("Living room")
    await ac.set_hvac_mode("heat")
    assert ac.state == "heat"
    assert ac.attr("active_entity_id") == HEATER
    assert ac.attr("hvac_action") == "heating"


# --- ENT-HA-1: temperatures shown by Home Assistant ----------------------------------------------


@spec("ENT-HA-1")
async def test_ent_ha_1_single_target_and_current_temperature(bench: Bench) -> None:
    heater(bench)
    bench.sensor(ROOM, 21.5)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER, temperature_sensor=ROOM)])
    ac = bench.ac("Living room")
    await ac.set_hvac_mode("heat")
    await ac.set_temperature(temperature=22.0)
    assert ac.attr("current_temperature") == 21.5
    assert ac.attr("temperature") == 22.0
    assert ac.features & ClimateEntityFeature.TARGET_TEMPERATURE
    await bench.advance(15)
    assert bench.devices[HEATER].temperature == 22.0


@spec("ENT-HA-1")
async def test_ent_ha_1_low_and_high_targets(bench: Bench) -> None:
    range_pump(bench)
    await bench.start([yaml_entry("Living room", heat_cool_entity=PUMP)])
    ac = bench.ac("Living room")
    await ac.set_hvac_mode("heat_cool")
    await ac.set_temperature(target_temp_low=18.0, target_temp_high=24.0)
    assert ac.attr("target_temp_low") == 18.0
    assert ac.attr("target_temp_high") == 24.0
    assert ac.features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    await bench.advance(15)
    pump = bench.devices[PUMP]
    assert (pump.target_temp_low, pump.target_temp_high) == (18.0, 24.0)


@spec("ENT-HA-1", "CFG-UNIT-1")
async def test_ent_ha_1_in_fahrenheit(bench: Bench) -> None:
    """Home Assistant in °F: the entity shows its values in °F, without converting them twice."""
    heater(bench, unit="°F", current_temperature=68.0, temperature=68.0, min_temp=45, max_temp=95)
    bench.sensor(ROOM, 70.0, unit="°F")
    bench.fahrenheit()
    await bench.start([yaml_entry("Living room", heat_entity=HEATER, temperature_sensor=ROOM)])
    ac = bench.ac("Living room")
    await ac.set_hvac_mode("heat")
    await ac.set_temperature(temperature=72.0)
    assert ac.attr("current_temperature") == 70.0
    assert ac.attr("temperature") == 72.0
    await bench.advance(15)
    assert bench.devices[HEATER].temperature == 72.0
