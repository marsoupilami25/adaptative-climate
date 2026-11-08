"""Current mode of the entity, and switching modes.

The entity does not store its mode: ModeTracker reads it from the
sources each time.

- current: the mode a source runs in, or HEAT_COOL when the combined
  phase runs. While waiting for the phase, or switching, it stays
  HEAT_COOL even if the sources still show off or the other phase.
- source_mode, active_source, display_source: what is sent to the
  source, the source of the current mode, the source read for display
  (the active one, else the first usable one).
- modes, profile, entities, usable, check, next_mode: the modes offered,
  their profile and sources, whether they can be used (check refuses with
  a translated error), and the mode turn_on goes to.
- temperature_range, fit: the range of the entity (sources of the
  current mode, all of them when off, narrowed by the limits), and a
  value as a source gets it (only kept in that range without a source).
- async_activate: turns the other sources off, sets the mode of the
  source, sends back its remembered settings. switching_to is set
  meanwhile. async_turn_off turns every source off.
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
        phase, or off, it stays HEAT_COOL.
        """
        running = self._sources.running_mode()
        phase = self._phase.phase
        if phase is not None and (
            running == phase
            or (
                (self._phase.waiting or self.switching)
                and running in {HVACMode.OFF, *PHASES}
            )
        ):
            return HVACMode.HEAT_COOL
        return running

    def source_mode(self, mode: HVACMode) -> HVACMode:
        """Return the mode sent to the source: the phase for the combined HEAT_COOL."""
        return self.profile(mode).source_mode(self._phase.phase)

    def active_source(self) -> str | None:
        """Return the source of the current mode (None when off)."""
        return self._sources.mode_sources.get(self.source_mode(self.current()))

    def display_source(self) -> str | None:
        """Return the source used for readings: the active one, else the first usable one."""
        active = self.active_source()
        if active is not None:
            return active
        for entity_id in self._sources.entity_ids:
            if self._sources.state(entity_id) is not None:
                return entity_id
        return None

    def entities(self, mode: HVACMode) -> list[str]:
        """Return the sources a mode uses."""
        mode_sources = self._sources.mode_sources
        return [mode_sources[source_mode] for source_mode in self.profile(mode).source_modes()]

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

        On: the range of the sources of the current mode (heat and cool for
        the combined HEAT_COOL). Off: the widest range of the sources. Both
        narrowed by the configured limits.
        """
        mode = self.current()
        return self._sources.limited_range(
            self._sources.entity_ids if mode is HVACMode.OFF else self.entities(mode)
        )

    def fit(self, value: float, entity_id: str | None) -> float:
        """Return a value as a source gets it: rounded to its step, in its range.

        Without a source (entity off), the value is only kept in the range
        of the entity.
        """
        if entity_id is not None:
            return self._sources.fit(value, entity_id)
        low, high = self.temperature_range()
        return min(max(value, low), high)

    async def async_activate(self, source_mode: HVACMode, mode: HVACMode) -> None:
        """Run the source of a mode, after turning the other sources off.

        source_mode is sent to the source; mode is the mode of this entity
        (HEAT_COOL for a phase of the combined mode). The remembered settings
        of the mode are then sent to its source.
        """
        entity_id = self._sources.mode_sources[source_mode]
        self.switching_to = mode
        self._request = (entity_id, source_mode, dt_util.utcnow())
        try:
            await self._coordinator.async_turn_off_other_sources(entity_id)
            await self._sources.async_call(
                "set_hvac_mode", entity_id, {ATTR_HVAC_MODE: source_mode}
            )
            await self._memory.async_send(source_mode, entity_id)
        except BaseException:
            self._request = None
            raise
        finally:
            self.switching_to = None

    async def async_turn_off(self) -> None:
        """Turn off every source that is on."""
        self._request = None
        await self._coordinator.async_turn_off_other_sources(None)

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
