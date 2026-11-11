"""Coordinator for Adaptative Climate."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

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
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_TEMPERATURE_SENSOR,
    DOMAIN,
    combined_heat_cool,
    entry_settings,
    min_phase_duration,
    mode_sources,
    sync_modes,
)
from .known import KnownCapabilities

if TYPE_CHECKING:
    from .engine.model import TargetGap
    from .engine.monitoring import TargetMismatch

_LOGGER = logging.getLogger(__name__)

type SourceStates = dict[str, State | None]

# A source that does not turn off when another one runs is tried again this
# often, while it runs.
EXCLUSIVE_RETRY = timedelta(minutes=1)


def is_running(state: State | None) -> bool:
    """Return True when a source is usable and not off."""
    return state is not None and state.state not in {
        HVACMode.OFF,
        STATE_UNAVAILABLE,
        STATE_UNKNOWN,
    }


def foreign_mode(state: State | None, served: set[HVACMode]) -> str | None:
    """Return the mode a source runs in when it does not serve it here, else None.

    Such a mode was set elsewhere (remote, app): the entity ignores it.
    """
    if not is_running(state) or state.state in served:
        return None
    return state.state


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
        # HEAT_COOL switches between the heat and cool sources.
        self.combined_heat_cool: bool = combined_heat_cool(settings)
        # Minimum time in a phase of the combined HEAT_COOL before it switches
        # to the other one by itself.
        self.min_phase_duration: timedelta = min_phase_duration(settings)
        # Each source once, in mode order (a source can serve several modes).
        self.source_entity_ids: list[str] = list(dict.fromkeys(self.mode_sources.values()))
        # Modes each source serves.
        self.served_modes: dict[str, set[HVACMode]] = {
            entity_id: {m for m, e in self.mode_sources.items() if e == entity_id}
            for entity_id in self.source_entity_ids
        }
        # Optional sensor giving the room temperature.
        self.temperature_sensor: str | None = settings.get(CONF_TEMPERATURE_SENSOR) or None
        # Entities whose states are followed: the sources, then the sensor.
        self.tracked_entity_ids: list[str] = list(
            dict.fromkeys(
                [*self.source_entity_ids, *filter(None, [self.temperature_sensor])]
            )
        )
        # What each source showed it offers, kept while it is away and
        # across restarts (saved by the climate entity).
        self.known = KnownCapabilities(self.source_entity_ids)
        self._unsub_state_change: CALLBACK_TYPE | None = None
        # Source most recently switched to a running mode. Modes are
        # exclusive: it wins over the other sources.
        self.last_on_source: str | None = None
        # Modes whose source is usable but does not offer them. They stay
        # listed, but switching to them is refused (see _async_check_modes).
        self.unsupported_modes: set[HVACMode] = set()
        # Sources that did not turn off while another one runs: the source
        # that runs, and the error. Tried again every EXCLUSIVE_RETRY while
        # they run. Reported by the monitoring.
        self.stuck_sources: dict[str, tuple[str, str]] = {}
        # Targets the active source shows instead of those sent to it, from
        # the climate entity. Reported by the monitoring.
        self.target_mismatches: list[TargetMismatch] = []
        self._problem_listeners: list[CALLBACK_TYPE] = []
        # Targets the climate entity shows otherwise than it keeps them (out
        # of reach of the active source). Reported by the target gap sensor.
        self.target_gaps: list[TargetGap] = []
        self._gap_listeners: list[CALLBACK_TYPE] = []
        # Sources of the selected mode that are unavailable, from the climate
        # entity. Reported by the source unavailable sensor.
        self.missing_sources: list[str] = []
        self._missing_listeners: list[CALLBACK_TYPE] = []
        # One exclusivity check at a time: a mode change and a source turned
        # on elsewhere would both turn the same sources off.
        self._exclusive_lock = asyncio.Lock()
        self._cancel_retry: CALLBACK_TYPE | None = None

    def async_start(self) -> None:
        """Check the source modes, then listen for source and sensor state changes."""
        self._async_check_modes()
        for entity_id in self.source_entity_ids:
            self._warn_foreign(entity_id, self.hass.states.get(entity_id))
        self._unsub_state_change = async_track_state_change_event(
            self.hass,
            self.tracked_entity_ids,
            self._async_source_state_changed,
        )

    async def async_shutdown(self) -> None:
        """Stop listening for source entity state changes."""
        if self._unsub_state_change is not None:
            self._unsub_state_change()
            self._unsub_state_change = None
        self._stop_retry()
        self.stuck_sources = {}
        # The issues are checked again when the entry loads.
        for mode in self.unsupported_modes:
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(mode))
        self.unsupported_modes = set()
        await super().async_shutdown()

    def _issue_id(self, mode: HVACMode) -> str:
        """Return the Repairs issue id of a mode its source does not offer."""
        return f"{self.config_entry.entry_id}_{mode}_not_supported"

    @callback
    def async_restore_known(self, data: dict[str, Any]) -> None:
        """Read what the sources offered before a restart, and check the modes again."""
        self.known.restore(data)
        self._async_check_modes()

    def _lacks_mode(self, mode: HVACMode, entity_id: str) -> bool:
        """Return True when a source is known not to offer a mode.

        Judged on the modes it showed when last usable: a source never seen
        (still starting) is not judged.
        """
        modes = self.known.get(entity_id, ATTR_HVAC_MODES)
        return modes is not None and mode not in modes

    @callback
    def _async_check_modes(self) -> None:
        """Check that every source offers the modes it serves.

        The config check accepts a source that is still starting, so this runs
        again on every source update. A Repairs issue is raised for each mode
        its source does not offer, and removed once it does. A source away
        is judged on what it offered when last usable.
        """
        unsupported = {
            mode
            for mode, entity_id in self.mode_sources.items()
            if self._lacks_mode(mode, entity_id)
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

    def _warn_foreign(self, entity_id: str, state: State | None) -> None:
        """Log a source running in a mode it does not serve here."""
        mode = foreign_mode(state, self.served_modes[entity_id])
        if mode is not None:
            _LOGGER.warning(
                "%s: %s runs in the %s mode, which it does not serve here; "
                "the entity ignores it",
                self.config_entry.title,
                entity_id,
                mode,
            )

    async def _async_update_data(self) -> SourceStates:
        """Fetch the state of every source entity and of the sensor."""
        states = {
            entity_id: self.hass.states.get(entity_id)
            for entity_id in self.tracked_entity_ids
        }
        for entity_id, state in states.items():
            self.known.record(entity_id, state)
        return states

    async def _async_turn_off(self, entity_id: str) -> None:
        """Turn a source off."""
        await self.hass.services.async_call(
            CLIMATE_DOMAIN,
            "set_hvac_mode",
            {ATTR_ENTITY_ID: entity_id, ATTR_HVAC_MODE: HVACMode.OFF},
            blocking=True,
        )

    async def async_turn_off_sources(self) -> None:
        """Turn off every running source. Errors are raised."""
        for entity_id in self.source_entity_ids:
            if is_running(self.hass.states.get(entity_id)):
                await self._async_turn_off(entity_id)

    async def async_enforce_exclusive(self, keep: str, *, retry: bool = False) -> None:
        """Turn off every running source except keep, which runs.

        A source that fails is tried again once at once. If it still fails,
        it is stuck: listed in stuck_sources, and tried again every
        EXCLUSIVE_RETRY while it runs and keep is the source turned on last.
        Between those times, only retry (the timer) tries a stuck source.
        Errors are not raised: keep is on, the mode change worked.
        """
        async with self._exclusive_lock:
            for entity_id in self.source_entity_ids:
                if entity_id == keep or not is_running(self.hass.states.get(entity_id)):
                    continue
                if entity_id in self.stuck_sources and not retry:
                    continue
                error = await self._async_try_turn_off(entity_id)
                if error is None:
                    self._unstick(entity_id)
                    continue
                _LOGGER.debug(
                    "%s: %s does not turn off while %s runs (%s)",
                    self.config_entry.title,
                    entity_id,
                    keep,
                    error,
                )
                self.stuck_sources[entity_id] = (keep, error)
            if self.stuck_sources and self._cancel_retry is None:
                self._cancel_retry = async_call_later(
                    self.hass, EXCLUSIVE_RETRY, self._async_retry_exclusive
                )
        self.async_update_listeners()

    async def _async_try_turn_off(self, entity_id: str) -> str | None:
        """Turn a source off, trying twice. Return the last error, if any."""
        error = ""
        for _ in range(2):
            try:
                await self._async_turn_off(entity_id)
            # The source integration may raise anything: it must not stop the
            # other sources from being turned off.
            except Exception as err:  # noqa: BLE001
                error = str(err) or type(err).__name__
            else:
                return None
        return error

    @callback
    def _async_retry_exclusive(self, _now: datetime) -> None:
        """Try the stuck sources again, while the source turned on last runs."""
        self._cancel_retry = None
        keep = self.last_on_source
        if keep is None or not is_running(self.hass.states.get(keep)):
            for entity_id in list(self.stuck_sources):
                self._unstick(entity_id)
            self.async_update_listeners()
            return
        self.config_entry.async_create_background_task(
            self.hass,
            self.async_enforce_exclusive(keep, retry=True),
            f"{DOMAIN} exclusive retry {keep}",
        )

    @callback
    def _unstick(self, entity_id: str) -> None:
        """Forget a stuck source (it turned off, or no longer has to)."""
        if self.stuck_sources.pop(entity_id, None) is not None:
            _LOGGER.debug(
                "%s: %s no longer runs along with another source",
                self.config_entry.title,
                entity_id,
            )
        if not self.stuck_sources:
            self._stop_retry()

    @callback
    def _stop_retry(self) -> None:
        """Stop trying the stuck sources again."""
        if self._cancel_retry is not None:
            self._cancel_retry()
            self._cancel_retry = None

    @callback
    def async_set_target_mismatches(self, mismatches: list[TargetMismatch]) -> None:
        """Keep the targets the active source does not show, and tell the monitoring."""
        if mismatches == self.target_mismatches:
            return
        self.target_mismatches = mismatches
        for listener in list(self._problem_listeners):
            listener()

    @callback
    def async_add_problem_listener(self, listener: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Call listener when the target mismatches change. Return the removal."""
        self._problem_listeners.append(listener)

        @callback
        def _remove() -> None:
            self._problem_listeners.remove(listener)

        return _remove

    @callback
    def async_set_target_gaps(self, gaps: list[TargetGap]) -> None:
        """Keep the targets shown otherwise than kept, and tell the target gap sensor."""
        if gaps == self.target_gaps:
            return
        self.target_gaps = gaps
        for listener in list(self._gap_listeners):
            listener()

    @callback
    def async_add_gap_listener(self, listener: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Call listener when the target gaps change. Return the removal."""
        self._gap_listeners.append(listener)

        @callback
        def _remove() -> None:
            self._gap_listeners.remove(listener)

        return _remove

    @callback
    def async_set_missing_sources(self, missing: list[str]) -> None:
        """Keep the unavailable sources of the selected mode, and tell the sensor."""
        if missing == self.missing_sources:
            return
        self.missing_sources = missing
        for listener in list(self._missing_listeners):
            listener()

    @callback
    def async_add_missing_listener(self, listener: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Call listener when the unavailable sources of the selected mode change."""
        self._missing_listeners.append(listener)

        @callback
        def _remove() -> None:
            self._missing_listeners.remove(listener)

        return _remove

    async def _async_enforce_on(self, entity_id: str) -> None:
        """Turn off the other sources, unless another source was turned on since."""
        if self.last_on_source == entity_id:
            await self.async_enforce_exclusive(entity_id)

    @callback
    def _async_source_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle a source or sensor state update.

        A source switched to a new mode it serves (by this integration or
        elsewhere) becomes the active one and the other sources are turned off.
        A source back from unavailable in its old mode while another one was
        turned on meanwhile is turned off instead.
        A source switched to a mode it does not serve here is only logged: the
        entity ignores it and the other sources keep running.
        """
        entity_id = event.data["entity_id"]
        old_state = event.data["old_state"]
        new_state = event.data["new_state"]
        self.known.record(entity_id, new_state)

        mode_changed = (
            entity_id in self.source_entity_ids
            and is_running(new_state)
            and (old_state is None or old_state.state != new_state.state)
        )
        switched_on = (
            mode_changed and new_state.state in self.served_modes[entity_id]
        )
        if mode_changed and not switched_on:
            self._warn_foreign(entity_id, new_state)
        # Back from unavailable while another source was turned on meanwhile:
        # it still shows its old mode, the other source wins.
        stale = (
            switched_on
            and old_state is not None
            and old_state.state == STATE_UNAVAILABLE
            and self.last_on_source not in (None, entity_id)
            and is_running(self.hass.states.get(self.last_on_source))
        )
        if stale:
            switched_on = False
        if switched_on:
            self.last_on_source = entity_id
        if entity_id in self.stuck_sources and not is_running(new_state):
            self._unstick(entity_id)

        self._async_check_modes()
        self.async_set_updated_data({**(self.data or {}), entity_id: new_state})

        if switched_on or stale:
            keep = self.last_on_source
            assert keep is not None
            self.config_entry.async_create_background_task(
                self.hass,
                self._async_enforce_on(keep),
                f"{DOMAIN} exclusive {keep}",
            )


type AdaptativeClimateConfigEntry = ConfigEntry[AdaptativeClimateCoordinator]
