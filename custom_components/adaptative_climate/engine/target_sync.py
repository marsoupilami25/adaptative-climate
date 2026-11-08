"""Targets of the entity, between the user and the sources.

TargetSync uses the TargetStore and the profiles to:

- Route: key (mode and phase), mapping (which target each attribute of
  the active source gets), target_mode, applied (a target as the source
  of a mode gets it: plus its offset, rounded, in its range), keep (a
  low/high target that goes to one source is kept as that source gets
  it).
- Offsets: the targets are those of the room. A source gets them plus
  its offset, and a target read from it (taken or shown) is minus its
  offset, so a target changed on the source still becomes the target of
  the entity, without drift.
- Set: set (targets asked by the user; the single target is low in heat,
  high in cool), apply_gap (with the configured gap), init (first
  targets from the sources once one is usable).
- Follow the active source (observe): entering a mode turned on
  elsewhere (remote, app) takes the targets of the source. Entering a mode
  asked by the entity starts the settle time and sends the targets. During
  the settle time the source targets
  are ignored (it may report its own, late); the source showing the
  targets sent ends it, otherwise they are sent again at its end if it
  showed others. Outside the settle time, a target changed on the source
  becomes the target of the entity (the source takeover wins).
- Send (async_send): only to the active source still in that mode, only
  the targets it has, low and high together, nothing already applied.
  Errors are logged.
- Show (shown): what the entity shows in each target attribute. A target
  the active source gets is read from it, except during the settle time.
  Off, low/high are shown when supported, else the targets of the mode
  turn_on goes to.
"""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

from homeassistant.components.climate import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from ..const import CONF_MIN_GAP, DOMAIN, MIN_GAP, entry_settings
from ..coordinator import AdaptativeClimateCoordinator
from .model import SETTLE_TIME, SINGLE_TARGETS, TARGET_FEATURES, TargetKey
from .modes import ModeTracker
from .phase import CombinedPhase
from .sources import Sources
from .targets import TargetStore
from .timer import Timer
from .util import changed, is_number, same_temperature

_LOGGER = logging.getLogger(__name__)


