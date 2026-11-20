"""Sstm: state management of a source (spec §1.2.3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..model.events import (
    AC_REQUEST,
    S_ACTION,
    S_OFF,
    S_ON,
    S_TEMPERATURE,
    S_UNDISCOVERED,
    S_UNUSABLE,
    S_USABLE,
    SDSM_DISCOVERED,
    SDSM_RESTORED,
    SDSM_SERVED_MODE_LOST,
    SDSM_SERVED_MODES_BACK,
    SE_ATTRIBUTES,
    SE_NOT_USABLE,
    SE_OFF,
    SE_ON,
    SSTM_BACK,
    SSTM_MODE_CHANGED,
    SSTM_RESTORED,
    SSTM_SEND,
    SSTM_TAKEOVER,
    SSTM_UNUSABLE,
    Event,
)
from ..model.values import OFF, Snapshot, as_number, is_usable

if TYPE_CHECKING:
    from .source import Source

# States of the source (§1.2.3.1)
STARTING = "starting"  # before Sdsm=>Sstm_restored
UNDISCOVERED = "UNDISCOVERED"
STATE_OFF = "OFF"
STATE_ON = "ON"
UNUSABLE = "UNUSABLE"


class StateManagement:
    """Sstm: the local state of the source, kept in sync with its source entity."""

    def __init__(self, source: Source) -> None:
        self._source = source
        self.state = STARTING
        self.mode: str | None = None  # m of ON(m)

    # --- Reading ---------------------------------------------------------------

    @property
    def current(self) -> str | None:
        """`off` in OFF, `m` in ON(m), None otherwise."""
        if self.state == STATE_OFF:
            return OFF
        if self.state == STATE_ON:
            return self.mode
        # Safety net (not reached): only asked in OFF or ON(m)
        return None

    @property
    def operating(self) -> bool:
        """In OFF or ON(m)."""
        return self.state in (STATE_OFF, STATE_ON)

    # --- Events ----------------------------------------------------------------

    def handle(self, event: Event) -> None:
        """Transitions of §1.2.3.1."""
        kind = event.kind
        state = self.state  # the state when the event arrived (EXEC-1)
        if kind == SDSM_RESTORED:
            self._first()
        elif kind == SDSM_DISCOVERED:
            if state == UNDISCOVERED:
                self._discovered()
        elif kind in (SE_OFF, SE_ON):
            if state in (STATE_OFF, STATE_ON):
                self._change(event)
            elif state == UNUSABLE:
                self._try_back()
            if state in (STATE_OFF, STATE_ON):
                self._report_readings()
        elif kind == SE_ATTRIBUTES:
            if state in (STATE_OFF, STATE_ON):
                self._report_readings()
        elif kind in SE_NOT_USABLE or kind == SDSM_SERVED_MODE_LOST:
            if state in (STATE_OFF, STATE_ON):
                self._to_unusable()
        elif kind == SDSM_SERVED_MODES_BACK:
            if state == UNUSABLE:
                self._try_back()
        elif kind == AC_REQUEST:
            self._request(event.value)

    # --- First state (SRC-STATE-1) -----------------------------------------------

    def _first(self) -> None:
        source = self._source
        if not source.data.discovered:
            self.state = UNDISCOVERED
            source.send_ac(S_UNDISCOVERED)
            return
        if not is_usable(source.snapshot) or not source.served_offered():
            self.state = UNUSABLE
            source.send_ac(S_UNUSABLE)
            return
        stored = source.data.state
        if stored == OFF:
            self._set(STATE_OFF, None)
            source.send_ac(S_OFF)
        else:
            self._set(STATE_ON, stored)
            source.send_ac(S_ON, stored)
        self._entry(origin="restore")

    def _discovered(self) -> None:
        """SRC-STATE-8: discovered, to OFF; UNUSABLE if a served mode is not offered."""
        source = self._source
        source.data.state = OFF
        source.save()
        if source.served_offered():
            self._set(STATE_OFF, None)
            source.send_ac(S_OFF)
            self._entry(origin="discovered")
        else:
            self.state = UNUSABLE
            source.send_ac(S_UNUSABLE)

    # --- Entry of OFF / ON(m): check source entity (SRC-STATE-2) -----------------

    def _entry(self, origin: str) -> None:
        source = self._source
        target = self.current
        assert target is not None
        shown = _shown(source.snapshot)
        if origin == "request" and source.mrc.running:
            source.post(Event(SSTM_SEND, value=target))  # always sent (SRC-STATE-2)
        elif shown != target:
            source.post(Event(SSTM_SEND, value=target))
        elif target != OFF:
            if origin == "back":
                source.post(Event(SSTM_BACK, value=target))
            elif origin == "restore":
                source.post(Event(SSTM_RESTORED, value=target))

    def _set(self, state: str, mode: str | None) -> None:
        """A change of state, saved as the stored state (SRC-STATE-9)."""
        self.state = state
        self.mode = mode
        stored = mode if state == STATE_ON else OFF
        if self._source.data.state != stored:
            self._source.data.state = stored
            self._source.save()

    # --- Changes of the source entity (SRC-STATE-5) ------------------------------

    def _followed(self) -> bool:
        """[followed]: no confirmation running, or RETRY_WAIT(r) and another state shown."""
        mrc = self._source.mrc
        if not mrc.running:
            return True
        return mrc.waiting_retry and _shown(self._source.snapshot) != mrc.request

    def _change(self, event: Event) -> None:
        source = self._source
        shown = _shown(source.snapshot)
        if shown is None or shown == self.current or not self._followed():
            return
        if shown == OFF:
            self._set(STATE_OFF, None)
            source.send_ac(S_OFF)
            source.post(Event(SSTM_TAKEOVER, value=OFF))
        else:
            self._set(STATE_ON, shown)
            source.send_ac(S_ON, shown)
            source.post(Event(SSTM_TAKEOVER, value=shown))

    def _to_unusable(self) -> None:
        """SRC-STATE-6: the state asked stays the stored state."""
        self.state = UNUSABLE
        self._source.send_ac(S_UNUSABLE)
        self._source.post(Event(SSTM_UNUSABLE))

    def _try_back(self) -> None:
        """SRC-STATE-7: back to the stored state, not to the state shown."""
        source = self._source
        if not is_usable(source.snapshot) or not source.served_offered():
            return
        source.send_ac(S_USABLE)
        stored = source.data.state
        if stored == OFF:
            self._set(STATE_OFF, None)
        else:
            self._set(STATE_ON, stored)
        self._entry(origin="back")

    # --- Requests of the entity (SRC-STATE-3, SRC-STATE-4) -----------------------

    def _request(self, requested: str) -> None:
        source = self._source
        if self.state == UNUSABLE:
            if requested != source.data.state:
                source.data.state = requested
                source.save()
                source.post(Event(SSTM_MODE_CHANGED, value=requested))
            return
        if not self.operating or requested == self.current:
            return
        if requested == OFF:
            self._set(STATE_OFF, None)
        else:
            self._set(STATE_ON, requested)
        source.post(Event(SSTM_MODE_CHANGED, value=requested))
        self._entry(origin="request")

    # --- Current temperature and action (SRC-STATE-11, SRC-STATE-12) -------------

    def _report_readings(self) -> None:
        source = self._source
        before, now = source.prev_snapshot, source.snapshot
        temperature = _temperature(now)
        if temperature != _temperature(before):
            source.send_ac(S_TEMPERATURE, temperature)
        action = _action(now)
        if action != _action(before):
            source.send_ac(S_ACTION, action)


def _shown(snapshot: Snapshot | None) -> str | None:
    """The state the source entity shows: off or a mode; None when not usable."""
    return snapshot.state if is_usable(snapshot) else None


def _temperature(snapshot: Snapshot | None) -> float | None:
    if not is_usable(snapshot):
        # Safety net (not reached): only read from a usable source entity
        return None
    return as_number(snapshot.get("current_temperature"))


def _action(snapshot: Snapshot | None) -> str | None:
    if not is_usable(snapshot):
        # Safety net (not reached): only read from a usable source entity
        return None
    action = snapshot.get("hvac_action")
    return str(action) if action is not None else None
