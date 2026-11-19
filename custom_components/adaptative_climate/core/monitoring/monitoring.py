"""The monitoring actor (spec §4, ARCHITECTURE §4.3).

An external queue only, no functions: one state machine per problem, each
with its delay timer. It reads no data of the other actors and sends them
nothing (MON-ROLE-1).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..model.entry_config import EntryConfig
from ..model.events import HA_START, M_DOWN, M_UP, TIMEOUT, Event
from ..model.ports import ClockPort, NotifyPort, TimerPort
from ..model.problems import Problem
from ..runtime.actor import Actor
from .problem_lifecycle import REPORTED, ProblemLifecycle

MONITORING = "monitoring"


class Monitoring(Actor):
    """Waits for the delay of each problem, reports it and shows it."""

    def __init__(
        self,
        entry: EntryConfig,
        timer_port: TimerPort,
        notify: NotifyPort,
        clock: ClockPort,
        sensor_entity_ids: Callable[[str], str | None],
    ) -> None:
        super().__init__(MONITORING, timer_port)
        self.entry = entry
        self._notify = notify
        self._clock = clock
        self._sensor_entity_ids = sensor_entity_ids
        self._problems: dict[Problem, ProblemLifecycle] = {}
        self._by_timer: dict[str, Problem] = {}

    def step(self, event: Event) -> None:
        """No functions: the monitoring handles its events itself."""
        if event.kind == TIMEOUT and not self.timers.accept(event):
            return
        kind = event.kind
        if kind == HA_START:
            self._problems.clear()  # MON-SEND-3: it starts with no problem
            self._by_timer.clear()
        elif kind == M_UP:
            self._up(event.value)
        elif kind == M_DOWN:
            self._down(event.value)
        elif kind == TIMEOUT:
            problem = self._by_timer.get(event.value[0])
            if problem is not None:
                self._report(self._problems[problem])

    def _up(self, problem: Problem) -> None:
        if problem in self._problems:
            return
        lifecycle = ProblemLifecycle(problem, self._clock.now())
        self._problems[problem] = lifecycle
        self._by_timer[lifecycle.timer] = problem
        if problem.delay <= 0:
            self._report(lifecycle)  # 0: at once
        else:
            self.timers.start(lifecycle.timer, problem.delay)

    def _down(self, problem: Problem) -> None:
        lifecycle = self._problems.pop(problem, None)
        if lifecycle is None:
            return  # a problem the monitoring does not have: ignored
        self._by_timer.pop(lifecycle.timer, None)
        self.timers.cancel(lifecycle.timer)
        if lifecycle.state == REPORTED:
            message = f"{self.entry.name}: problem ended: {lifecycle.problem.message}"
            self._notify.log("info", message)
            self._fire(lifecycle, "ended", message)

    def _report(self, lifecycle: ProblemLifecycle) -> None:
        lifecycle.state = REPORTED
        message = f"{self.entry.name}: {lifecycle.problem.message}"
        self._notify.log("warning", message)
        self._fire(lifecycle, "started", message)

    def _fire(self, lifecycle: ProblemLifecycle, status: str, message: str) -> None:
        """MON-LIFE-2, MON-LIFE-3."""
        self._notify.fire_problem(
            {
                "entry_id": self.entry.entry_id,
                "name": self.entry.name,
                "entity_id": self._sensor_entity_ids(lifecycle.problem.sensor),
                "status": status,
                "message": message,
                "problem": self._describe(lifecycle),
            }
        )

    @staticmethod
    def _describe(lifecycle: ProblemLifecycle) -> dict[str, Any]:
        return {**lifecycle.problem.describe(), "since": lifecycle.since}

    # --- Shown by the binary sensors (spec §4.1) -------------------------------------

    def reported(self, sensor: str) -> list[dict[str, Any]]:
        """The problems reported for a sensor (MON-SENS-1, MON-SENS-2)."""
        return [
            self._describe(lifecycle)
            for lifecycle in self._problems.values()
            if lifecycle.state == REPORTED and lifecycle.problem.sensor == sensor
        ]

