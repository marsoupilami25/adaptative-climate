"""Tests for the YAML configuration of Adaptative Climate."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.climate import HVACMode
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_NAME, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from custom_components.adaptative_climate.config_flow import AdaptativeClimateConfigFlow
from custom_components.adaptative_climate.const import (
    CONF_COOL_ENTITY,
    CONF_HEAT_ENTITY,
    CONF_MAX_TEMP,
    CONF_MIN_GAP,
    CONF_MIN_PHASE_DURATION,
    CONF_MIN_TEMP,
    CONF_SYNC_MODES,
    DOMAIN,
)

from .conftest import AC, ENTITY_ID, HEATER

pytestmark = pytest.mark.usefixtures("sources")

YAML_ENTRY = {CONF_NAME: "Living room", CONF_HEAT_ENTITY: HEATER, CONF_COOL_ENTITY: AC}

# What the import stores: the YAML entry as it is (limits are optional).
IMPORTED_DATA = YAML_ENTRY


async def _setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the integration from a YAML config and wait for the imports."""
    result = await async_setup_component(hass, DOMAIN, config)
    await hass.async_block_till_done()
    return result


def _imported_entry(
    unique_id: str = "Living room", data: dict[str, Any] | None = None, **kwargs: Any
) -> MockConfigEntry:
    """Return an entry as a previous YAML import created it."""
    return MockConfigEntry(
        domain=DOMAIN,
        source=SOURCE_IMPORT,
        unique_id=unique_id,
        title=unique_id,
        data=data or {**IMPORTED_DATA, CONF_NAME: unique_id},
        **kwargs,
    )


async def test_import_creates_entry(hass: HomeAssistant) -> None:
    """A YAML entry becomes a loaded config entry with a working entity."""
    assert await _setup(hass, {DOMAIN: [YAML_ENTRY]})

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.source == SOURCE_IMPORT
    assert entry.unique_id == "Living room"
    assert entry.title == "Living room"
    assert entry.data == IMPORTED_DATA
    assert entry.state is ConfigEntryState.LOADED

    state = hass.states.get(ENTITY_ID)
    assert state.state == HVACMode.OFF
    assert state.attributes["hvac_modes"] == [
        HVACMode.OFF,
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.HEAT_COOL,
    ]


async def test_import_sync_modes(hass: HomeAssistant) -> None:
    """sync_modes is imported as a list, a single mode included."""
    assert await _setup(hass, {DOMAIN: [{**YAML_ENTRY, CONF_SYNC_MODES: "cool"}]})

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.data == {**IMPORTED_DATA, CONF_SYNC_MODES: ["cool"]}
    assert entry.runtime_data.sync_modes == {HVACMode.COOL}


async def test_import_single_entry_without_list(hass: HomeAssistant) -> None:
    """One entry can be written without a list."""
    assert await _setup(hass, {DOMAIN: YAML_ENTRY})

    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_import_several_entries(hass: HomeAssistant) -> None:
    """Each YAML entry gets its own config entry."""
    assert await _setup(
        hass,
        {DOMAIN: [YAML_ENTRY, {CONF_NAME: "Bedroom", CONF_HEAT_ENTITY: HEATER}]},
    )

    titles = sorted(e.title for e in hass.config_entries.async_entries(DOMAIN))
    assert titles == ["Bedroom", "Living room"]


async def test_import_updates_existing_entry(hass: HomeAssistant) -> None:
    """A changed YAML entry updates its config entry instead of adding one."""
    entry = _imported_entry()
    entry.add_to_hass(hass)

    # The cool source is removed and the maximum lowered.
    heat_only = {CONF_NAME: "Living room", CONF_HEAT_ENTITY: HEATER}
    assert await _setup(hass, {DOMAIN: [{**heat_only, CONF_MAX_TEMP: 28}]})

    assert hass.config_entries.async_entries(DOMAIN) == [entry]
    assert entry.data == {**heat_only, CONF_MAX_TEMP: 28.0}
    assert entry.state is ConfigEntryState.LOADED
    state = hass.states.get(ENTITY_ID)
    assert state.attributes["hvac_modes"] == [HVACMode.OFF, HVACMode.HEAT]
    assert state.attributes["max_temp"] == 28.0


