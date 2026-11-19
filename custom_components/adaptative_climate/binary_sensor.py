"""Interface module, no logic: platform setup -> ha/views (ARCHITECTURE §11)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .ha.views.monitoring_sensors import monitoring_sensors


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """The two monitoring sensors of the entry."""
    async_add_entities(monitoring_sensors(entry.runtime_data))
