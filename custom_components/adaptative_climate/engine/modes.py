"""Current mode of the entity, and switching modes.

The entity does not store its mode: ModeTracker reads it from the
sources each time.

- current: the mode a source runs in, or HEAT_COOL when the combined
  phase runs. While waiting for the phase, or switching, it stays
  HEAT_COOL even if the sources still show off or the other phase; and
  while the source of the phase is unavailable (phase_lost), with no
  source running.
- waiting, waiting_mode, selected: a mode whose source became
  unavailable while it ran is waited for (the entity shows an unknown
  mode, with the targets and settings of that mode) until its source is
  back, another source runs, or the user picks a mode. Not for the
  combined HEAT_COOL, which stays HEAT_COOL (see current). selected is
  the current mode, else the one waited for. Saved across restarts.
- source_mode, active_mode / active_source, display_mode /
  display_source: what is sent to the source, the source mode of the
  current mode and its source, the one read for display (the active one,
  else the first usable one).
- modes, profile, entities, usable, check, next_mode: the modes offered,
  their profile and sources, whether they can be used (check refuses with
  a translated error), and the mode turn_on goes to.
- temperature_range, fit: the range of the entity (sources of the
  current mode, all of them when off, minus their offset, narrowed by the
  limits), and a value as the source of a mode gets it (only kept in that
  range without a source mode).
- async_activate: sets the mode of the source, sends back its remembered
  settings, then turns the other sources off (the new mode runs even if
  one of them fails, see AdaptativeClimateCoordinator.async_enforce_exclusive).
  switching_to is set meanwhile. async_turn_off turns every source off.
- take_request: whether a source entering a mode was asked to by this
  entity (recently), or turned on elsewhere.

State: switching_to, lock (one mode change at a time), last_on_mode,
the mode last asked of a source.
The phase of the combined HEAT_COOL is decided by CombinedPhase and the
entity, not here; the targets are handled by TargetSync.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from homeassistant.components.climate import ATTR_HVAC_MODE, HVACMode
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from ..const import DOMAIN
from ..coordinator import AdaptativeClimateCoordinator
from .model import PHASES, REQUEST_TIME
from .phase import CombinedPhase
from .profiles import ModeProfile
from .settings_memory import SettingsMemory
from .sources import Sources


class ModeTracker:
    """Read the mode of the entity from its sources, and switch it.

    The entity is in a mode when the source of that mode is in the HVAC mode
    of the same name, or in the combined HEAT_COOL when its source runs in
    its phase. Otherwise it is off.
    """

    def __init__(
        self,
        coordinator: AdaptativeClimateCoordinator,
        sources: Sources,
        profiles: dict[HVACMode, ModeProfile],
        phase: CombinedPhase,
        memory: SettingsMemory,
    ) -> None:
        """Initialize from the profiles of the configured modes."""
        self._coordinator = coordinator
        self._sources = sources
        self._profiles = profiles
        self._off = ModeProfile(HVACMode.OFF, sources)
        self._phase = phase
        self._memory = memory
        # Mode being switched to by this entity, while it is in progress.
        self.switching_to: HVACMode | None = None
        # One mode change at a time: a phase switch running in the background
        # and a mode asked by the user would mix their source calls.
        self.lock = asyncio.Lock()
        # Mode restored by turn_on. Kept in memory only.
        self.last_on_mode: HVACMode | None = None
        # Source, mode asked of it and when, until the source shows it.
        self._request: tuple[str, HVACMode, datetime] | None = None
        # Source that became unavailable while the entity ran with it, the
        # mode it runs in and the mode of the entity: back in that mode, it
        # gets the targets and settings of the entity.
        self.waiting: tuple[str, HVACMode, HVACMode] | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return the mode waited for, saved across restarts."""
        return {"waiting": list(self.waiting) if self.waiting is not None else None}

    def restore(self, data: dict[str, Any]) -> None:
        """Read the mode waited for before a restart, if its source still serves it."""
        raw = data.get("waiting")
        if not isinstance(raw, list) or len(raw) != 3:
            return
        entity_id, source_mode, mode = raw
        if (
            source_mode in self._sources.mode_sources
            and self._sources.mode_sources[source_mode] == entity_id
            and mode in self._profiles
        ):
            self.waiting = (entity_id, HVACMode(source_mode), HVACMode(mode))

    @property
    def waiting_mode(self) -> HVACMode | None:
        """Return the mode waited for: its source is away and no source runs.

        The combined HEAT_COOL is never waited for: it stays HEAT_COOL.
        """
        if self.waiting is None:
            return None
        entity_id, _, mode = self.waiting
        if (
            mode is HVACMode.HEAT_COOL and self._phase.enabled
        ) or self._sources.state(entity_id) is not None:
            return None
        if self._sources.running_mode() is not HVACMode.OFF:
            return None
        return mode

    def selected(self) -> HVACMode:
        """Return the mode the user is in: the current one, else the one waited for."""
        return self.waiting_mode or self.current()

    def selected_source_mode(self) -> HVACMode | None:
        """Return the source mode of the selected mode (None when off)."""
        mode = self.source_mode(self.selected())
        return mode if mode in self._sources.mode_sources else None

    def selected_source(self) -> str | None:
        """Return the source of the selected mode (None when off)."""
        return self._sources.mode_sources.get(self.source_mode(self.selected()))

    def missing_sources(self) -> list[str]:
        """Return the sources of the selected mode that are unavailable.

        Both sources of the combined HEAT_COOL count.
        """
        mode = self.selected()
        if mode is HVACMode.OFF:
            return []
        missing: list[str] = []
        for source_mode in self.profile(mode).source_modes():
            entity_id = self._sources.mode_sources[source_mode]
            if self._sources.state(entity_id) is None and entity_id not in missing:
                missing.append(entity_id)
        return missing

    @property
    def switching(self) -> bool:
        """Return True while this entity switches modes."""
        return self.switching_to is not None

    @property
    def modes(self) -> list[HVACMode]:
        """Return OFF plus every mode that has a profile."""
        return [HVACMode.OFF, *self._profiles]

    def profile(self, mode: HVACMode) -> ModeProfile:
        """Return the profile of a mode (that of OFF for a mode not offered)."""
        return self._profiles.get(mode, self._off)

    def current(self) -> HVACMode:
        """Return the mode of the entity.

        The mode the sources run in, or the combined HEAT_COOL when its source
        runs in its phase. While the sources may still show the previous
        phase, or off, it stays HEAT_COOL. So it does while the source of
        the phase is unavailable and no source runs.
        """
        running = self._sources.running_mode()
        phase = self._phase.phase
        if phase is not None and (
            running == phase
            or (
                (self._phase.waiting or self.switching)
                and running in {HVACMode.OFF, *PHASES}
            )
            or (running is HVACMode.OFF and self.phase_lost(phase))
        ):
            return HVACMode.HEAT_COOL
        return running

    def phase_lost(self, phase: HVACMode) -> bool:
        """Return True when the source of a phase of the combined HEAT_COOL is unavailable."""
        return self._sources.state(self._sources.mode_sources.get(phase)) is None

    def source_mode(self, mode: HVACMode) -> HVACMode:
        """Return the mode sent to the source: the phase for the combined HEAT_COOL."""
        return self.profile(mode).source_mode(self._phase.phase)

    def active_mode(self) -> HVACMode | None:
        """Return the source mode of the current mode (None when off)."""
        mode = self.source_mode(self.current())
        return mode if mode in self._sources.mode_sources else None

    def active_source(self) -> str | None:
        """Return the source of the current mode (None when off)."""
        return self._sources.mode_sources.get(self.source_mode(self.current()))

    def display_mode(self) -> HVACMode | None:
        """Return the source mode used for readings: the active one, else the first usable one."""
        active = self.active_mode()
        if active is not None:
            return active
        for mode, entity_id in self._sources.mode_sources.items():
            if self._sources.state(entity_id) is not None:
                return mode
        return None

    def display_source(self) -> str | None:
        """Return the source used for readings: the active one, else the first usable one."""
        mode = self.display_mode()
        return None if mode is None else self._sources.mode_sources[mode]

    def usable(self, mode: HVACMode) -> bool:
        """Return True when the sources of a mode are usable and offer it."""
        return all(
            self._sources.state(self._sources.mode_sources[source_mode]) is not None
            and source_mode not in self._coordinator.unsupported_modes
            for source_mode in self.profile(mode).source_modes()
        )

    def check(self, hvac_mode: HVACMode) -> None:
        """Refuse a mode whose sources are unavailable or do not offer its mode."""
        for source_mode in self.profile(hvac_mode).source_modes():
            entity_id = self._sources.mode_sources[source_mode]
            placeholders = {"hvac_mode": str(hvac_mode), "entity_id": entity_id}
            if self._sources.state(entity_id) is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="source_unavailable",
                    translation_placeholders=placeholders,
                )
            if source_mode in self._coordinator.unsupported_modes:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="source_mode_not_supported",
                    translation_placeholders=placeholders,
                )

    def next_mode(self) -> HVACMode:
        """Return the mode turn_on goes to: the last used one, else the first configured.

        While off, the targets shown and set are those of this mode.
        """
        modes = self.modes[1:]
        mode = self.last_on_mode
        if mode not in modes:
            mode = next(iter(modes), HVACMode.OFF)
        return mode

    def temperature_range(self) -> tuple[float, float]:
        """Return the range of the entity.

        On, or waiting for a mode: the range of the sources of that mode
        (heat and cool for the combined HEAT_COOL), known from when they
        were last usable. Off: the widest range of the sources. Each source
        minus its offset, narrowed by the configured limits.
        """
        mode = self.selected()
        return self._sources.limited_range(
            list(self._sources.mode_sources)
            if mode is HVACMode.OFF
            else list(self.profile(mode).source_modes())
        )

    def fit(self, value: float, mode: HVACMode | None) -> float:
        """Return a value as the source of a mode gets it (see Sources.fit).

        Without a source mode (entity off), the value is only kept in the
        range of the entity.
        """
        if mode is not None:
            return self._sources.fit(value, mode)
        low, high = self.temperature_range()
        return min(max(value, low), high)

    async def async_activate(self, source_mode: HVACMode, mode: HVACMode) -> None:
        """Run the source of a mode, then turn the other sources off.

        source_mode is sent to the source; mode is the mode of this entity
        (HEAT_COOL for a phase of the combined mode). The remembered settings
        of the mode are then sent to its source. The source is turned on
        first: if it fails, the other sources keep running. A source that
        does not turn off is tried again later, without failing the change.
        """
        entity_id = self._sources.mode_sources[source_mode]
        self.switching_to = mode
        self._request = (entity_id, source_mode, dt_util.utcnow())
        try:
            await self._sources.async_call(
                "set_hvac_mode", entity_id, {ATTR_HVAC_MODE: source_mode}
            )
            # It wins over the other sources, even if it was already in its
            # mode (no state change to tell the coordinator).
            self._coordinator.last_on_source = entity_id
            await self._memory.async_send(source_mode, entity_id)
            await self._coordinator.async_enforce_exclusive(entity_id)
        except BaseException:
            self._request = None
            raise
        finally:
            self.switching_to = None

    async def async_turn_off(self) -> None:
        """Turn off every source that is on."""
        self._request = None
        await self._coordinator.async_turn_off_sources()

    def take_request(self, entity_id: str, source_mode: HVACMode) -> bool:
        """Return True when this entity asked a source for the mode it entered.

        The request is used up. A source entering a mode nobody asked for
        here, or too late (see REQUEST_TIME), was turned on elsewhere.
        """
        request, self._request = self._request, None
        return (
            request is not None
            and request[:2] == (entity_id, source_mode)
            and dt_util.utcnow() - request[2] <= REQUEST_TIME
        )
