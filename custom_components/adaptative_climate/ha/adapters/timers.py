"""Timer and clock ports (ARCHITECTURE ARCH-7): Home Assistant scheduled callbacks."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from functools import partial
from typing import TYPE_CHECKING

from homeassistant.core import HassJob, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from ...core.model.events import TIMEOUT, Event

if TYPE_CHECKING:
    from ..entry.host import EntryHost


class TimerAdapter:
    """Each end of a timer is a stimulus for the actor that owns it."""

    def __init__(self, hass: HomeAssistant, host: EntryHost) -> None:
        self._hass = hass
        self._host = host
        self._handles: dict[tuple[str, str], Callable[[], None]] = {}

    def start(self, owner: str, name: str, number: int, seconds: float) -> None:
        """Start, or restart, a timer."""
        self.cancel(owner, name)
        job = HassJob(partial(self._ended, owner, name, number), cancel_on_shutdown=True)
        self._handles[(owner, name)] = async_call_later(self._hass, seconds, job)

    def cancel(self, owner: str, name: str) -> None:
        """Cancel a timer."""
        handle = self._handles.pop((owner, name), None)
        if handle is not None:
            handle()

    def cancel_all(self) -> None:
        """Every timer cancelled (END-1)."""
        # Safety net (not reached): the actors have cancelled their timers at the unload
        for handle in self._handles.values():
            handle()
        self._handles.clear()

    @callback
    def _ended(self, owner: str, name: str, number: int, _now: datetime) -> None:
        self._handles.pop((owner, name), None)
        self._host.submit(owner, Event(TIMEOUT, "timer", (name, number)))


class ClockAdapter:
    """Time of Home Assistant."""

    def now(self) -> str:
        """Now, ISO format."""
        return dt_util.utcnow().isoformat()
