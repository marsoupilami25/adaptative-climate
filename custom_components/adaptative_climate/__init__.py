"""Adaptative Climate: interface module, no logic (ARCHITECTURE §3, §11).

Setup, unload, remove -> ha/entry; YAML at start -> config/yaml_import;
the dashboard card -> ha/frontend.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .config.yaml_import.yaml_import import CONFIG_SCHEMA, async_import_yaml
from .ha.entry import lifecycle
from .ha.frontend.card import async_setup_card

__all__ = ["CONFIG_SCHEMA"]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Import and sync the YAML entries (spec §3.2), provide the card (ENT-CARD-1)."""
    await async_import_yaml(hass, config)
    await async_setup_card(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry."""
    return await lifecycle.async_setup_entry(hass, entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await lifecycle.async_unload_entry(hass, entry)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete a config entry: its stored data is erased."""
    await lifecycle.async_remove_entry(hass, entry)
