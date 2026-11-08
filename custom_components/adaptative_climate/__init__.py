"""Adaptative Climate integration."""

from __future__ import annotations

from collections import Counter
from typing import Any

import voluptuous as vol

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_MAX_TEMP,
    CONF_MIN_GAP,
    CONF_MIN_TEMP,
    CONF_SYNC_MODES,
    CONF_TEMPERATURE_SENSOR,
    DOMAIN,
    MIN_GAP,
    MODE_SOURCE_KEYS,
)
from .coordinator import AdaptativeClimateConfigEntry, AdaptativeClimateCoordinator

PLATFORMS: list[Platform] = [Platform.CLIMATE]


def _check_entry(conf: dict[str, Any]) -> dict[str, Any]:
    """Check what the schema alone cannot: one source at least, min below max."""
    if not any(conf.get(key) for key in MODE_SOURCE_KEYS.values()):
        raise vol.Invalid("Set a climate entity for at least one mode")
    min_temp = conf.get(CONF_MIN_TEMP)
    max_temp = conf.get(CONF_MAX_TEMP)
    if min_temp is not None and max_temp is not None and min_temp >= max_temp:
        raise vol.Invalid(f"{CONF_MIN_TEMP} must be lower than {CONF_MAX_TEMP}")
    return conf


def _unique_names(confs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reject two entries with the same name: the name identifies an entry."""
    duplicates = [
        name for name, count in Counter(c[CONF_NAME] for c in confs).items() if count > 1
    ]
    if duplicates:
        raise vol.Invalid(f"Duplicate name: {', '.join(duplicates)}")
    return confs


ENTRY_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Required(CONF_NAME): cv.string,
            **{
                vol.Optional(key): cv.entity_domain(CLIMATE_DOMAIN)
                for key in MODE_SOURCE_KEYS.values()
            },
            vol.Optional(CONF_TEMPERATURE_SENSOR): cv.entity_domain("sensor"),
            vol.Optional(CONF_MIN_TEMP): vol.Coerce(float),
            vol.Optional(CONF_MAX_TEMP): vol.Coerce(float),
            vol.Optional(CONF_MIN_GAP): vol.All(vol.Coerce(float), vol.Range(min=MIN_GAP)),
            vol.Optional(CONF_SYNC_MODES): vol.All(
                cv.ensure_list, [vol.In([str(mode) for mode in MODE_SOURCE_KEYS])]
            ),
        }
    ),
    _check_entry,
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.All(cv.ensure_list, [ENTRY_SCHEMA], _unique_names)},
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Create, update or remove the entries declared in YAML.

    YAML is the source of truth for imported entries: an entry whose name
    is no longer in YAML is removed. Entries created from the UI are left alone.
    """
    confs: list[dict[str, Any]] = config.get(DOMAIN, [])
    names = {conf[CONF_NAME] for conf in confs}

    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.source == SOURCE_IMPORT and entry.unique_id not in names:
            await hass.config_entries.async_remove(entry.entry_id)

    for conf in confs:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=conf
            )
        )
    return True


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
