"""Spec §3 Configuration: options, checks, UI and YAML (CFG-*), and ENT-INIT-4."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryState
import pytest

from dev.spec.harness import (
    Bench,
    created,
    error_text,
    errors_logged,
    refused,
    yaml_entry,
)

spec = pytest.mark.spec

HEATER = "climate.heater"  # heat only
AIRCON = "climate.aircon"  # cool only
PUMP = "climate.heat_pump"  # every mode
AWAY = "climate.away"  # cool only, unavailable
UNKNOWN = "climate.unknown"  # cool only, state unknown
NOT_LOADED = "climate.not_loaded"  # never in Home Assistant
ROOM = "sensor.room"  # °C
ROOM_F = "sensor.room_f"  # °F
ROOM_K = "sensor.room_k"  # K
TEMPLATE = "sensor.template"  # no unit
HUMIDITY = "sensor.humidity"  # %
EXT = "number.heater_external"
EXT2 = "input_number.pump_external"

ALL_MODES = ["heat", "cool", "heat_cool", "auto", "dry", "fan_only"]


def world(bench: Bench) -> None:
    """The devices and sensors the configurations name."""
    bench.device(HEATER, ["heat"])
    bench.device(AIRCON, ["cool"])
    bench.device(PUMP, ALL_MODES)
    bench.device(AWAY, ["cool"], available=False)
    bench.device(UNKNOWN, ["cool"], hvac_mode=None)
    bench.sensor(ROOM, 20.0)
    bench.sensor(ROOM_F, 68.0, unit="°F")
    bench.sensor(ROOM_K, 293.15, unit="K")
    bench.sensor(TEMPLATE, 20.0, unit=None, device_class=None)
    bench.sensor(HUMIDITY, 50, unit="%", device_class="humidity")
    bench.external(EXT)
    bench.external(EXT2)


def case(case_id: str, *rules: str, **options: Any) -> Any:
    """A configuration (without its name), tagged with the rules it checks."""
    return pytest.param(options, id=case_id, marks=spec(*rules))


async def ui_entry(bench: Bench, name: str, **options: Any) -> Any:
    result = await bench.create_entry(name=name, **options)
    assert created(result), result
    return result


async def heat_on(bench: Bench, name: str) -> None:
    """The user turns the entity on in heat; the heater follows."""
    await bench.ac(name).set_hvac_mode("heat")
    assert bench.ac(name).state == "heat"


# --- CFG-CHECK-1: refused configurations -------------------------------------------------

REFUSED = [
    case("offset above 10", "CFG-CHECK-1", heat_entity=HEATER, heat_offset=10.5),
    case("offset below -10", "CFG-CHECK-1", heat_entity=HEATER, heat_offset=-10.5),
    case("removal timer negative", "CFG-CHECK-1", heat_entity=HEATER, removal_confirmation_timer=-1),
    case("confirmation timer zero", "CFG-CHECK-1", heat_entity=HEATER, request_confirmation_timer=0),
    case("settle timer zero", "CFG-CHECK-1", heat_entity=HEATER, settle_timer=0),
    case("resend timer zero", "CFG-CHECK-1", heat_entity=HEATER, external_sensor_resend_timer=0),
    case("phase hysteresis negative", "CFG-CHECK-1", heat_entity=HEATER, phase_hysteresis=-1),
    case("monitoring gap zero", "CFG-CHECK-1", heat_entity=HEATER, monitoring_gap=0),
    case("monitoring delay negative", "CFG-CHECK-1", heat_entity=HEATER, monitoring_delay_timer=-1),
    case("min gap below 1", "CFG-CHECK-1", heat_entity=HEATER, min_gap=0.5),
    case("source entity not a climate", "CFG-CHECK-1", heat_entity=ROOM),
    case("temperature sensor not a sensor", "CFG-CHECK-1", heat_entity=HEATER, temperature_sensor=HEATER),
    case(
        "external sensor not a number",
        "CFG-CHECK-1",
        heat_entity=HEATER,
        temperature_sensor=ROOM,
        heat_external_sensor=TEMPLATE,
    ),
    case("sync_modes not a mode", "CFG-CHECK-1", heat_entity=HEATER, sync_modes=["boost"]),
    case(
        "temperature sensor not a temperature",
        "CFG-CHECK-1",
        "CFG-SENS-6",
        heat_entity=HEATER,
        temperature_sensor=HUMIDITY,
    ),
    case("no mode", "CFG-CHECK-1", "CFG-MODE-4", temperature_sensor=ROOM),
    case("source without its mode", "CFG-CHECK-1", "CFG-MODE-5", heat_entity=AIRCON),
    case(
        "phase source without its phase",
        "CFG-CHECK-1",
        "CFG-MODE-5",
        heat_entity=HEATER,
        cool_entity=HEATER,
    ),
    case(
        "mono-source heat_cool not offered",
        "CFG-CHECK-1",
        "CFG-MODE-5",
        heat_cool_entity=HEATER,
    ),
    case(
        "external sensor without temperature sensor",
        "CFG-CHECK-1",
        "CFG-SENS-2",
        heat_entity=HEATER,
        heat_external_sensor=EXT,
    ),
    case(
        "external sensor with an offset",
        "CFG-CHECK-1",
        "CFG-SENS-2",
        heat_entity=HEATER,
        temperature_sensor=ROOM,
        heat_external_sensor=EXT,
        heat_offset=1,
    ),
    case(
        "one source entity, two offsets",
        "CFG-CHECK-1",
        "CFG-SENS-4",
        heat_entity=PUMP,
        cool_entity=PUMP,
        heat_offset=1,
        cool_offset=2,
    ),
    case(
        "one source entity, two external sensors",
        "CFG-CHECK-1",
        "CFG-SENS-4",
        heat_entity=PUMP,
        cool_entity=PUMP,
        temperature_sensor=ROOM,
        heat_external_sensor=EXT,
        cool_external_sensor=EXT2,
    ),
    case(
        "one source entity, external sensor for one mode only",
        "CFG-CHECK-1",
        "CFG-SENS-4",
        heat_entity=PUMP,
        cool_entity=PUMP,
        temperature_sensor=ROOM,
        heat_external_sensor=EXT2,
    ),
    case(
        "retry shorter than confirmation",
        "CFG-CHECK-1",
        "CFG-TIMER-1",
        heat_entity=HEATER,
        request_confirmation_timer=60,
        request_retry_timer=59,
    ),
    case(
        "limits closer than min_gap",
        "CFG-CHECK-1",
        "CFG-LIM-1",
        heat_entity=HEATER,
        min_temp=18,
        max_temp=18.5,
    ),
    case(
        "limits closer than a larger min_gap",
        "CFG-CHECK-1",
        "CFG-LIM-1",
        heat_entity=HEATER,
        min_temp=18,
        max_temp=20,
        min_gap=3,
    ),
]


@pytest.mark.parametrize("options", REFUSED)
async def test_cfg_check_1_refused_in_the_ui(bench: Bench, options: dict[str, Any]) -> None:
    """The UI shows the error; the entry is not created."""
    world(bench)
    await bench.start()
    result = await bench.create_entry(name="Living room", **options)
    assert refused(result), result
    assert not bench.has_entry("Living room")


@spec("CFG-YAML-5")
@pytest.mark.parametrize("options", REFUSED)
async def test_cfg_check_1_refused_in_the_yaml(
    bench: Bench, caplog: pytest.LogCaptureFixture, options: dict[str, Any]
) -> None:
    """An invalid YAML entry is an error: not imported, the error is logged."""
    world(bench)
    await bench.start([yaml_entry("Living room", **options)])
    assert not bench.has_entry("Living room")
    assert errors_logged(caplog, "Living room")


# --- Accepted configurations ---------------------------------------------------------------

ACCEPTED = [
    case(
        "offsets at their bounds",
        "CFG-CHECK-1",
        heat_entity=HEATER,
        cool_entity=AIRCON,
        heat_offset=-10,
        cool_offset=10,
    ),
    case(
        "zero allowed for removal, monitoring delay, hysteresis",
        "CFG-CHECK-1",
        heat_entity=HEATER,
        removal_confirmation_timer=0,
        monitoring_delay_timer=0,
        phase_hysteresis=0,
    ),
    case(
        "retry equal to confirmation",
        "CFG-TIMER-1",
        heat_entity=HEATER,
        request_confirmation_timer=60,
        request_retry_timer=60,
    ),
    case("limits min_gap apart", "CFG-LIM-1", heat_entity=HEATER, min_temp=18, max_temp=19),
    case(
        "limits a larger min_gap apart",
        "CFG-LIM-1",
        heat_entity=HEATER,
        min_temp=18,
        max_temp=21,
        min_gap=3,
    ),
    case("only one limit", "CFG-LIM-1", heat_entity=HEATER, max_temp=24),
    case("sensor without unit", "CFG-SENS-6", heat_entity=HEATER, temperature_sensor=TEMPLATE),
    case("sensor in °F", "CFG-SENS-6", heat_entity=HEATER, temperature_sensor=ROOM_F),
    case("sensor in K", "CFG-SENS-6", heat_entity=HEATER, temperature_sensor=ROOM_K),
    case(
        "source entity not loaded",
        "CFG-MODE-5",
        "CFG-CHECK-3",
        heat_entity=NOT_LOADED,
    ),
    case("source entity unavailable", "CFG-MODE-5", "CFG-CHECK-3", heat_entity=AWAY),
    case("source entity unknown", "CFG-MODE-5", "CFG-CHECK-3", heat_entity=UNKNOWN),
    case(
        "one source entity, several modes, same offset",
        "CFG-MODE-1",
        "CFG-SENS-4",
        heat_entity=PUMP,
        cool_entity=PUMP,
        dry_entity=PUMP,
        heat_offset=1,
        cool_offset=1,
        dry_offset=1,
    ),
    case(
        "one source entity, several modes, same external sensor",
        "CFG-SENS-4",
        heat_entity=PUMP,
        cool_entity=PUMP,
        temperature_sensor=ROOM,
        heat_external_sensor=EXT2,
        cool_external_sensor=EXT2,
    ),
    case(
        "offset of a mode without source entity",
        "CFG-CHECK-2",
        "CFG-SENS-3",
        heat_entity=HEATER,
        cool_offset=3,
    ),
    case(
        "external sensor and offset of a mode without source entity",
        "CFG-CHECK-2",
        "CFG-SENS-3",
        heat_entity=HEATER,
        temperature_sensor=ROOM,
        cool_external_sensor=EXT,
        cool_offset=2,
    ),
    case(
        "external sensor and offset of a bi-source heat_cool",
        "CFG-CHECK-2",
        "CFG-SENS-3",
        heat_entity=HEATER,
        cool_entity=AIRCON,
        temperature_sensor=ROOM,
        heat_cool_external_sensor=EXT,
        heat_cool_offset=3,
    ),
    case(
        "bi-source heat_cool not counted in the consistency",
        "CFG-SENS-4",
        heat_entity=PUMP,
        cool_entity=PUMP,
        heat_offset=1,
        cool_offset=1,
        heat_cool_offset=4,
    ),
    case(
        "sync_modes with a mode without source entity",
        "CFG-CHECK-2",
        "CFG-FAN-1",
        heat_entity=HEATER,
        sync_modes=["heat", "dry"],
    ),
    case(
        "bi_source_sync without bi-source heat_cool",
        "CFG-CHECK-2",
        "CFG-FAN-2",
        heat_entity=HEATER,
        bi_source_sync=True,
    ),
    case(
        "bi-source heat_cool in sync_modes",
        "CFG-CHECK-3",
        "CFG-FAN-1",
        heat_entity=HEATER,
        cool_entity=AIRCON,
        sync_modes=["heat", "heat_cool"],
    ),
]


@pytest.mark.parametrize("options", ACCEPTED)
async def test_accepted_in_the_ui(bench: Bench, options: dict[str, Any]) -> None:
    """The entry is created and loaded."""
    world(bench)
    await bench.start()
    await ui_entry(bench, "Living room", **options)
    assert bench.entry("Living room").state is ConfigEntryState.LOADED
    assert bench.ac("Living room").exists


@spec("CFG-YAML-1")
@pytest.mark.parametrize("options", ACCEPTED)
async def test_accepted_in_the_yaml(
    bench: Bench, caplog: pytest.LogCaptureFixture, options: dict[str, Any]
) -> None:
    """The YAML entry is imported as a config entry, and loaded."""
    world(bench)
    await bench.start([yaml_entry("Living room", **options)])
    assert bench.entry("Living room").state is ConfigEntryState.LOADED
    assert bench.ac("Living room").exists
    assert not errors_logged(caplog, "Living room")


# --- Error messages ------------------------------------------------------------------------


@spec("CFG-SENS-4")
async def test_cfg_sens_4_error_names_the_modes_in_the_ui(bench: Bench) -> None:
    world(bench)
    await bench.start()
    result = await bench.create_entry(
        name="Living room", heat_entity=PUMP, cool_entity=PUMP, heat_offset=1, cool_offset=2
    )
    assert refused(result)
    text = error_text(result)
    assert "heat" in text
    assert "cool" in text


@spec("CFG-SENS-4", "CFG-YAML-5")
async def test_cfg_sens_4_error_names_the_modes_in_the_log(
    bench: Bench, caplog: pytest.LogCaptureFixture
) -> None:
    world(bench)
    entry = yaml_entry("Living room", heat_entity=PUMP, cool_entity=PUMP, heat_offset=1, cool_offset=2)
    await bench.start([entry])
    assert errors_logged(caplog, "Living room", "heat", "cool")


# --- CFG-SENS-5: one source entity in several entries ----------------------------------------


@spec("CFG-SENS-5", "CFG-CHECK-1")
async def test_cfg_sens_5_other_entry_with_another_offset_is_refused(bench: Bench) -> None:
    world(bench)
    await bench.start()
    await ui_entry(bench, "Living room", heat_entity=PUMP, heat_offset=1)
    result = await bench.create_entry(name="Office", cool_entity=PUMP, cool_offset=2)
    assert refused(result)
    text = error_text(result)
    assert "Living room" in text
    assert "heat" in text
    assert not bench.has_entry("Office")


@spec("CFG-SENS-5", "CFG-MODE-1")
async def test_cfg_sens_5_other_entry_with_the_same_offset_is_accepted(bench: Bench) -> None:
    world(bench)
    await bench.start()
    await ui_entry(bench, "Living room", heat_entity=PUMP, heat_offset=1)
    await ui_entry(bench, "Office", cool_entity=PUMP, cool_offset=1)
    assert bench.entry("Office").state is ConfigEntryState.LOADED


@spec("CFG-SENS-5", "CFG-CHECK-1")
async def test_cfg_sens_5_other_entry_without_the_external_sensor_is_refused(bench: Bench) -> None:
    world(bench)
    await bench.start()
    await ui_entry(
        bench, "Living room", heat_entity=PUMP, temperature_sensor=ROOM, heat_external_sensor=EXT2
    )
    result = await bench.create_entry(name="Office", cool_entity=PUMP)
    assert refused(result)
    assert "Living room" in error_text(result)


@spec("CFG-SENS-5", "CFG-YAML-5")
async def test_cfg_sens_5_in_the_yaml(bench: Bench, caplog: pytest.LogCaptureFixture) -> None:
    world(bench)
    living = yaml_entry("Living room", heat_entity=PUMP, heat_offset=1)
    await bench.start([living])
    await bench.restart([living, yaml_entry("Office", cool_entity=PUMP, cool_offset=2)])
    assert not bench.has_entry("Office")
    assert errors_logged(caplog, "Office", "Living room")
    assert bench.entry("Living room").state is ConfigEntryState.LOADED


# --- CFG-MODE-2: an AC entity is not a source entity -------------------------------------------


@spec("CFG-MODE-2", "CFG-CHECK-1")
async def test_cfg_mode_2_ac_entity_of_another_entry_is_refused(bench: Bench) -> None:
    world(bench)
    await bench.start()
    await ui_entry(bench, "Living room", heat_entity=HEATER)
    result = await bench.create_entry(name="Office", heat_entity="climate.living_room")
    assert refused(result)
    assert not bench.has_entry("Office")


@spec("CFG-MODE-2", "CFG-CHECK-1")
async def test_cfg_mode_2_its_own_ac_entity_is_refused(bench: Bench) -> None:
    world(bench)
    await bench.start()
    await ui_entry(bench, "Living room", heat_entity=HEATER)
    result = await bench.change_options("Living room", cool_entity="climate.living_room")
    assert refused(result)
    assert bench.ac("Living room").attr("hvac_modes") == ["off", "heat"]


@spec("CFG-MODE-2", "CFG-YAML-5")
async def test_cfg_mode_2_in_the_yaml(bench: Bench, caplog: pytest.LogCaptureFixture) -> None:
    world(bench)
    living = yaml_entry("Living room", heat_entity=HEATER)
    await bench.start([living])
    await bench.restart([living, yaml_entry("Office", heat_entity="climate.living_room")])
    assert not bench.has_entry("Office")
    assert errors_logged(caplog, "Office")


# --- CFG-MODE-3, ENT-HVAC-1: the modes follow the configuration ---------------------------------


@spec("CFG-MODE-3", "ENT-HVAC-1")
@pytest.mark.parametrize(
    ("options", "listed"),
    [
        pytest.param({"heat_entity": HEATER}, ["off", "heat"], id="heat"),
        pytest.param(
            {"heat_entity": HEATER, "cool_entity": AIRCON},
            ["off", "heat", "cool", "heat_cool"],
            id="heat and cool: bi-source heat_cool",
        ),
        pytest.param(
            {"heat_entity": HEATER, "cool_entity": AIRCON, "heat_cool_entity": PUMP},
            ["off", "heat", "cool", "heat_cool"],
            id="heat, cool and heat_cool: mono-source heat_cool",
        ),
        pytest.param(
            {
                "fan_only_entity": PUMP,
                "dry_entity": PUMP,
                "auto_entity": PUMP,
                "heat_cool_entity": PUMP,
                "cool_entity": PUMP,
                "heat_entity": PUMP,
            },
            ["off", "heat", "cool", "heat_cool", "auto", "dry", "fan_only"],
            id="every mode, in mode order",
        ),
        pytest.param({"dry_entity": PUMP}, ["off", "dry"], id="dry"),
    ],
)
async def test_cfg_mode_3_modes_listed(
    bench: Bench, options: dict[str, Any], listed: list[str]
) -> None:
    world(bench)
    await bench.start([yaml_entry("Living room", **options)])
    assert bench.ac("Living room").attr("hvac_modes") == listed


@spec("CFG-MODE-3")
async def test_cfg_mode_3_mono_source_heat_cool_uses_its_source(bench: Bench) -> None:
    """With heat_cool_entity, heat_cool is mono-source: its own source runs it."""
    world(bench)
    await bench.start(
        [yaml_entry("Living room", heat_entity=HEATER, cool_entity=AIRCON, heat_cool_entity=PUMP)]
    )
    await bench.ac("Living room").set_hvac_mode("heat_cool")
    assert bench.devices[PUMP].modes_asked() == ["heat_cool"]
    assert bench.devices[HEATER].modes_asked() in ([], ["off"])
    assert bench.devices[AIRCON].modes_asked() in ([], ["off"])


@spec("CFG-MODE-3")
async def test_cfg_mode_3_bi_source_heat_cool_uses_the_phase_sources(bench: Bench) -> None:
    """Without heat_cool_entity, heat_cool runs on the heat or the cool source."""
    world(bench)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER, cool_entity=AIRCON)])
    await bench.ac("Living room").set_hvac_mode("heat_cool")
    asked = bench.devices[HEATER].modes_asked() + bench.devices[AIRCON].modes_asked()
    assert "heat" in asked or "cool" in asked
    assert "heat_cool" not in asked
    assert bench.ac("Living room").state == "heat_cool"


@spec("CFG-MODE-3")
async def test_mode_entity_ids_lists_the_modes_with_their_own_source(bench: Bench) -> None:
    """`mode_entity_ids` (§2.2): a bi-source heat_cool has no source of its own."""
    world(bench)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER, cool_entity=AIRCON)])
    assert bench.ac("Living room").attr("mode_entity_ids") == {"heat": HEATER, "cool": AIRCON}


# --- CFG-NAME-1, CFG-YAML-2: unique names -----------------------------------------------------------


@spec("CFG-NAME-1", "CFG-CHECK-1")
async def test_cfg_name_1_name_used_in_the_ui_is_refused_ignoring_case(bench: Bench) -> None:
    world(bench)
    await bench.start()
    await ui_entry(bench, "Living room", heat_entity=HEATER)
    result = await bench.create_entry(name="living ROOM", cool_entity=AIRCON)
    assert refused(result)
    assert len(bench.entries()) == 1


@spec("CFG-NAME-1", "CFG-CHECK-1")
async def test_cfg_name_1_name_of_a_yaml_entry_is_refused_in_the_ui(bench: Bench) -> None:
    world(bench)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    result = await bench.create_entry(name="LIVING room", cool_entity=AIRCON)
    assert refused(result)
    assert len(bench.entries()) == 1


@spec("CFG-NAME-1", "CFG-YAML-5", "CFG-YAML-4")
async def test_cfg_name_1_yaml_entry_with_a_name_of_the_ui_is_not_imported(
    bench: Bench, caplog: pytest.LogCaptureFixture
) -> None:
    world(bench)
    await bench.start()
    await ui_entry(bench, "Living room", heat_entity=HEATER)
    await heat_on(bench, "Living room")
    await bench.restart([yaml_entry("living room", cool_entity=AIRCON)])
    assert len(bench.entries()) == 1
    entry = bench.entry("Living room")
    assert entry.source == "user"
    assert entry.state is ConfigEntryState.LOADED
    assert bench.ac("Living room").state == "heat"
    assert bench.devices[AIRCON].calls == []
    assert errors_logged(caplog, "living room")


@spec("CFG-YAML-2", "CFG-NAME-1", "CFG-YAML-5")
async def test_cfg_yaml_2_two_yaml_entries_with_one_name_are_refused(
    bench: Bench, caplog: pytest.LogCaptureFixture
) -> None:
    world(bench)
    await bench.start(
        [
            yaml_entry("Living room", heat_entity=HEATER),
            yaml_entry("LIVING ROOM", cool_entity=AIRCON),
            yaml_entry("Office", dry_entity=PUMP),
        ]
    )
    assert [entry.title for entry in bench.entries()] == ["Office"]
    assert errors_logged(caplog, "Living room")


# --- CFG-YAML-1, CFG-YAML-3: the YAML wins over the UI ---------------------------------------------


@spec("CFG-YAML-1")
async def test_cfg_yaml_1_yaml_entry_is_a_config_entry(bench: Bench) -> None:
    world(bench)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER, cool_entity=AIRCON)])
    entry = bench.entry("Living room")
    assert entry.state is ConfigEntryState.LOADED
    ac = bench.ac("Living room")
    assert ac.attr("hvac_modes") == ["off", "heat", "cool", "heat_cool"]
    assert ac.attr("mode_entity_ids") == {"heat": HEATER, "cool": AIRCON}


@spec("CFG-YAML-3")
async def test_cfg_yaml_3_imported_entry_has_no_options(bench: Bench) -> None:
    world(bench)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    await ui_entry(bench, "Office", cool_entity=AIRCON)
    assert not bench.has_options("Living room")
    assert bench.has_options("Office")


@spec("CFG-YAML-3", "ENT-INIT-4")
async def test_cfg_yaml_3_changed_yaml_entry_is_updated_and_off(bench: Bench) -> None:
    """An entry changed in the YAML is updated as by the options: the entity is OFF."""
    world(bench)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    await heat_on(bench, "Living room")
    heater = bench.devices[HEATER]
    heater.clear_calls()
    await bench.restart([yaml_entry("Living room", heat_entity=HEATER, temperature_sensor=ROOM)])
    ac = bench.ac("Living room")
    assert ac.state == "off"
    assert heater.modes_asked() == ["off"]
    assert heater.hvac_mode == "off"
    assert len(bench.entries()) == 1


@spec("CFG-YAML-1", "ENT-INIT-4", "END-2")
async def test_cfg_yaml_1_unchanged_yaml_entry_resumes(bench: Bench) -> None:
    """A YAML entry imported again unchanged is a restart: the stored mode is resumed."""
    world(bench)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    await heat_on(bench, "Living room")
    await bench.restart()
    assert bench.ac("Living room").state == "heat"
    assert bench.devices[HEATER].hvac_mode == "heat"


@spec("CFG-YAML-3", "END-3")
async def test_cfg_yaml_3_entry_removed_from_the_yaml_is_deleted(bench: Bench) -> None:
    world(bench)
    await bench.start(
        [yaml_entry("Living room", heat_entity=HEATER), yaml_entry("Office", cool_entity=AIRCON)]
    )
    await heat_on(bench, "Living room")
    heater = bench.devices[HEATER]
    heater.clear_calls()
    await bench.restart([yaml_entry("Office", cool_entity=AIRCON)])
    assert [entry.title for entry in bench.entries()] == ["Office"]
    assert not bench.ac("Living room").exists
    # The source entity is left as it is
    assert heater.calls == []
    assert heater.hvac_mode == "heat"


@spec("CFG-YAML-5", "CFG-YAML-3", "END-1")
async def test_cfg_yaml_5_invalid_yaml_keeps_the_entry_not_loaded(
    bench: Bench, caplog: pytest.LogCaptureFixture
) -> None:
    world(bench)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    await heat_on(bench, "Living room")
    heater = bench.devices[HEATER]
    heater.clear_calls()
    await bench.restart([yaml_entry("Living room", heat_entity=HEATER, heat_offset=50)])
    entry = bench.entry("Living room")
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entry.reason  # Home Assistant shows the error
    assert not bench.ac("Living room").available
    assert errors_logged(caplog, "Living room")
    # Not managed: its source entity is left as it is
    await bench.advance(60)
    assert heater.calls == []
    assert heater.hvac_mode == "heat"


@spec("CFG-YAML-5", "END-2")
async def test_cfg_yaml_5_entry_back_to_its_valid_yaml_resumes(bench: Bench) -> None:
    world(bench)
    living = yaml_entry("Living room", heat_entity=HEATER)
    await bench.start([living])
    await heat_on(bench, "Living room")
    await bench.restart([yaml_entry("Living room", heat_entity=HEATER, heat_offset=50)])
    await bench.restart([living])
    assert bench.entry("Living room").state is ConfigEntryState.LOADED
    assert bench.ac("Living room").state == "heat"


@spec("CFG-YAML-5", "ENT-INIT-4")
async def test_cfg_yaml_5_entry_back_with_another_valid_yaml_is_updated(bench: Bench) -> None:
    world(bench)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    await heat_on(bench, "Living room")
    await bench.restart([yaml_entry("Living room", heat_entity=HEATER, heat_offset=50)])
    await bench.restart([yaml_entry("Living room", heat_entity=HEATER, heat_offset=1)])
    assert bench.entry("Living room").state is ConfigEntryState.LOADED
    assert bench.ac("Living room").state == "off"
    assert bench.devices[HEATER].hvac_mode == "off"


@spec("CFG-YAML-4", "CFG-YAML-5")
async def test_cfg_yaml_4_ui_entries_are_not_affected_by_the_yaml(bench: Bench) -> None:
    world(bench)
    await bench.start([yaml_entry("Office", cool_entity=AIRCON)])
    await ui_entry(bench, "Living room", heat_entity=HEATER)
    await heat_on(bench, "Living room")
    # The YAML changes, then becomes invalid, then is gone
    await bench.restart([yaml_entry("Office", cool_entity=AIRCON, cool_offset=1)])
    await bench.restart([yaml_entry("Office", cool_entity=AIRCON, cool_offset=50)])
    await bench.restart([])
    entry = bench.entry("Living room")
    assert entry.state is ConfigEntryState.LOADED
    assert bench.ac("Living room").state == "heat"
    assert not bench.has_entry("Office")


@spec("CFG-MODE-5", "CFG-CHECK-1", "CFG-YAML-1")
async def test_cfg_mode_5_nothing_refused_at_a_start_with_an_unchanged_yaml(bench: Bench) -> None:
    """A mode lost meanwhile is handled while running: the entry and its data are kept."""
    world(bench)
    living = yaml_entry("Living room", heat_entity=HEATER)
    await bench.start([living])
    await bench.stop()
    bench.devices[HEATER].hvac_modes = ["off", "cool"]
    await bench.start([living])
    assert bench.entry("Living room").state is ConfigEntryState.LOADED
    assert bench.ac("Living room").exists


@spec("CFG-MODE-5", "CFG-YAML-5")
async def test_cfg_mode_5_changed_yaml_is_checked_against_the_source(
    bench: Bench, caplog: pytest.LogCaptureFixture
) -> None:
    world(bench)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    await bench.stop()
    bench.devices[HEATER].hvac_modes = ["off", "cool"]
    await bench.start([yaml_entry("Living room", heat_entity=HEATER, heat_offset=1)])
    assert bench.entry("Living room").state is ConfigEntryState.SETUP_ERROR
    assert errors_logged(caplog, "Living room")


@spec("CFG-NAME-2", "CFG-YAML-3", "END-3")
async def test_cfg_name_2_renaming_a_yaml_entry_starts_a_new_entry(bench: Bench) -> None:
    world(bench)
    await bench.start([yaml_entry("Living room", heat_entity=HEATER)])
    await heat_on(bench, "Living room")
    old_id = bench.entry("Living room").entry_id
    heater = bench.devices[HEATER]
    heater.clear_calls()
    await bench.restart([yaml_entry("Lounge", heat_entity=HEATER)])
    assert [entry.title for entry in bench.entries()] == ["Lounge"]
    assert bench.entry("Lounge").entry_id != old_id
    assert not bench.ac("Living room").exists
    # A first start: no stored mode, the entity is OFF and turns its source off
    assert bench.ac("Lounge").state == "off"
    assert heater.modes_asked() == ["off"]


# --- Options flow (CFG-YAML-4, ENT-INIT-4) -------------------------------------------------------


@spec("CFG-YAML-4", "ENT-INIT-4")
async def test_options_change_reloads_the_entry_off(bench: Bench) -> None:
    world(bench)
    await bench.start()
    await ui_entry(bench, "Living room", heat_entity=HEATER)
    await heat_on(bench, "Living room")
    heater = bench.devices[HEATER]
    heater.clear_calls()
    result = await bench.change_options("Living room", temperature_sensor=ROOM)
    assert created(result)
    assert bench.ac("Living room").state == "off"
    assert heater.modes_asked() == ["off"]


@spec("CFG-YAML-4")
async def test_options_replace_the_whole_configuration(bench: Bench) -> None:
    """The form shows the configuration; an option cleared is gone."""
    world(bench)
    await bench.start()
    await ui_entry(bench, "Living room", heat_entity=HEATER, cool_entity=AIRCON, heat_offset=2)
    result = await bench.change_options("Living room", cool_entity=None)
    assert created(result)
    ac = bench.ac("Living room")
    assert ac.attr("hvac_modes") == ["off", "heat"]
    assert ac.attr("mode_entity_ids") == {"heat": HEATER}


@spec("CFG-CHECK-1", "CFG-TIMER-1")
async def test_refused_options_are_not_applied(bench: Bench) -> None:
    world(bench)
    await bench.start()
    await ui_entry(bench, "Living room", heat_entity=HEATER)
    await heat_on(bench, "Living room")
    heater = bench.devices[HEATER]
    heater.clear_calls()
    result = await bench.change_options(
        "Living room", request_confirmation_timer=60, request_retry_timer=10
    )
    assert refused(result)
    assert bench.ac("Living room").state == "heat"
    assert heater.calls == []


@spec("ENT-INIT-4", "END-2")
async def test_reload_without_change_resumes(bench: Bench) -> None:
    world(bench)
    await bench.start()
    await ui_entry(bench, "Living room", heat_entity=HEATER)
    await heat_on(bench, "Living room")
    await bench.reload("Living room")
    assert bench.ac("Living room").state == "heat"
    assert bench.devices[HEATER].hvac_mode == "heat"


@spec("ENT-INIT-4", "END-2")
async def test_ui_entry_resumes_after_a_restart(bench: Bench) -> None:
    world(bench)
    await bench.start()
    await ui_entry(bench, "Living room", heat_entity=HEATER)
    await heat_on(bench, "Living room")
    await bench.restart()
    assert bench.ac("Living room").state == "heat"


# --- CFG-UNIT-1: options in the unit of Home Assistant ---------------------------------------------

REFUSED_F = [
    case("offset above 18 °F", "CFG-UNIT-1", heat_entity=HEATER, heat_offset=18.5),
    case("min gap below 2 °F", "CFG-UNIT-1", heat_entity=HEATER, min_gap=1.5),
    case(
        "limits closer than 2 °F",
        "CFG-UNIT-1",
        "CFG-LIM-1",
        heat_entity=HEATER,
        min_temp=60,
        max_temp=61,
    ),
]

ACCEPTED_F = [
    case("offset at 18 °F", "CFG-UNIT-1", heat_entity=HEATER, heat_offset=18),
    case("min gap at 2 °F", "CFG-UNIT-1", heat_entity=HEATER, min_gap=2),
    case(
        "limits 2 °F apart",
        "CFG-UNIT-1",
        "CFG-LIM-1",
        heat_entity=HEATER,
        min_temp=60,
        max_temp=62,
    ),
]


@pytest.mark.parametrize("options", REFUSED_F)
async def test_cfg_unit_1_refused_in_fahrenheit(bench: Bench, options: dict[str, Any]) -> None:
    world(bench)
    bench.fahrenheit()
    await bench.start()
    assert refused(await bench.create_entry(name="Living room", **options))
    await bench.restart([yaml_entry("Living room", **options)])
    assert not bench.has_entry("Living room")


@pytest.mark.parametrize("options", ACCEPTED_F)
async def test_cfg_unit_1_accepted_in_fahrenheit(bench: Bench, options: dict[str, Any]) -> None:
    world(bench)
    bench.fahrenheit()
    await bench.start()
    await ui_entry(bench, "Living room", **options)
    await bench.restart([yaml_entry("Office", **options)])
    assert bench.entry("Office").state is ConfigEntryState.LOADED
