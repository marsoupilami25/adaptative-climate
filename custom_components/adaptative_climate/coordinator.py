"""Coordinator for Adaptative Climate."""

from __future__ import annotations

import logging

from homeassistant.components.climate import HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, entry_settings, mode_sources

_LOGGER = logging.getLogger(__name__)

type SourceStates = dict[str, State | None]


class AdaptativeClimateCoordinator(DataUpdateCoordinator[SourceStates]):
    """Coordinate updates from the source climate entities."""

    config_entry: AdaptativeClimateConfigEntry

    def __init__(self, hass: HomeAssistant, entry: AdaptativeClimateConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            logger=_LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=None,
        )
        self.mode_sources: dict[HVACMode, str] = mode_sources(entry_settings(entry))
        # Each source once, in mode order (a source can serve several modes).
        self.source_entity_ids: list[str] = list(dict.fromkeys(self.mode_sources.values()))
        self._unsub_state_change: CALLBACK_TYPE | None = None

    def async_start(self) -> None:
        """Start listening for source entity state changes."""
        self._unsub_state_change = async_track_state_change_event(
            self.hass,
            self.source_entity_ids,
            self._async_source_state_changed,
        )

    async def async_shutdown(self) -> None:
        """Stop listening for source entity state changes."""
        if self._unsub_state_change is not None:
            self._unsub_state_change()
            self._unsub_state_change = None
        await super().async_shutdown()

    async def _async_update_data(self) -> SourceStates:
        """Fetch the state of every source entity."""
        return {
            entity_id: self.hass.states.get(entity_id)
            for entity_id in self.source_entity_ids
        }

    @callback
    def _async_source_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle a source entity state update."""
        self.async_set_updated_data(
            {**(self.data or {}), event.data["entity_id"]: event.data["new_state"]}
        )


type AdaptativeClimateConfigEntry = ConfigEntry[AdaptativeClimateCoordinator]
