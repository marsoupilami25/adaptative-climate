"""Interface module, no logic: platform setup -> ha/views (ARCHITECTURE §11)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .ha.views.climate_view import AdaptativeClimateEntity


if TYPE_CHECKING:
    # Home Assistant from 2025.3 only (ENT-HA-1): annotations only
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """The AC entity of the entry."""
    async_add_entities([AdaptativeClimateEntity(entry.runtime_data)])
