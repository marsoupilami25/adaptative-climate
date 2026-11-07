"""Tests for the Adaptative Climate config and options flows."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.climate import HVACMode
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.adaptative_climate.const import (
    CONF_COOL_ENTITY,
    CONF_HEAT_ENTITY,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    DOMAIN,
)

from .conftest import AC, ENTITY_ID, HEATER


async def test_user_flow(hass: HomeAssistant) -> None:
    """A valid form creates the entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Living room", CONF_HEAT_ENTITY: HEATER},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Living room"
    assert result["data"] == {
        CONF_NAME: "Living room",
        CONF_HEAT_ENTITY: HEATER,
        CONF_MIN_TEMP: 7.0,
        CONF_MAX_TEMP: 35.0,
    }


async def test_user_flow_no_source(hass: HomeAssistant) -> None:
    """At least one source is required; the user can then fix the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Living room"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_source"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Living room", CONF_COOL_ENTITY: AC}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_min_max_invalid(hass: HomeAssistant) -> None:
    """The minimum must be lower than the maximum."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Living room",
            CONF_HEAT_ENTITY: HEATER,
            CONF_MIN_TEMP: 25,
            CONF_MAX_TEMP: 25,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "min_max_invalid"}


async def test_user_flow_self_reference(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """An Adaptative Climate entity cannot be a source."""
    own = entity_registry.async_get_or_create(
        "climate", DOMAIN, "other_entry", suggested_object_id="other"
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Living room", CONF_HEAT_ENTITY: own.entity_id},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HEAT_ENTITY: "self_reference"}


async def test_user_flow_mode_not_supported(hass: HomeAssistant, sources: None) -> None:
    """A source must offer the mode it serves."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    # The heater has no cool mode.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Living room", CONF_HEAT_ENTITY: HEATER, CONF_COOL_ENTITY: HEATER},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_COOL_ENTITY: "mode_not_supported"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Living room", CONF_HEAT_ENTITY: HEATER, CONF_COOL_ENTITY: AC},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_options_flow(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Options replace the settings and reload the entry."""
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    # Only the heater is kept: the cool and dry sources are cleared.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_HEAT_ENTITY: HEATER, CONF_MIN_TEMP: 10.0, CONF_MAX_TEMP: 28.0},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options == {
        CONF_HEAT_ENTITY: HEATER,
        CONF_MIN_TEMP: 10.0,
        CONF_MAX_TEMP: 28.0,
    }
    state = hass.states.get(ENTITY_ID)
    assert state.attributes["hvac_modes"] == [HVACMode.OFF, HVACMode.HEAT]
    assert state.attributes["min_temp"] == 10.0
    assert state.attributes["max_temp"] == 28.0


async def test_options_flow_error(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Invalid options show the form again."""
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MIN_TEMP: 10.0, CONF_MAX_TEMP: 28.0}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_source"}


async def test_options_flow_mode_not_supported(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The options flow also rejects a source without the mode."""
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    # The AC has no heat mode.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_HEAT_ENTITY: AC, CONF_MIN_TEMP: 10.0, CONF_MAX_TEMP: 28.0},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HEAT_ENTITY: "mode_not_supported"}