async def test_import_min_only(hass: HomeAssistant) -> None:
    """One limit can be set without the other."""
    assert await _setup(hass, {DOMAIN: [{**YAML_ENTRY, CONF_MIN_TEMP: 18}]})

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.data == {**YAML_ENTRY, CONF_MIN_TEMP: 18.0}
    assert hass.states.get(ENTITY_ID).attributes["min_temp"] == 18.0


async def test_import_min_gap(hass: HomeAssistant) -> None:
    """The minimum gap between the low and high targets is a number."""
    assert await _setup(hass, {DOMAIN: [{**YAML_ENTRY, CONF_MIN_GAP: 2}]})

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.data == {**YAML_ENTRY, CONF_MIN_GAP: 2.0}


async def test_import_min_phase_duration(hass: HomeAssistant) -> None:
    """The minimum phase duration is a number of minutes."""
    assert await _setup(hass, {DOMAIN: [{**YAML_ENTRY, CONF_MIN_PHASE_DURATION: 0}]})

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.data == {**YAML_ENTRY, CONF_MIN_PHASE_DURATION: 0.0}


async def test_import_offsets(hass: HomeAssistant) -> None:
    """The temperature offset of each mode is a number, either way."""
    conf = {**YAML_ENTRY, "heat_offset": 2, "cool_offset": "-1.5"}
    assert await _setup(hass, {DOMAIN: [conf]})

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.data == {**YAML_ENTRY, "heat_offset": 2.0, "cool_offset": -1.5}


async def test_import_monitoring(hass: HomeAssistant) -> None:
    """The monitoring gap and duration are numbers."""
    conf = {**YAML_ENTRY, "monitoring_gap": 3, "monitoring_duration": 0}
    assert await _setup(hass, {DOMAIN: [conf]})

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.data == {**YAML_ENTRY, "monitoring_gap": 3.0, "monitoring_duration": 0.0}


async def test_import_external_sensor(hass: HomeAssistant) -> None:
    """An external sensor is a number or input_number, with the room sensor."""
    conf = {
        **YAML_ENTRY,
        "temperature_sensor": "sensor.room",
        "heat_external_sensor": "number.trv_external",
    }
    assert await _setup(hass, {DOMAIN: [conf]})

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.data == conf


async def test_import_reloads_loaded_entry(hass: HomeAssistant) -> None:
    """Re-importing a changed entry while it runs reloads it."""
    assert await _setup(hass, {DOMAIN: [YAML_ENTRY]})
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={**IMPORTED_DATA, CONF_MAX_TEMP: 25.0},
    )
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(ENTITY_ID).attributes["max_temp"] == 25.0


async def test_import_clears_options(hass: HomeAssistant) -> None:
    """Options of an imported entry are dropped: YAML wins."""
    entry = _imported_entry(options={**IMPORTED_DATA, CONF_MAX_TEMP: 20.0})
    entry.add_to_hass(hass)

    assert await _setup(hass, {DOMAIN: [YAML_ENTRY]})

    assert entry.options == {}
    # Off: the widest maximum of the sources (AC).
    assert hass.states.get(ENTITY_ID).attributes["max_temp"] == 32.0


async def test_import_unchanged_entry_not_updated(hass: HomeAssistant) -> None:
    """An unchanged YAML entry leaves its config entry as it is."""
    entry = _imported_entry()
    entry.add_to_hass(hass)
    modified_at = entry.modified_at

    assert await _setup(hass, {DOMAIN: [YAML_ENTRY]})

    assert entry.modified_at == modified_at


async def test_entry_removed_from_yaml(hass: HomeAssistant) -> None:
    """An imported entry whose name left YAML is removed, with its entity."""
    old = _imported_entry("Old room")
    old.add_to_hass(hass)

    assert await _setup(hass, {DOMAIN: [YAML_ENTRY]})

    assert [e.title for e in hass.config_entries.async_entries(DOMAIN)] == ["Living room"]
    assert er.async_get(hass).async_get_entity_id("climate", DOMAIN, old.entry_id) is None


