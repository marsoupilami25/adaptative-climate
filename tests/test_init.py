"""Tests for setting up and unloading Adaptative Climate."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.climate import HVACMode
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from .conftest import ENTITY_ID, HEATER


async def test_setup_and_unload(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The entry loads, creates the entity, and unloads cleanly."""
    assert init_integration.state is ConfigEntryState.LOADED
    assert hass.states.get(ENTITY_ID).state == HVACMode.OFF

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert init_integration.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE

    # The coordinator no longer listens to its sources.
    hass.states.async_set(HEATER, HVACMode.HEAT)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE

