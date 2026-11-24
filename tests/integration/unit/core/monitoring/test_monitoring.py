"""core/monitoring: what the spec says of the monitoring but no stimulus from outside reaches."""

from __future__ import annotations

from custom_components.adaptative_climate.core.model.events import M_DOWN, M_UP, TIMEOUT, Event
from custom_components.adaptative_climate.core.model.problems import Problem
from tests.integration.unit.core.kit import Core, climate

HEATER = "climate.heater"


def started() -> Core:
    core = Core({"heat_entity": HEATER}, snapshots={HEATER: climate("off", ["heat"])})
    core.start()
    return core


def problem(delay: float = 60) -> Problem:
    return Problem("test", (HEATER,), "sources", delay, "a test problem")


def test_mon_life_down_of_a_problem_it_does_not_have_is_ignored() -> None:
    """§4.4: a X=>M_down(p) for a problem the monitoring does not have is ignored."""
    core = started()
    core.stimulus((core.monitoring.actor_id, Event(M_DOWN, HEATER, problem())))
    assert core.notify.events == []
    assert core.notify.logs == []


def test_mon_send_up_of_a_problem_it_has_already_changes_nothing() -> None:
    core = started()
    monitoring = core.monitoring.actor_id
    core.stimulus((monitoring, Event(M_UP, HEATER, problem())))
    core.advance(30)
    core.stimulus((monitoring, Event(M_UP, HEATER, problem())))
    core.advance(31)  # its delay counts from the first up
    assert [event["status"] for event in core.notify.events] == ["started"]


def test_mon_life_end_of_a_delay_cancelled_is_ignored() -> None:
    core = started()
    monitoring = core.monitoring.actor_id
    core.stimulus((monitoring, Event(M_UP, HEATER, problem())))
    core.stimulus((monitoring, Event(M_DOWN, HEATER, problem())))
    core.stimulus((monitoring, Event(TIMEOUT, "timer", ("test:climate.heater", 1))))
    assert core.notify.events == []
