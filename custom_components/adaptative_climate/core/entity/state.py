"""ACstm: state management of the AC entity: AC.apply, AC.follow (spec §1.3.2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..model.events import (
    ACSTM_ENTERED,
    ACSTM_LEFT,
    S_OFF,
    S_ON,
    S_STATE_EVENTS,
    S_UNUSABLE,
    S_USABLE,
    U_SET_MODE,
    U_SET_SETTINGS,
    Event,
)
from ..model.values import HEAT_COOL, OFF

if TYPE_CHECKING:
    from .entity import ACEntity

INIT = "INIT"
NO_SOURCE = "NO_SOURCE"
STATE_OFF = "OFF"
STATE_ON = "ON"
WAITING = "WAITING"

# Refusals of a user request (ENT-STATE-4)
MODE_NOT_CONFIGURED = "mode_not_configured"
MODE_NOT_AVAILABLE = "mode_not_available"


class EntityStateManagement:
    """ACstm: INIT, OPER (OFF, ON(m), WAITING(m)), NO_SOURCE."""

    def __init__(self, entity: ACEntity) -> None:
        self._entity = entity
        self.state = INIT
        self.mode: str | None = None  # m of ON(m) and WAITING(m)
        self._reported: set[str] = set()

    # --- Reading ---------------------------------------------------------------

    def operating_mode(self) -> str | None:
        """The current mode in ON(m) and WAITING(m); None otherwise."""
        return self.mode if self.state in (STATE_ON, WAITING) else None

    def check_mode(self, mode: str | None) -> tuple[str | None, str | None]:
        """A user mode request: (mode to set or None for nothing, refusal) (ENT-STATE-4, 8)."""
        entity = self._entity
        if self.state not in (STATE_OFF, STATE_ON, WAITING):
            return None, None  # unavailable: Home Assistant does not call it (ENT-NOSRC-3)
        if mode is None:  # turn_on: only acts in OFF
            if self.state != STATE_OFF:
                return None, None
            mode = entity.turn_on_mode()
        if mode == OFF:
            return (None if self.state == STATE_OFF else OFF), None
        if mode not in entity.entry.modes:
            return None, MODE_NOT_CONFIGURED
        if mode == self.operating_mode():
            return None, None
        if not entity.mode_available(mode):
            return None, MODE_NOT_AVAILABLE
        return mode, None

    # --- Events ----------------------------------------------------------------

    def handle(self, event: Event) -> None:
        """Transitions of §1.3.2.1."""
        entity = self._entity
        kind = event.kind
        sender = event.sender
        if self.state == INIT:
            if kind in S_STATE_EVENTS:
                self._reported.add(sender)
                if self._reported >= set(entity.sources):
                    self._leave_init()
            return  # ENT-INIT-5
        if kind == S_OFF:
            entity.sending.reported_state(sender, OFF)
        elif kind == S_ON:
            entity.sending.reported_state(sender, event.value)
        if self.state == NO_SOURCE:
            if kind in (S_USABLE, S_OFF):
                self._enter_oper()
            return  # ENT-NOSRC-4
        # OPER
        if kind == S_UNUSABLE and not entity.any_available():
            self._to_no_source()  # wins over the other transitions (ENT-STATE-6)
            return
        if kind == U_SET_MODE:
            self._user_mode(event.value)
        elif kind == U_SET_SETTINGS and "hvac_mode" in event.value:
            self._user_mode(event.value["hvac_mode"])
        elif kind == S_ON:
            self._source_on(sender, event.value)
        elif kind == S_OFF:
            if self.state == STATE_ON and sender == entity.active_source():
                self._enter_off(apply=False)  # takeover: nothing sent
            elif self.state == WAITING and sender in entity.entry.sources_of(self.mode):
                self._enter_on(self.mode, activity=None)
        elif kind == S_USABLE:
            if self.state == WAITING and sender in entity.entry.sources_of(self.mode):
                self._enter_on(self.mode, activity=None)  # the source resynchronizes itself
        elif kind == S_UNUSABLE:
            if self.state == STATE_ON and sender in entity.entry.sources_of(self.mode):
                if not entity.mode_available(self.mode):
                    self._enter_waiting(self.mode, apply=False)

    def _user_mode(self, requested: str | None) -> None:
        mode, refusal = self.check_mode(requested)
        if refusal or mode is None:
            return
        if mode == OFF:
            self._enter_off(apply=True)
        else:
            self._enter_on(mode, activity="apply")

    def _source_on(self, sender: str, mode: str) -> None:
        """ENT-STATE-5: served -> takeover; foreign -> OFF if from the active source."""
        entity = self._entity
        if entity.entry.is_served(sender, mode):
            entity.sem.adopt_all.add(sender)
            self._enter_on(mode, activity="follow", source=sender)
            return
        # `log` in the spec: at warning level (§0, notation)
        entity.notify.log("warning", f"{sender} runs {mode}, a mode it does not serve here")
        if self.state == STATE_ON and sender == entity.active_source():
            self._enter_off(apply=False)

    # --- INIT, NO_SOURCE, resume ------------------------------------------------------

    def _leave_init(self) -> None:
        """ENT-INIT-1: every source has reported its first state."""
        entity = self._entity
        entity.sem.leave_init()
        if not entity.any_available():
            self.state = NO_SOURCE
            return
        self._enter_oper()

    def _enter_oper(self) -> None:
        """Entry of OPER, through the choice `resume` (ENT-TGT-10 first)."""
        entity = self._entity
        entity.sem.enter_oper()
        mode = entity.stored.mode
        sources = entity.entry.sources_of(mode) if mode != OFF else []
        if mode == OFF or not sources or all(entity.source_state(s).undiscovered for s in sources):
            self._enter_off(apply=True)
        elif entity.mode_available(mode):
            self._enter_on(mode, activity="apply")
        elif any(entity.source_state(s).unusable for s in sources):
            self._enter_waiting(mode, apply=True)
        else:
            self._enter_off(apply=True)

    def _to_no_source(self) -> None:
        """No source available: the stored mode is kept for the return (ENT-NOSRC-2)."""
        self.state = NO_SOURCE

    # --- Entering the sub-states ------------------------------------------------------

    def _leaving_heat_cool(self, mode: str | None) -> None:
        entity = self._entity
        if entity.entry.bi_source and mode != HEAT_COOL and entity.mom.state != "NO_PHASE":
            entity.post(Event(ACSTM_LEFT))

    def _store_mode(self, mode: str) -> None:
        stored = self._entity.stored
        changed = stored.mode != mode
        stored.mode = mode
        if mode != OFF and self.state == STATE_ON:
            changed |= stored.last_used != mode
            stored.last_used = mode
        if changed:
            self._entity.save()

    def _enter_off(self, apply: bool) -> None:
        self._leaving_heat_cool(OFF)
        self.state = STATE_OFF
        self.mode = None
        self._store_mode(OFF)
        if apply:
            self.apply_off()

    def _enter_on(self, mode: str, activity: str | None, source: str | None = None) -> None:
        entity = self._entity
        self._leaving_heat_cool(mode)
        self.state = STATE_ON
        self.mode = mode
        self._store_mode(mode)
        if activity == "apply":
            self.apply_mode(mode)
        elif activity == "follow" and source is not None:
            self.follow(source)
        if entity.entry.is_bi(mode):
            entity.post(Event(ACSTM_ENTERED))

    def _enter_waiting(self, mode: str, apply: bool) -> None:
        self._leaving_heat_cool(mode)
        self.state = WAITING
        self.mode = mode
        self._store_mode(mode)
        if apply:
            self.apply_mode(mode)

    # --- Activities (§1.3.2.1) ----------------------------------------------------------

    def apply_mode(self, mode: str) -> None:
        """AC.apply(m): the source of m in m with the settings of m; the others off."""
        entity = self._entity
        entity.sem.fan.not_shared.clear()
        if entity.entry.is_bi(mode):
            entity.sending.expect_others_off(entity.entry.sources_of(mode))
            return
        source_id = entity.entry.source_of(mode)
        settings = entity.sem.settings_for(source_id, mode, mode, False)
        entity.sending.expect_only(source_id, mode, settings)

    def apply_off(self) -> None:
        """AC.apply(off): every source off."""
        self._entity.sem.fan.not_shared.clear()
        self._entity.sending.expect_only(None, OFF, {})

    def follow(self, source_id: str) -> None:
        """AC.follow(S): what S reported is adopted; the others off."""
        entity = self._entity
        entity.sem.fan.not_shared.clear()
        entity.sending.expect_others_off([source_id])

    def apply_phase(self, phase: str) -> None:
        """AC.apply(p): the source of p in p with the settings of the phase (§1.3.3.2.1)."""
        entity = self._entity
        entity.sem.fan.not_shared.clear()
        source_id = entity.entry.phase_source(phase)
        settings = entity.sem.settings_for(source_id, phase, phase, True)
        entity.sending.expect_only(source_id, phase, settings)