class TargetSync:
    """Send the targets to the sources, and take the changes made on them.

    The targets belong to the entity, not to the sources (see TargetStore):
    they are sent to the source of each mode the entity enters, rounded to
    the step of that source and kept in its range.
    """

    def __init__(
        self,
        coordinator: AdaptativeClimateCoordinator,
        sources: Sources,
        modes: ModeTracker,
        phase: CombinedPhase,
        store: TargetStore,
        on_change: Callable[[], None],
    ) -> None:
        """Initialize. on_change writes the state of the entity."""
        self._coordinator = coordinator
        self._entry = coordinator.config_entry
        self._sources = sources
        self._modes = modes
        self._phase = phase
        self._store = store
        self._on_change = on_change
        # Settle time after entering a mode (see SETTLE_TIME).
        self._settle = Timer(coordinator.hass)
        # A target was sent to the source during the settle time, so the
        # source showing it confirms the mode.
        self._settle_sent = False
        # The source showed another target during the settle time.
        self._settle_received = False

    @property
    def settling(self) -> bool:
        """Return True during the settle time."""
        return self._settle.active

    # Which target goes where

    def key(self) -> TargetKey:
        """Return what the targets are sent for: the mode and the combined phase."""
        mode = self._modes.current()
        return (mode, self._phase.phase if mode is HVACMode.HEAT_COOL else None)

    def mapping(self) -> dict[str, str]:
        """Return which target each target attribute of the active source gets."""
        return self._modes.profile(self._modes.current()).target_map(self._phase.phase)

    def target_mode(self, target: str) -> HVACMode | None:
        """Return the only source mode a low/high target goes to, if any.

        Low/high go to the source of HEAT_COOL and to that of auto, when it
        has them. Several sources (or one source with two offsets), or the
        single target: None.
        """
        if target == ATTR_TEMPERATURE:
            return None
        found = {
            (self._sources.mode_sources[mode], self._sources.offset(mode)): mode
            for profile_mode in (HVACMode.HEAT_COOL, HVACMode.AUTO)
            if (mode := self._modes.profile(profile_mode).target_mode(target)) is not None
        }
        return next(iter(found.values())) if len(found) == 1 else None

    def applied(self, target: str, mode: HVACMode | None) -> float | None:
        """Return a target as the source of a mode gets it (plus its offset)."""
        value = self._store[target]
        return None if value is None else self._modes.fit(value, mode)

    def _applied_room(self, target: str, mode: HVACMode | None) -> float | None:
        """Return a target as the source of a mode gets it, minus its offset."""
        value = self.applied(target, mode)
        return None if value is None else value - self._sources.offset(mode)

    def keep(self, target: str, value: float) -> float:
        """Return a value to keep for a target.

        A target that only goes to one source (see target_mode) is kept as
        that source gets it (minus its offset), so the phase switches where
        the source works. Otherwise it is kept as is, for every source.
        """
        mode = self.target_mode(target)
        if mode is not None and self._sources.state(self._sources.mode_sources[mode]) is not None:
            return self._modes.fit(value, mode) - self._sources.offset(mode)
        return value

    # Setting the targets

    def min_gap(self) -> float:
        """Return the gap kept between the low and high targets (MIN_GAP at least)."""
        return max(float(entry_settings(self._entry).get(CONF_MIN_GAP) or 0), MIN_GAP)

    def apply_gap(self, changed_targets: list[str], *, give_way: bool = True) -> None:
        """Keep the low target the configured gap below the high one."""
        self._store.apply_gap(changed_targets, self.min_gap(), self.keep, give_way=give_way)

    def set(self, values: dict[str, float], mode: HVACMode) -> None:
        """Set targets asked by the user, for a mode.

        The single target is the heating setpoint in heat, the cooling one
        in cool. Setting one keeps the configured gap with the other.
        """
        changed_targets: list[str] = []
        for attr, value in values.items():
            target = SINGLE_TARGETS.get(mode, attr) if attr == ATTR_TEMPERATURE else attr
            self._store[target] = self.keep(target, value)
            changed_targets.append(target)
        self.apply_gap(changed_targets)

    @callback
    def init(self) -> None:
        """Set the first targets, once a source is usable.

        The single target comes from a source, else the middle of the range.
        The low target (heating setpoint) comes from the heat source, the high
        one from the cool source. A heat_cool source with low/high targets
        comes first; without any source, they are 1 degree around the single
        target. They then keep the gap. Targets read from a source are
        minus its offset.
        """
        if self._modes.display_source() is None:
            return
        sources = self._sources
        active = self._modes.active_mode()
        modes = [active] if active else list(sources.mode_sources)
        single = self._store[ATTR_TEMPERATURE]
        if single is None:
            low, high = self._modes.temperature_range()
            single = next(
                (
                    value
                    for mode in modes
                    if (
                        value := sources.from_source(
                            sources.attr(sources.mode_sources[mode], ATTR_TEMPERATURE),
                            mode,
                        )
                    )
                    is not None
                ),
                (low + high) / 2,
            )
            self._store[ATTR_TEMPERATURE] = single
        if self._store.has_range():
            return
        own = sources.pair([HVACMode.HEAT_COOL])
        other = sources.pair(list(sources.mode_sources))
        filled: list[str] = []
        for index, (target, mode, fallback) in enumerate(
            (
                (ATTR_TARGET_TEMP_LOW, HVACMode.HEAT, single - 1),
                (ATTR_TARGET_TEMP_HIGH, HVACMode.COOL, single + 1),
            )
        ):
            if self._store[target] is not None:
                continue
            value = sources.from_source(
                sources.attr(sources.mode_sources.get(mode), ATTR_TEMPERATURE), mode
            )
            if own is not None:
                value = own[index]
            elif value is None:
                value = other[index] if other is not None else fallback
            self._store[target] = float(value)
            filled.append(target)
        self.apply_gap(filled)

    # Following the active source

    @callback
    def observe(
        self,
        key: TargetKey,
        source_mode: HVACMode,
        values: dict[str, Any],
        before: dict[str, Any] | None,
        *,
        requested: bool = True,
    ) -> None:
        """Send the targets to a source entering its mode, or take a change made on it.

        A source turned on elsewhere (not requested by this entity) gives
        its targets: the source takeover wins, as for a change made on it.
        A target it reports late is taken too, as a change.

        Entering a mode asked by this entity starts the settle time and
        sends the targets once the source shows the mode. During the
        settle time, the targets of the source are ignored: it may report
        its own targets for the mode, late. The source showing the targets
        sent to it ends the settle time. Otherwise, at its end, the targets
        are sent again if the source showed others in the meantime. If it
        showed nothing, nothing is sent.

        Outside the settle time, a target changed on the source becomes the
        target of this entity (minus the offset of source_mode, the mode the
        source runs in), unless it is the value sent to it (rounded and in
        its range).
        """
        mapping = self.mapping()
        if before is None:
            if not requested:
                self.end_settle()
                self._take(source_mode, values, list(mapping))
                return
            self._start_settle(key)
            self.schedule_send(key)
            return
        changes = [attr for attr in mapping if changed(values[attr], before[attr])]
        if self.settling:
            if self._settle_sent and all(
                same_temperature(values[attr], self.applied(target, source_mode))
                for attr, target in mapping.items()
            ):
                self.end_settle()
            elif changes:
                self._settle_received = True
            return
        self._take(source_mode, values, changes)

    @callback
    def _take(self, source_mode: HVACMode, values: dict[str, Any], attrs: list[str]) -> None:
        """Take target attributes shown by the active source as the targets.

        Minus the offset of its mode: the targets are those of the room.
        """
        mapping = self.mapping()
        taken: list[str] = []
        for attr in attrs:
            value = values[attr]
            target = mapping[attr]
            if not is_number(value) or same_temperature(
                value, self.applied(target, source_mode)
            ):
                continue
            # The user took over from the source: it is kept as is, even
            # outside the range or the limits of this entity. The other
            # target moves to keep the gap.
            self._store[target] = float(value) - self._sources.offset(source_mode)
            taken.append(target)
        self.apply_gap(taken, give_way=False)

    @callback
    def _start_settle(self, key: TargetKey) -> None:
        """Start the settle time of a mode just entered."""
        self.end_settle()

        @callback
        def _settled() -> None:
            received = self._settle_received
            self.end_settle()
            if received:
                self.schedule_send(key)
            self._on_change()

        self._settle.start(SETTLE_TIME, _settled)

    @callback
    def end_settle(self) -> None:
        """End the settle time, if any."""
        self._settle.cancel()
        self._settle_sent = False
        self._settle_received = False

    # Sending the targets

    @callback
    def schedule_send(self, key: TargetKey) -> None:
        """Send the targets to the active source, without waiting."""
        self._entry.async_create_task(
            self._coordinator.hass,
            self.async_send(key),
            f"{DOMAIN} temperature {self._modes.active_source()}",
        )

    async def async_send(self, key: TargetKey) -> None:
        """Send the targets to the active source, if its mode is still on.

        A source without these targets, fan only, or dry or auto on a source
        without target, gets nothing, and they are kept for the next mode. A
        source error is logged without failing.
        """
        if (
            key[0] is HVACMode.OFF
            or self.key() != key
            or self._sources.running_mode() != self._modes.source_mode(key[0])
        ):
            return
        source_mode = self._modes.active_mode()
        assert source_mode is not None
        entity_id = self._sources.mode_sources[source_mode]
        mapping = self.mapping()
        features = self._sources.features(entity_id)
        data: dict[str, float] = {}
        for attr, target in mapping.items():
            applied = self.applied(target, source_mode)
            if TARGET_FEATURES[attr] in features and applied is not None:
                data[attr] = applied
        # Low and high targets go together.
        if len(data) < len(mapping) or all(
            same_temperature(self._sources.attr(entity_id, attr), value)
            for attr, value in data.items()
        ):
            return
        # Set first: the source may show the targets before the call returns.
        if self.settling:
            self._settle_sent = True
        try:
            await self._sources.async_call("set_temperature", entity_id, data)
        except HomeAssistantError as err:
            _LOGGER.warning(
                "Could not set %s on %s: %s",
                ", ".join(f"{attr} {value}" for attr, value in data.items()),
                entity_id,
                err,
            )

    # Showing the targets

    def shown(self, attr: str, range_supported: bool) -> float | None:
        """Return a target attribute as shown by the entity.

        Heat shows the low target as the single target and cool the high one;
        the low/high attributes are empty. HEAT_COOL shows low/high and no
        single target. Fan only shows none. Dry and auto show the targets
        their source has (auto: low/high first). While off, the low/high
        targets are shown when the entity has them (range_supported), else
        the targets of the mode turn_on goes to.

        A target the active source gets is read from it: it shows what is
        applied, even a target set on it outside the limits. During the
        settle time, or from a source without that target, the target of
        this entity is shown, as the active source gets it. The target of the
        other phase of the combined mode is shown as its source gets it.
        A target read from a source, or as it gets it, is minus its offset.
        """
        mode = self._modes.current()
        mapping = self.mapping()
        target: str | None
        if mode is HVACMode.OFF and range_supported:
            # Off, both setpoints are shown, to be set before turning on.
            target = None if attr == ATTR_TEMPERATURE else attr
        else:
            if mode is HVACMode.OFF:
                # No low/high targets: those of the mode turn_on goes to.
                mode = self._modes.next_mode()
            target = self._modes.profile(mode).shown_target(attr, mapping)
        if target is None:
            return None

        active_mode = self._modes.active_mode()
        active = self._modes.active_source()
        for source_attr, mapped in mapping.items():
            if mapped != target:
                continue
            value = self._sources.from_source(self._sources.attr(active, source_attr), active_mode)
            if (
                not self.settling
                and TARGET_FEATURES[source_attr] in self._sources.features(active)
                and value is not None
            ):
                return value
            return self._applied_room(target, active_mode)
        return self._applied_room(target, self.target_mode(target))
