"""Setup, unload, reload, delete of an entry (ARCHITECTURE §8, spec §1.1.4)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError

from ...config.options.builder import build
from ...config.yaml_import.yaml_import import yaml_error
from ...const import DOMAIN
from ..adapters.store import entry_store, forget_store
from .host import EntryHost

PLATFORMS = [Platform.CLIMATE, Platform.BINARY_SENSOR]

type AdaptativeClimateConfigEntry = ConfigEntry[EntryHost]


async def async_setup_entry(hass: HomeAssistant, entry: AdaptativeClimateConfigEntry) -> bool:
    """Setup: model, store, runtime and adapters, views, then the start stimulus."""
    if (error := yaml_error(hass, entry.entry_id)) is not None:
        # Invalid YAML entry: kept with its stored data, not loaded (CFG-YAML-5)
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="invalid_yaml_entry",
            translation_placeholders={"error": error},
        )
    model = build(entry.entry_id, entry.data, hass.config.units.temperature_unit)
    store = entry_store(hass, entry.entry_id)
    stored = await store.async_load()
    host = EntryHost(hass, model, store, stored)
    entry.runtime_data = host
    # The views are added before the start stimulus: the first state is written at its end
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    host.start()
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AdaptativeClimateConfigEntry) -> bool:
    """Unload (END-1): every actor stops at once; nothing is sent to the source entities."""
    entry.runtime_data.stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete (END-3): all the stored data of the entry is erased."""
    await forget_store(hass, entry.entry_id).async_remove()


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """A change of configuration (options, YAML) reloads the entry (ENT-INIT-4)."""
    await hass.config_entries.async_reload(entry.entry_id)
