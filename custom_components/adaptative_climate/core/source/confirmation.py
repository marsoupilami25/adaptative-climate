"""Smrc: mode request confirmation of a source (spec §1.2.4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..model.events import (
    SDSM_SERVED_MODE_LOST,
    SE_CALL_FAILED,
    SE_NOT_USABLE,
    SE_OFF,
    SE_ON,
    SET_HVAC_MODE,
    SMRC_CONFIRMED,
    SSTM_SEND,
    Call,
    Event,
)
from ..model.values import OFF, is_usable

if TYPE_CHECKING:
    from .source import Source

IDLE = "IDLE"
CONFIRMING = "CONFIRMING"
RETRY_WAIT = "RETRY_WAIT"

CONFIRM_TIMER = "confirm"
RETRY_TIMER = "retry"


class ModeRequestConfirmation:
    """Smrc: sends the state asked, checks that it is shown, retries."""

    def __init__(self, source: Source) -> None:
        self._source = source
        self.state = IDLE
        self.request: str | None = None  # r
        #: Out of sync, from a confirm timeout where r is not shown (SRC-REQ-9).
        self.out_of_sync = False

    @property
    def running(self) -> bool:
        """A mode request confirmation is running: CONFIRMING(r) or RETRY_WAIT(r)."""
        return self.state != IDLE

    @property
    def waiting_retry(self) -> bool:
        """In RETRY_WAIT(r)."""
        return self.state == RETRY_WAIT

    def handle(self, event: Event) -> None:
        """Transitions of §1.2.4."""
        kind = event.kind
        source = self._source
        if kind == SSTM_SEND:
            if self.state == RETRY_WAIT:
                source.timers.cancel(RETRY_TIMER)
            self.request = event.value
            self.out_of_sync = False
            self._send()
            source.timers.start(CONFIRM_TIMER, source.entry.request_confirmation_timer)
            self.state = CONFIRMING
        elif not self.running:
            return
        elif kind in (SE_OFF, SE_ON):
            shown = self._shown_request()
            if shown:
                self._confirmed()
            elif self.state == RETRY_WAIT:
                # SRC-REQ-8: the source entity is master, followed as a takeover
                source.timers.cancel(RETRY_TIMER)
                self._idle()
        elif kind == SE_CALL_FAILED:
            call: Call = event.value
            if call.service == SET_HVAC_MODE and self.state == CONFIRMING:
                source.notify.log(
                    "warning",
                    f"{source.cfg.entity_id}: set_hvac_mode({self.request}) failed",
                )
        elif kind in SE_NOT_USABLE or kind == SDSM_SERVED_MODE_LOST:
            source.timers.cancel(CONFIRM_TIMER)
            source.timers.cancel(RETRY_TIMER)
            self._idle()
        elif event.is_timeout(CONFIRM_TIMER) and self.state == CONFIRMING:
            if self._shown_request():
                self._confirmed()
            else:
                self.out_of_sync = True  # SRC-REQ-5, MON-SRC-3
                self.state = RETRY_WAIT
                source.timers.start(RETRY_TIMER, source.entry.request_retry_timer)
        elif event.is_timeout(RETRY_TIMER) and self.state == RETRY_WAIT:
            self._send()
            source.timers.start(CONFIRM_TIMER, source.entry.request_confirmation_timer)
            self.state = CONFIRMING

    def _shown_request(self) -> bool:
        snapshot = self._source.snapshot
        return is_usable(snapshot) and snapshot.state == self.request

    def _send(self) -> None:
        self._source.port.call(Call(SET_HVAC_MODE), {"hvac_mode": self.request})

    def _confirmed(self) -> None:
        source = self._source
        source.timers.cancel(CONFIRM_TIMER)
        source.timers.cancel(RETRY_TIMER)
        request = self.request
        self._idle()
        if request is not None and request != OFF:
            source.post(Event(SMRC_CONFIRMED, value=request))

    def _idle(self) -> None:
        self.state = IDLE
        self.out_of_sync = False
