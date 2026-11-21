"""ACcam: capabilities management of the AC entity (spec §1.3.4).

The entity builds its capabilities from those of its sources
(`capabilities@S`), read at each computation: modes available, features,
step, ranges, temperature targets used by each mode, fan/swing options.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..model.events import ACCAM_CAPABILITIES_CHANGED, HA_START, S_CAPABILITIES, Event
from ..model.values import (
    CAP_LISTS,
    CAP_NUMBERS,
    CASE_LOW_HIGH,
    CASE_NONE,
    COOL,
    FAN_ONLY,
    FAN_SWING_SETTINGS,
    FEATURE_OF,
    FEATURE_TARGET_TEMPERATURE,
    FEATURE_TARGET_TEMPERATURE_RANGE,
    FEATURE_TURN_OFF,
    FEATURE_TURN_ON,
    HEAT,
    HIGH,
    LOW,
    PHASES,
    SINGLE,
    TARGET_TEMP_HIGH,
    TARGET_TEMP_LOW,
    TARGETS,
    TEMPERATURE,
    ModeCaps,
    steps_gcd,
)

if TYPE_CHECKING:
    from .entity import ACEntity

Range = tuple[float, float]

#: A source never seen usable gives no provisional capability: its modes count as
#: with a single temperature target, in the Home Assistant default range (ENT-CAP-4).
FALLBACK = ModeCaps(supported_features=FEATURE_TARGET_TEMPERATURE)

TARGETS_SHOWN = {
    (): "no temperature target",
    (TEMPERATURE,): "a single temperature target",
    (TARGET_TEMP_HIGH, TARGET_TEMP_LOW): "low/high",
}


class CapabilitiesManagement:
    """ACcam: rebuilds the capabilities of the entity on S=>AC_capabilities."""

    def __init__(self, entity: ACEntity) -> None:
        self._entity = entity
        self._geometry: Any = None
        #: Per mono-source mode: (discovered, targets shown), at the last rebuild.
        self._shown: dict[str, tuple[bool, tuple[str, ...]]] = {}
        #: Targets a mode showed before its discovery, until it shows others (ENT-CAP-6).
        self._before_discovery: dict[str, tuple[str, ...]] = {}

    def handle(self, event: Event) -> None:
        """ENT-CAP-7: whatever the state of the entity, without changing it."""
        if event.kind == HA_START:
            self._geometry = self.geometry()
            self._shown = self._targets_shown()
            self._entity.check_sync_issues()  # ENT-FAN-7, at start with the stored capabilities
        elif event.kind == S_CAPABILITIES:
            geometry = self.geometry()
            changed = geometry != self._geometry
            self._geometry = geometry
            self._log_discoveries()
            self._entity.check_sync_issues()
            self._entity.post(Event(ACCAM_CAPABILITIES_CHANGED, value=changed))

    def _targets_shown(self) -> dict[str, tuple[bool, tuple[str, ...]]]:
        entry = self._entity.entry
        result = {}
        for mode in entry.modes:
            context = self.mode_context(mode)
            if entry.is_bi(mode) or context is None:
                continue
            result[mode] = (self.caps(*context) is not None, tuple(sorted(self.mode_targets(mode))))
        return result

    def _log_discoveries(self) -> None:
        """ENT-CAP-6: a mode discovered with other targets than it showed before, logged."""
        shown = self._targets_shown()
        for mode, (discovered, targets) in shown.items():
            before = self._shown.get(mode)
            if before is not None and not before[0] and discovered:
                self._before_discovery[mode] = before[1]
            if discovered and self._before_discovery.get(mode, targets) != targets:
                was = self._before_discovery.pop(mode)
                self._entity.notify.log(
                    "info",
                    f"{mode} discovered: it shows {TARGETS_SHOWN.get(targets, targets)} instead of "
                    f"{TARGETS_SHOWN.get(was, was)} shown before; the temperature targets set "
                    "meanwhile are kept",
                )
        self._shown = shown

    # --- Capabilities of a source in a mode -------------------------------------

    def caps(self, source_id: str, mode: str) -> ModeCaps | None:
        """Capabilities of a source in a mode; None when the mode is not discovered."""
        source = self._entity.sources.get(source_id)
        return source.capabilities.caps(mode) if source else None

    def case(self, source_id: str, mode: str) -> str | None:
        """Case of a source in a mode (ENT-FEAT-1); None when not discovered."""
        caps = self.caps(source_id, mode)
        return caps.case() if caps else None

    def provisional(self, source_id: str) -> ModeCaps:
        """Provisional capabilities of a source (SRC-DATA-13); the fallback without (ENT-CAP-4)."""
        source = self._entity.sources.get(source_id)
        caps = source.provisional if source else None
        return caps if caps is not None else FALLBACK

    def shown_caps(self, source_id: str, mode: str) -> ModeCaps:
        """What a mode shows: its capabilities with the held ones (SRC-DATA-13), or the
        provisional ones before its discovery (ENT-CAP-4).

        To show and to accept settings only, never to decide what to send (ENT-CAP-5).
        """
        caps = self.caps(source_id, mode)
        if caps is None:
            return self.provisional(source_id)
        source = self._entity.sources.get(source_id)
        held = source.held.get(mode) if source else None
        return caps if held is None else _merged(caps, held)

    def source_step(self, source_id: str, mode: str) -> float:
        """Step of a source in a mode; Home Assistant default without (ENT-STEP-1)."""
        caps = self.caps(source_id, mode)
        if caps is not None and caps.target_temp_step:
            return caps.target_temp_step
        return self._entity.entry.default_step

    def raw_range(self, source_id: str, mode: str) -> Range:
        """min_temp / max_temp of a source in a mode, as read (defaults without)."""
        entry = self._entity.entry
        caps = self.caps(source_id, mode)
        low = caps.min_temp if caps and caps.min_temp is not None else entry.default_min_temp
        high = caps.max_temp if caps and caps.max_temp is not None else entry.default_max_temp
        return low, high

    def context_range(self, source_id: str, mode: str, shown: bool = True) -> Range:
        """Range of a source in a mode on the scale of the entity, narrowed (ENT-RANGE-1, 3).

        Shown: before the discovery, the provisional range of the source (ENT-CAP-4), then
        with the held capabilities. Not shown (to send): the range read in the mode only.
        """
        entry = self._entity.entry
        caps = self.shown_caps(source_id, mode) if shown else self.caps(source_id, mode) or FALLBACK
        if caps is FALLBACK:
            return self._narrow((entry.default_min_temp, entry.default_max_temp))
        offset = entry.offset_of(source_id)
        low = caps.min_temp if caps.min_temp is not None else entry.default_min_temp
        high = caps.max_temp if caps.max_temp is not None else entry.default_max_temp
        return self._narrow((low - offset, high - offset))

    def _narrow(self, rng: Range) -> Range:
        """ENT-RANGE-3: the limits only narrow; a limit outside the range is ignored."""
        entry = self._entity.entry
        low, high = rng
        if entry.min_temp is not None and low <= entry.min_temp <= high:
            low = entry.min_temp
        if entry.max_temp is not None and low <= entry.max_temp <= high:
            high = entry.max_temp
        return low, high

    # --- Modes ------------------------------------------------------------------

    def mode_context(self, mode: str) -> tuple[str, str] | None:
        """(source, source mode) of a mono-source mode."""
        source_id = self._entity.entry.source_of(mode)
        return (source_id, mode) if source_id else None

    def phase_context(self, phase: str) -> tuple[str, str]:
        """(source, source mode) of a phase of the bi-source heat_cool."""
        return self._entity.entry.phase_source(phase), phase

    def mode_range(self, mode: str) -> Range:
        """Range of a mode (ENT-RANGE-1)."""
        entry = self._entity.entry
        if entry.is_bi(mode):
            low = self.context_range(*self.phase_context(HEAT))[0]
            high = self.context_range(*self.phase_context(COOL))[1]
            return low, max(low, high)
        context = self.mode_context(mode)
        if context is None:
            # Safety net (not reached): a configured mode always has a source (CFG-MODE-3)
            return self._narrow((entry.default_min_temp, entry.default_max_temp))
        return self.context_range(*context)

    def widest_range(self) -> Range:
        """The widest range of all the modes: the range shown in OFF (ENT-RANGE-2)."""
        ranges = [self.mode_range(m) for m in self._entity.entry.modes]
        if not ranges:
            # Safety net (not reached): a configuration without mode is refused (CFG-MODE-4)
            entry = self._entity.entry
            return entry.default_min_temp, entry.default_max_temp
        return min(r[0] for r in ranges), max(r[1] for r in ranges)

    def mode_targets(self, mode: str) -> dict[str, str]:
        """Temperature targets a mode shows: attribute -> target (§1.3.4.3)."""
        entry = self._entity.entry
        if mode == FAN_ONLY:
            return {}
        if entry.is_bi(mode):
            return {TARGET_TEMP_LOW: LOW, TARGET_TEMP_HIGH: HIGH}
        context = self.mode_context(mode)
        case = self.shown_caps(*context).case() if context else None  # provisional before discovery
        if case is None or case == CASE_NONE:
            return {}
        # Whatever the mode, the case of its source decides (ENT-FEAT-4).
        if case == CASE_LOW_HIGH:
            return {TARGET_TEMP_LOW: LOW, TARGET_TEMP_HIGH: HIGH}
        return {TEMPERATURE: SINGLE}

    def target_range(self, target: str) -> Range:
        """Widest range of the modes that use a target (ENT-RANGE-5)."""
        ranges = [
            self.mode_range(m)
            for m in self._entity.entry.modes
            if target in self.mode_targets(m).values()
        ]
        if not ranges:
            return self.widest_range()
        return min(r[0] for r in ranges), max(r[1] for r in ranges)

    def has_single(self) -> bool:
        """A configured mode shows a single temperature target (ENT-FEAT-3)."""
        return any(TEMPERATURE in self.mode_targets(m) for m in self._entity.entry.modes)

    def has_low_high(self) -> bool:
        """A configured mode shows low/high (ENT-FEAT-3)."""
        return any(TARGET_TEMP_LOW in self.mode_targets(m) for m in self._entity.entry.modes)

    def step(self) -> float:
        """Step of the entity: divides every step of the sources (ENT-STEP-1)."""
        entry = self._entity.entry
        steps = [
            caps.target_temp_step or entry.default_step
            for source in self._entity.sources.values()
            for caps in source.capabilities.modes.values()
        ]
        # The provisional step of a source while a configured mode of it is not discovered,
        # the held step of a mode just discovered without step (SRC-DATA-13)
        sources = self._entity.sources
        for source_id, mode in self.contexts():
            source = sources.get(source_id)
            caps = self.caps(source_id, mode)
            if source is None:
                continue
            if caps is None and source.provisional is not None:
                steps.append(source.provisional.target_temp_step or entry.default_step)
            elif caps is not None and caps.target_temp_step is None:
                held = source.held.get(mode)
                if held is not None and held.target_temp_step:
                    steps.append(held.target_temp_step)
        return steps_gcd(steps) or entry.default_step

    # --- Fan and swing (§1.3.4.6) -----------------------------------------------

    def options(self, source_id: str, mode: str, setting: str) -> list[str] | None:
        """Options of a setting in a mode; None when the capability is not discovered."""
        caps = self.caps(source_id, mode)
        return caps.options(setting) if caps else None

    def shown_options(self, source_id: str, mode: str, setting: str) -> list[str] | None:
        """Options shown in a discovered mode, held ones included (SRC-DATA-13)."""
        if self.caps(source_id, mode) is None:
            return None
        return self.shown_caps(source_id, mode).options(setting)

    def provisional_options(self, setting: str) -> list[str] | None:
        """ENT-FAN-3: with a single configured mode not discovered yet, the provisional
        options of its source (shown in OFF); None otherwise."""
        modes = self._entity.entry.modes
        if len(modes) != 1 or (context := self.mode_context(modes[0])) is None:
            return None
        if self.caps(*context) is not None:
            return None
        source = self._entity.sources.get(context[0])
        provisional = source.provisional if source else None
        return provisional.options(setting) if provisional is not None else None

    def contexts(self) -> list[tuple[str, str]]:
        """(source, source mode) of every configured mode and phase."""
        entry = self._entity.entry
        result: list[tuple[str, str]] = []
        for mode in entry.modes:
            if entry.is_bi(mode):
                result.extend(self.phase_context(p) for p in PHASES)
            elif (context := self.mode_context(mode)) is not None:
                result.append(context)
        return result

    def features(self) -> int:
        """Features of the entity (ENT-FEAT-3, ENT-FAN-2)."""
        features = FEATURE_TURN_ON | FEATURE_TURN_OFF
        if self.has_single():
            features |= FEATURE_TARGET_TEMPERATURE
        if self.has_low_high():
            features |= FEATURE_TARGET_TEMPERATURE_RANGE
        for setting in FAN_SWING_SETTINGS:
            if any(self.shown_options(s, m, setting) is not None for s, m in self.contexts()):
                features |= FEATURE_OF[setting]
            elif self.provisional_options(setting) is not None:
                features |= FEATURE_OF[setting]
        return features

    def geometry(self) -> Any:
        """What brings the targets back in line when it changes (ENT-TGT-4).

        The ranges of the sources are taken as read, before the limits: a change
        of the range of a source counts even when `min_temp` / `max_temp` hide it.
        """
        return (
            self.step(),
            self.has_low_high(),
            tuple(
                (self.raw_range(s, m), self.source_step(s, m))
                for s, m in self.contexts()
                if self.caps(s, m) is not None
            ),
            tuple(self.mode_range(m) for m in self._entity.entry.modes),
            tuple(self.target_range(t) for t in TARGETS),
        )



def _merged(caps: ModeCaps, held: ModeCaps) -> ModeCaps:
    """The capabilities of a mode with its held ones (SRC-DATA-13)."""
    merged = ModeCaps.from_dict(caps.to_dict()) or ModeCaps()
    merged.supported_features |= held.supported_features
    for name in CAP_NUMBERS:
        if getattr(merged, name) is None:
            setattr(merged, name, getattr(held, name))
    for name in CAP_LISTS:
        items: list[str] = getattr(merged, name)
        items.extend(i for i in getattr(held, name) if i not in items)
    return merged
