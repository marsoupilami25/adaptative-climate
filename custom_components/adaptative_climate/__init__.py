"""Adaptative Climate integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import AdaptativeClimateConfigEntry, AdaptativeClimateCoordinator

PLATFORMS: list[Platform] = [Platform.CLIMATE]


async def async_setup_entry(
    hass: HomeAssistant, entry: AdaptativeClimateConfigEntry
) -> bool:
    """Set up Adaptative Climate from a config entry."""
    coordinator = AdaptativeClimateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_start()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: AdaptativeClimateConfigEntry
) -> bool:
    """Unload a config entry.

    The coordinator shuts itself down when the entry unloads.
    """
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(
    hass: HomeAssistant, entry: AdaptativeClimateConfigEntry
) -> None:
    """Reload a config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
