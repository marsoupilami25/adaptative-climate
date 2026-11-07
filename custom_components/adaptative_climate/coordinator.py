"""Coordinator for Adaptative Climate."""

from __future__ import annotations

import logging

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    DOMAIN as CLIMATE_DOMAIN,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, entry_settings, mode_sources, sync_modes

_LOGGER = logging.getLogger(__name__)

type SourceStates = dict[str, State | None]


def is_running(state: State | None) -> bool:
    """Return True when a source is usable and not off."""
    return state is not None and state.state not in {
        HVACMode.OFF,
        STATE_UNAVAILABLE,
        STATE_UNKNOWN,
    }


def lacks_mode(state: State | None, mode: HVACMode) -> bool:
    """Return True when a usable source does not offer a mode.

    A source that is missing, unknown (still starting) or unavailable may not
    list its real modes, so it is not judged.
    """
    if state is None or state.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
        return False
    modes = state.attributes.get(ATTR_HVAC_MODES)
    return modes is not None and mode not in modes


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
        settings = entry_settings(entry)
        self.mode_sources: dict[HVACMode, str] = mode_sources(settings)
        # Modes sharing their fan and swing settings (each has a source).
        self.sync_modes: set[HVACMode] = sync_modes(settings)
        # Each source once, in mode order (a source can serve several modes).
        self.source_entity_ids: list[str] = list(dict.fromkeys(self.mode_sources.values()))
        self._unsub_state_change: CALLBACK_TYPE | None = None
        # Source most recently switched to a running mode. Modes are
        # exclusive: it wins over the other sources.
        self.last_on_source: str | None = None
        # Modes whose source is usable but does not offer them. They stay
        # listed, but switching to them is refused (see _async_check_modes).
        self.unsupported_modes: set[HVACMode] = set()

    def async_start(self) -> None:
        """Check the source modes, then listen for source entity state changes."""
        self._async_check_modes()
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
        # The issues are checked again when the entry loads.
        for mode in self.unsupported_modes:
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(mode))
        self.unsupported_modes = set()
        await super().async_shutdown()

    def _issue_id(self, mode: HVACMode) -> str:
        """Return the Repairs issue id of a mode its source does not offer."""
        return f"{self.config_entry.entry_id}_{mode}_not_supported"

    @callback
    def _async_check_modes(self) -> None:
        """Check that every usable source offers the modes it serves.

        The config check accepts a source that is still starting, so this runs
        again on every source update. A Repairs issue is raised for each mode
        its source does not offer, and removed once it does.
        """
        unsupported = {
            mode
            for mode, entity_id in self.mode_sources.items()
            if lacks_mode(self.hass.states.get(entity_id), mode)
        }
        for mode in unsupported - self.unsupported_modes:
            entity_id = self.mode_sources[mode]
            _LOGGER.warning(
                "%s: %s does not offer the %s mode, which cannot be used until it does",
                self.config_entry.title,
                entity_id,
                mode,
            )
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._issue_id(mode),
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="mode_not_supported",
                translation_placeholders={
                    "name": self.config_entry.title,
                    "hvac_mode": str(mode),
                    "entity_id": entity_id,
                },
            )
        for mode in self.unsupported_modes - unsupported:
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(mode))
        self.unsupported_modes = unsupported

    async def _async_update_data(self) -> SourceStates:
        """Fetch the state of every source entity."""
        return {
            entity_id: self.hass.states.get(entity_id)
            for entity_id in self.source_entity_ids
        }

    async def async_turn_off_other_sources(self, keep: str | None) -> None:
        """Turn off every running source except keep."""
        for entity_id in self.source_entity_ids:
            if entity_id != keep and is_running(self.hass.states.get(entity_id)):
                await self.hass.services.async_call(
                    CLIMATE_DOMAIN,
                    "set_hvac_mode",
                    {ATTR_ENTITY_ID: entity_id, ATTR_HVAC_MODE: HVACMode.OFF},
                    blocking=True,
                )

    async def _async_enforce_exclusive(self, entity_id: str) -> None:
        """Turn off the other sources, unless another source was turned on since."""
        if self.last_on_source == entity_id:
            await self.async_turn_off_other_sources(entity_id)

    @callback
    def _async_source_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle a source entity state update.

        A source switched to a new running mode (by this integration or
        elsewhere) becomes the active one and the other sources are turned off.
        """
        entity_id = event.data["entity_id"]
        old_state = event.data["old_state"]
        new_state = event.data["new_state"]

        switched_on = is_running(new_state) and (
            old_state is None or old_state.state != new_state.state
        )
        if switched_on:
            self.last_on_source = entity_id

        self._async_check_modes()
        self.async_set_updated_data({**(self.data or {}), entity_id: new_state})

        if switched_on:
            self.config_entry.async_create_background_task(
                self.hass,
                self._async_enforce_exclusive(entity_id),
                f"{DOMAIN} exclusive {entity_id}",
            )


type AdaptativeClimateConfigEntry = ConfigEntry[AdaptativeClimateCoordinator]
