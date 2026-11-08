"""Phase of the combined HEAT_COOL.

Without a heat_cool source, HEAT_COOL runs the heat or the cool source:
its phase. The sources cannot tell this mode (a heater in heat may be in
heat or in a phase of HEAT_COOL), so it is kept here.

- wanted_phase: pure function choosing the phase. Below the low target:
  heat. Above the high target: cool. In between: the current phase is
  kept (no oscillation); when entering, the closest target. Low above
  high (a source took over): the current phase is kept too.
- CombinedPhase: keeps the phase.
  - start: sets the phase and waits for the sources to show it
    (SETTLE_TIME); on_wait_end runs at the end of the wait.
  - update: on each source update. The source has the upper hand:
    another mode or off set on it ends the combined mode, unless the
    entity is waiting or switching. After a restart, brings the phase
    back once a source runs heat or cool.
  - can_switch: the phase may switch to follow the temperature.
  - leave, end_wait, restore, as_dict.

CombinedPhase does not call the sources: the entity checks the phase on
each update and runs the source of a new phase through ModeTracker.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant, callback

from .model import PHASES, SETTLE_TIME
from .timer import Timer


def wanted_phase(
    current: HVACMode | None,
    temperature: float | None,
    low: float | None,
    high: float | None,
    running: HVACMode,
) -> HVACMode:
    """Return the phase the combined HEAT_COOL should run in.

    Below the low target: heat. Above the high target: cool. In between,
    the current phase is kept; when entering (current is None), the phase
    of the closest target. Without room temperature, the current phase,
    else the heat or cool source already running, else heat.

    The low target can end up above the high one (a source took over and
    the other source could not follow): between them, both apply, so the
    current phase is kept too, not switched back and forth.
    """
    if temperature is not None and low is not None and high is not None:
        below = temperature < low
        above = temperature > high
        if below and not above:
            return HVACMode.HEAT
        if above and not below:
            return HVACMode.COOL
        if current is None:
            return HVACMode.HEAT if temperature - low <= high - temperature else HVACMode.COOL
    if current is not None:
        return current
    return running if running in PHASES else HVACMode.HEAT


class CombinedPhase:
    """The phase of the combined HEAT_COOL: the heat or cool source it runs.

    That mode cannot be read from the sources, so it is kept here. The
    source has the upper hand: another mode or off set on it ends the mode.
    """

    def __init__(
        self, hass: HomeAssistant, enabled: bool, on_wait_end: Callable[[], None]
    ) -> None:
        """Initialize, outside of the combined mode.

        enabled: HEAT_COOL is combined (no heat_cool source). on_wait_end
        runs when the wait for the sources to show a new phase ends.
        """
        self.enabled = enabled
        # The mode the source runs in (heat or cool), None outside of it.
        self.phase: HVACMode | None = None
        # After a phase switch, the sources may still show the previous one
        # for a while.
        self._wait = Timer(hass)
        self._on_wait_end = on_wait_end
        # The combined mode was on before a restart: it is restored once the
        # heat and cool sources are usable (see update).
        self._restore = False

    @property
    def waiting(self) -> bool:
        """Return True while waiting for the sources to show the phase."""
        return self._wait.active

    def restore(self, data: dict[str, Any]) -> None:
        """Restore the combined mode saved before a restart."""
        self._restore = self.enabled and data.get("heat_cool") is True

    def as_dict(self) -> dict[str, Any]:
        """Return the data saved across restarts."""
        return {"heat_cool": self.phase is not None or self._restore}

    @callback
    def update(
        self, running: HVACMode, usable: Callable[[], bool], switching: bool
    ) -> None:
        """Leave the combined mode when its source left the phase elsewhere.

        While the sources may still show the previous phase (see start), or
        while the entity switches modes, this is not judged.

        After a restart, the combined mode comes back with the phase its
        source runs in, once the sources are usable (usable returns True).
        """
        if self._restore:
            if running in PHASES:
                self.phase = running
                self._restore = False
            elif usable():
                # Both sources are usable and none runs: it was turned off.
                self._restore = False
        if self.phase is None:
            return
        if running == self.phase:
            self.end_wait()
            return
        if self.waiting or switching:
            return
        self.phase = None

    def can_switch(self, switching: bool) -> bool:
        """Return True when the phase may switch to follow the temperature."""
        return self.phase is not None and not self.waiting and not switching

    @callback
    def start(self, phase: HVACMode) -> None:
        """Set the phase and wait for the sources to show it."""
        self.phase = phase
        self._wait.start(SETTLE_TIME, self._on_wait_end)

    @callback
    def end_wait(self) -> None:
        """Stop waiting for the sources to show the phase."""
        self._wait.cancel()

    @callback
    def leave(self) -> None:
        """Leave the combined mode."""
        self.phase = None
        self.end_wait()
