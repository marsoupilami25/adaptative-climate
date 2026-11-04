"""Coordinator for Adaptative Climate."""

from __future__ import annotations

import logging

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

from .const import CONF_TARGET_ENTITY, DOMAIN

_LOGGER = logging.getLogger(__name__)


class AdaptativeClimateCoordinator(DataUpdateCoordinator[State | None]):
    """Coordinate updates from the wrapped climate entity."""

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
        self.target_entity_id: str = entry.data[CONF_TARGET_ENTITY]
        self._unsub_state_change: CALLBACK_TYPE | None = None

    def async_start(self) -> None:
        """Start listening for wrapped entity state changes."""
        self._unsub_state_change = async_track_state_change_event(
            self.hass,
            [self.target_entity_id],
            self._async_target_state_changed,
        )

    async def async_shutdown(self) -> None:
        """Stop listening for wrapped entity state changes."""
        if self._unsub_state_change is not None:
            self._unsub_state_change()
            self._unsub_state_change = None
        await super().async_shutdown()

    async def _async_update_data(self) -> State | None:
        """Fetch the wrapped climate entity state."""
        return self.hass.states.get(self.target_entity_id)

    @callback
    def _async_target_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle wrapped entity state updates."""
        self.async_set_updated_data(event.data["new_state"])


type AdaptativeClimateConfigEntry = ConfigEntry[AdaptativeClimateCoordinator]
