"""One-shot timer over async_call_later.

Timer runs an action once after a delay. Starting it again replaces the
running one; it is no longer active when the action runs. Used for the
settle time (TargetSync) and the wait for a new phase (CombinedPhase).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later


class Timer:
    """Run an action once after a delay, unless cancelled before."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the timer, not running."""
        self._hass = hass
        self._cancel: CALLBACK_TYPE | None = None

    @property
    def active(self) -> bool:
        """Return True while the timer runs."""
        return self._cancel is not None

    @callback
    def start(self, delay: timedelta, action: Callable[[], None]) -> None:
        """Run action after delay, replacing any running timer."""
        self.cancel()

        @callback
        def _fired(_now: datetime) -> None:
            # Not active anymore when the action runs.
            self._cancel = None
            action()

        self._cancel = async_call_later(self._hass, delay, _fired)

    @callback
    def cancel(self) -> None:
        """Stop the timer, if it runs."""
        if self._cancel is not None:
            self._cancel()
            self._cancel = None
