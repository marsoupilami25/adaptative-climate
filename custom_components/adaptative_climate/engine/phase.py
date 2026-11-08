"""Phase of the combined HEAT_COOL.

Without a heat_cool source, HEAT_COOL runs the heat or the cool source:
its phase. The sources cannot tell this mode (a heater in heat may be in
heat or in a phase of HEAT_COOL), so it is kept here.

- wanted_phase: pure function choosing the phase from the room
  temperatures: the sensor, else those of the heat and cool sources.
  Heat when all are below the low target, cool when all are above the
  high one. Otherwise (in between, or the sources contradict each other)
  the current phase is kept: no oscillation; when entering, the closest
  target to their mean. Low above high (a source took over): the current
  phase is kept too.
- CombinedPhase: keeps the phase.
  - start: sets the phase and waits for the sources to show it
    (SETTLE_TIME); on_wait_end runs at the end of the wait. The phase is
    then held for the minimum phase duration: it does not switch by
    itself before (on_wait_end runs at the end too).
  - update: on each source update. The source has the upper hand:
    another mode or off set on it ends the combined mode, unless the
    entity is waiting or switching. A source of the phase that is
    unavailable is waited for: the combined mode is kept. After a restart,
    brings the phase back once a source runs heat or cool (not held).
  - can_switch: the phase may switch to follow the temperature; forced
    (new targets from the user) ignores the hold.
  - leave, end_wait, stop_timers, restore, as_dict.

CombinedPhase does not call the sources: the entity checks the phase on
each update and runs the source of a new phase through ModeTracker.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import timedelta
from typing import Any

from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant, callback

from .model import PHASES, SETTLE_TIME
from .timer import Timer


def wanted_phase(
    current: HVACMode | None,
    temperatures: Sequence[float],
    low: float | None,
    high: float | None,
    running: HVACMode,
) -> HVACMode:
    """Return the phase the combined HEAT_COOL should run in.

    temperatures: the room sensor, else the readings of the heat and cool
    sources (each one may be missing). All below the low target: heat. All
    above the high target: cool. Otherwise the current phase is kept: in
    between, or when the sources contradict each other (the heater reads
    above high while the AC reads below low, each one near its own sensor):
    following either would switch back and forth. When entering (current
    is None), the phase of the closest target to their mean. Without room
    temperature, the current phase, else the heat or cool source already
    running, else heat.

    The low target can end up above the high one (a source took over and
    the other source could not follow): between them, both apply, so the
    current phase is kept too, not switched back and forth.
    """
    if temperatures and low is not None and high is not None:
        below = all(value < low for value in temperatures)
        above = all(value > high for value in temperatures)
        if below and not above:
            return HVACMode.HEAT
        if above and not below:
            return HVACMode.COOL
        if current is None:
            temperature = sum(temperatures) / len(temperatures)
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
        self,
        hass: HomeAssistant,
        enabled: bool,
        on_wait_end: Callable[[], None],
        min_duration: timedelta = timedelta(),
    ) -> None:
        """Initialize, outside of the combined mode.

        enabled: HEAT_COOL is combined (no heat_cool source). on_wait_end
        runs when the wait for the sources to show a new phase ends, and
        when the phase may switch again (min_duration after it started).
        """
        self.enabled = enabled
        # The mode the source runs in (heat or cool), None outside of it.
        self.phase: HVACMode | None = None
        # After a phase switch, the sources may still show the previous one
        # for a while.
        self._wait = Timer(hass)
        self._on_wait_end = on_wait_end
        # A new phase is held this long before switching by itself again.
        self._min_duration = min_duration
        self._hold = Timer(hass)
        # The combined mode was on before a restart: it is restored once the
        # heat and cool sources are usable (see update).
        self._restore = False

    @property
    def waiting(self) -> bool:
        """Return True while waiting for the sources to show the phase."""
        return self._wait.active

    @property
    def holding(self) -> bool:
        """Return True while the phase is held (minimum phase duration)."""
        return self._hold.active

    def restore(self, data: dict[str, Any]) -> None:
        """Restore the combined mode saved before a restart."""
        self._restore = self.enabled and data.get("heat_cool") is True

    def as_dict(self) -> dict[str, Any]:
        """Return the data saved across restarts."""
        return {"heat_cool": self.phase is not None or self._restore}

    @callback
    def update(
        self,
        running: HVACMode,
        usable: Callable[[], bool],
        switching: bool,
        lost: Callable[[HVACMode], bool] = lambda _phase: False,
    ) -> None:
        """Leave the combined mode when its source left the phase elsewhere.

        While the sources may still show the previous phase (see start), or
        while the entity switches modes, this is not judged. Nor while the
        source of the phase is unavailable (lost) and no source runs: the
        combined mode goes on once it is back in the phase; back off, it
        ends.

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
        if running is HVACMode.OFF and lost(self.phase):
            return
        self.leave()

    def can_switch(self, switching: bool, *, forced: bool = False) -> bool:
        """Return True when the phase may switch to follow the temperature.

        forced: the user set new targets, the hold of the phase is ignored.
        """
        return (
            self.phase is not None
            and not self.waiting
            and not switching
            and (forced or not self.holding)
        )

    @callback
    def start(self, phase: HVACMode) -> None:
        """Set the phase, wait for the sources to show it, then hold it."""
        self.phase = phase
        self._wait.start(SETTLE_TIME, self._on_wait_end)
        if self._min_duration > timedelta():
            self._hold.start(self._min_duration, self._on_wait_end)
        else:
            self._hold.cancel()

    @callback
    def end_wait(self) -> None:
        """Stop waiting for the sources to show the phase."""
        self._wait.cancel()

    @callback
    def leave(self) -> None:
        """Leave the combined mode."""
        self.phase = None
        self.stop_timers()

    @callback
    def stop_timers(self) -> None:
        """Stop waiting for the sources and holding the phase."""
        self.end_wait()
        self._hold.cancel()
