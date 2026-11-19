"""ACmom: mode management of the AC entity: mono/bi-source, phase, AC.wanted (spec §1.3.3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..model.events import (
    ACSEM_TARGETS_CHANGED,
    ACSTM_ENTERED,
    ACSTM_LEFT,
    S_OFF,
    S_STATE_EVENTS,
    S_TEMPERATURE,
    S_UNDISCOVERED,
    S_UNUSABLE,
    S_USABLE,
    T_TEMPERATURE,
    Event,
)
from ..model.values import COOL, HEAT, HIGH, LOW, PHASES, other_phase
from . import reference

if TYPE_CHECKING:
    from .entity import ACEntity

NO_PHASE = "NO_PHASE"
PHASE = "PHASE"
WAITING_PHASE = "WAITING_PHASE"


class ModeManagement:
    """ACmom: the phase of the bi-source heat_cool (§1.3.3.2)."""

    def __init__(self, entity: ACEntity) -> None:
        self._entity = entity
        self.state = NO_PHASE
        self.phase: str | None = None
        self._undiscovered: set[str] = set()

    def handle(self, event: Event) -> None:
        """Transitions of §1.3.3.2.1."""
        entity = self._entity
        if not entity.entry.bi_source:
            return
        kind = event.kind
        was_undiscovered = event.sender in self._undiscovered
        if kind == S_UNDISCOVERED:
            self._undiscovered.add(event.sender)
        elif kind in S_STATE_EVENTS or kind == S_USABLE:
            self._undiscovered.discard(event.sender)

        if kind == ACSTM_ENTERED:
            self._enter()
        elif kind == ACSTM_LEFT:
            self.state = NO_PHASE
            self._set_phase(None)
        elif self.state == NO_PHASE:
            return
        elif kind == T_TEMPERATURE:
            self._check(entity.entry.phase_hysteresis)
        elif kind == S_TEMPERATURE and event.sender in self._phase_sources():
            self._check(entity.entry.phase_hysteresis)
        elif kind == S_OFF and event.sender in self._phase_sources() and was_undiscovered:
            self._check(entity.entry.phase_hysteresis)  # discovery of a phase source
        elif kind == ACSEM_TARGETS_CHANGED:
            self._check(0.0)
        elif kind == S_UNUSABLE and event.sender == self._source(self.phase):
            if self.state == PHASE:
                self.state = WAITING_PHASE
        elif kind == S_USABLE and event.sender == self._source(self.phase):
            if self.state == WAITING_PHASE:
                self.state = PHASE

    # --- Helpers -------------------------------------------------------------------

    def _source(self, phase: str | None) -> str | None:
        return self._entity.entry.phase_source(phase) if phase else None

    def _phase_sources(self) -> set[str]:
        return {self._entity.entry.phase_source(p) for p in PHASES}

    def _set_phase(self, phase: str | None) -> None:
        self.phase = phase
        stored = self._entity.stored
        if stored.phase != phase:
            stored.phase = phase
            self._entity.save()

    def _undiscovered_phase(self, phase: str) -> bool:
        return self._entity.source_state(self._entity.entry.phase_source(phase)).undiscovered

    # --- Transitions -----------------------------------------------------------------

    def _enter(self) -> None:
        """Choice `entering`: the phase is chosen again (ENT-PHASE-1, ENT-WANT-1)."""
        phase = self.wanted_entering()
        self._set_phase(phase)
        available = self._entity.source_state(self._source(phase)).available
        self.state = PHASE if available else WAITING_PHASE
        self._entity.stm.apply_phase(phase)

    def _check(self, hysteresis: float) -> None:
        """A new reading or a change of the targets: switch the phase if wanted (ENT-PHASE-2)."""
        wanted = self.wanted_switch(hysteresis)
        if wanted == self.phase:
            return
        state = self._entity.source_state(self._source(wanted))
        if state.available:
            self.state = PHASE
        elif state.unusable and self.state == PHASE:
            self.state = WAITING_PHASE
        else:
            return
        self._set_phase(wanted)
        self._entity.stm.apply_phase(wanted)

    # --- AC.wanted (§1.3.3.2.2) ---------------------------------------------------------

    def wanted_entering(self) -> str:
        """ENT-WANT-1: the target closest to the reference; else the phase already running."""
        entity = self._entity
        targets = entity.stored.targets
        ref = reference.reference(entity)
        low, high = targets[LOW], targets[HIGH]
        if ref is not None and low is not None and high is not None:
            phase = HEAT if abs(ref - low) <= abs(ref - high) else COOL
        elif entity.source_state(self._source(HEAT)).runs(HEAT):
            phase = HEAT
        elif entity.source_state(self._source(COOL)).runs(COOL):
            phase = COOL
        else:
            phase = entity.stored.phase or HEAT
        if self._undiscovered_phase(phase):
            phase = other_phase(phase)
        return phase

    def wanted_switch(self, hysteresis: float) -> str | None:
        """ENT-WANT-3: switching phase after entering, with the hysteresis `h`."""
        targets = self._entity.stored.targets
        low, high = targets[LOW], targets[HIGH]
        phase = self.phase
        if phase is None or low is None or high is None or low > high:
            return phase
        local_low, local_high = reference.local_temperatures(self._entity)
        if phase == HEAT:
            if local_high is not None and local_high > high + hysteresis and not self._undiscovered_phase(COOL):
                return COOL
        elif local_low is not None and local_low < low - hysteresis and not self._undiscovered_phase(HEAT):
            return HEAT
        return phase
