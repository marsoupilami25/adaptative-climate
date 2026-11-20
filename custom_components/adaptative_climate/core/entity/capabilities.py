"""ACcam: capabilities management of the AC entity (spec §1.3.4).

The entity builds its capabilities from those of its sources
(`capabilities@S`), read at each computation: modes available, features,
step, ranges, temperature targets used by each mode, fan/swing options.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..model.events import ACCAM_CAPABILITIES_CHANGED, HA_START, S_CAPABILITIES, Event
from ..model.values import (
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


class CapabilitiesManagement:
    """ACcam: rebuilds the capabilities of the entity on S=>AC_capabilities."""

    def __init__(self, entity: ACEntity) -> None:
        self._entity = entity
        self._geometry: Any = None

    def handle(self, event: Event) -> None:
        """ENT-CAP-7: whatever the state of the entity, without changing it."""
        if event.kind == HA_START:
            self._geometry = self.geometry()
            self._entity.check_sync_issues()  # ENT-FAN-7, at start with the stored capabilities
        elif event.kind == S_CAPABILITIES:
            geometry = self.geometry()
            changed = geometry != self._geometry
            self._geometry = geometry
            self._entity.check_sync_issues()
            self._entity.post(Event(ACCAM_CAPABILITIES_CHANGED, value=changed))

    # --- Capabilities of a source in a mode -------------------------------------

    def caps(self, source_id: str, mode: str) -> ModeCaps | None:
        """Capabilities of a source in a mode; None when the mode is not discovered."""
        source = self._entity.sources.get(source_id)
        return source.capabilities.caps(mode) if source else None

    def case(self, source_id: str, mode: str) -> str | None:
        """Case of a source in a mode (ENT-FEAT-1); None when not discovered."""
        caps = self.caps(source_id, mode)
        return caps.case() if caps else None

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

    def context_range(self, source_id: str, mode: str) -> Range:
        """Range of a source in a mode on the scale of the entity, narrowed (ENT-RANGE-1, 3)."""
        entry = self._entity.entry
        if self.caps(source_id, mode) is None:
            return self._narrow((entry.default_min_temp, entry.default_max_temp))
        offset = entry.offset_of(source_id)
        low, high = self.raw_range(source_id, mode)
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
        case = self.case(*context) if context else None
        if case is None or case == CASE_NONE:
            return {}
        if mode == HEAT:
            return {TEMPERATURE: LOW}
        if mode == COOL:
            return {TEMPERATURE: HIGH}
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
        return steps_gcd(steps) or entry.default_step

    # --- Fan and swing (§1.3.4.6) -----------------------------------------------

    def options(self, source_id: str, mode: str, setting: str) -> list[str] | None:
        """Options of a setting in a mode; None when the capability is not discovered."""
        caps = self.caps(source_id, mode)
        return caps.options(setting) if caps else None

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
            if any(self.options(s, m, setting) is not None for s, m in self.contexts()):
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