async def test_all_imported_entries_removed_without_yaml(hass: HomeAssistant) -> None:
    """Removing the YAML section removes every imported entry."""
    _imported_entry().add_to_hass(hass)

    assert await _setup(hass, {})

    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_ui_entries_kept(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Entries created from the UI are not touched by YAML."""
    mock_config_entry.add_to_hass(hass)

    assert await _setup(hass, {DOMAIN: [{**YAML_ENTRY, CONF_NAME: "Bedroom"}]})

    entries = hass.config_entries.async_entries(DOMAIN)
    assert {e.title for e in entries} == {"Living room", "Bedroom"}
    assert mock_config_entry.source == SOURCE_USER
    assert mock_config_entry.data[CONF_NAME] == "Living room"


@pytest.mark.parametrize(
    "conf",
    [
        pytest.param({CONF_NAME: "Living room"}, id="no_source"),
        pytest.param({**YAML_ENTRY, CONF_MIN_TEMP: 30, CONF_MAX_TEMP: 20}, id="min_max"),
        pytest.param({**YAML_ENTRY, CONF_MIN_GAP: -1}, id="negative_gap"),
        pytest.param(
            {**YAML_ENTRY, CONF_MIN_PHASE_DURATION: -1}, id="negative_phase_duration"
        ),
        pytest.param({**YAML_ENTRY, "heat_offset": 11}, id="offset_too_large"),
        pytest.param({**YAML_ENTRY, "monitoring_gap": 0}, id="zero_monitoring_gap"),
        pytest.param(
            {**YAML_ENTRY, "heat_external_sensor": "input_number.trv"},
            id="external_sensor_without_sensor",
        ),
        pytest.param(
            {
                **YAML_ENTRY,
                "temperature_sensor": "sensor.room",
                "heat_external_sensor": "sensor.trv",
            },
            id="external_sensor_not_number",
        ),
        pytest.param(
            {**YAML_ENTRY, "monitoring_duration": -1}, id="negative_monitoring_duration"
        ),
        pytest.param({**YAML_ENTRY, CONF_HEAT_ENTITY: "sensor.heater"}, id="not_climate"),
        pytest.param({CONF_HEAT_ENTITY: HEATER}, id="no_name"),
        pytest.param({**YAML_ENTRY, "unknown": 1}, id="unknown_key"),
        pytest.param([YAML_ENTRY, YAML_ENTRY], id="duplicate_name"),
        pytest.param({**YAML_ENTRY, CONF_SYNC_MODES: ["heat", "off"]}, id="sync_off"),
    ],
)
async def test_invalid_yaml(hass: HomeAssistant, conf: Any) -> None:
    """Invalid YAML fails the setup and creates no entry."""
    assert not await _setup(hass, {DOMAIN: conf})

    assert hass.config_entries.async_entries(DOMAIN) == []


@pytest.mark.parametrize("source_state", [STATE_UNKNOWN, STATE_UNAVAILABLE])
async def test_import_source_not_ready(hass: HomeAssistant, source_state: str) -> None:
    """A source still starting may list wrong modes: it is not checked."""
    hass.states.async_set("climate.starting", source_state, {"hvac_modes": []})

    assert await _setup(
        hass, {DOMAIN: [{**YAML_ENTRY, CONF_COOL_ENTITY: "climate.starting"}]}
    )

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.data[CONF_COOL_ENTITY] == "climate.starting"


async def test_import_self_reference(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """An Adaptative Climate entity cannot be a source, from YAML either."""
    assert await _setup(hass, {DOMAIN: [YAML_ENTRY]})

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={**IMPORTED_DATA, CONF_NAME: "Loop", CONF_HEAT_ENTITY: ENTITY_ID},
    )

    assert result["type"] == "abort"
    assert result["reason"] == "invalid_yaml"
    assert "Invalid YAML configuration for Loop" in caplog.text
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_no_options_for_imported_entry(hass: HomeAssistant) -> None:
    """Imported entries have no options flow; UI entries keep theirs."""
    assert await _setup(hass, {DOMAIN: [YAML_ENTRY]})
    imported = hass.config_entries.async_entries(DOMAIN)[0]
    ui_entry = MockConfigEntry(domain=DOMAIN, data=IMPORTED_DATA)

    assert not AdaptativeClimateConfigFlow.async_supports_options_flow(imported)
    assert AdaptativeClimateConfigFlow.async_supports_options_flow(ui_entry)
