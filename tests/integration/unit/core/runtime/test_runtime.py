"""core/runtime: steps, queues, stimuli, loop guard, unload (EXEC-1 to EXEC-4, ARCH-3, ARCH-11).

Test actors record what their functions get, in order.
"""

from __future__ import annotations

from typing import Any

from custom_components.adaptative_climate.core.model.events import (
    HA_START,
    HA_UNLOAD,
    TIMEOUT,
    Event,
)
from custom_components.adaptative_climate.core.runtime import actor as actor_module
from custom_components.adaptative_climate.core.runtime import runtime as runtime_module
from custom_components.adaptative_climate.core.runtime.actor import Actor
from custom_components.adaptative_climate.core.runtime.runtime import Runtime
from custom_components.adaptative_climate.core.runtime.stimulus_queue import (
    Stimulus,
    StimulusQueue,
)
from tests.integration.unit.core.kit import Clock, FakeNotify, FakeTimers


class Recorder:
    """A function: records (function, event kind); can react."""

    def __init__(self, name: str, log: list[str], react: Any = None) -> None:
        self.name = name
        self.log = log
        self.react = react

    def handle(self, event: Event) -> None:
        self.log.append(f"{self.name}:{event.kind}")
        if self.react is not None:
            self.react(event)


class TestActor(Actor):
    __test__ = False  # not a pytest class

    def __init__(self, actor_id: str, log: list[str], timers: FakeTimers) -> None:
        super().__init__(actor_id, timers)
        self.log = log
        self.ends = 0

    def end_of_step(self) -> None:
        self.ends += 1
        self.log.append(f"{self.actor_id}:end")


def runtime_with(*ids: str) -> tuple[Runtime, dict[str, TestActor], list[str], FakeNotify]:
    log: list[str] = []
    notify = FakeNotify()
    timers = FakeTimers(Clock())
    runtime = Runtime(notify)
    actors = {}
    for actor_id in ids:
        actors[actor_id] = TestActor(actor_id, log, timers)
        runtime.add_actor(actors[actor_id])
    return runtime, actors, log, notify


# --- EXEC-1: steps -------------------------------------------------------------------------


def test_exec_1_external_event_to_every_function_before_internal_events() -> None:
    runtime, actors, log, _ = runtime_with("a")
    a = actors["a"]

    def first_reacts(event: Event) -> None:
        if event.kind == "ext":
            a.post(Event("int1"))
        elif event.kind == "int1":
            a.post(Event("int2"))  # emitted while the internal queue is emptied: at the end

    a.functions = [Recorder("f1", log, first_reacts), Recorder("f2", log)]
    runtime.submit(Stimulus([("a", Event("ext"))]))
    assert log == [
        "f1:ext", "f2:ext",
        "f1:int1", "f2:int1",
        "f1:int2", "f2:int2",
        "a:end",
    ]


def test_exec_1_a_step_is_not_interrupted_by_another_actor() -> None:
    """Events to another actor wait in its queue until the end of the step."""
    runtime, actors, log, _ = runtime_with("a", "b")
    a, b = actors["a"], actors["b"]

    def a_reacts(event: Event) -> None:
        if event.kind == "ext":
            a.send("b", Event("to_b"))
            a.post(Event("int"))

    a.functions = [Recorder("a", log, a_reacts)]
    b.functions = [Recorder("b", log)]
    runtime.submit(Stimulus([("a", Event("ext"))]))
    assert log == ["a:ext", "a:int", "a:end", "b:to_b", "b:end"]


def test_exec_1_end_of_step_hook_when_both_queues_are_empty() -> None:
    """Two events already waiting for one actor: its hook runs once, after the second."""
    runtime, actors, log, _ = runtime_with("a")
    actors["a"].functions = [Recorder("f", log)]
    runtime.submit(Stimulus([("a", Event("e1")), ("a", Event("e2"))]))
    assert log == ["f:e1", "f:e2", "a:end"]


# --- EXEC-2, EXEC-3: order, one stimulus at a time ----------------------------------------------------


def test_exec_2_events_of_one_sender_keep_their_order() -> None:
    runtime, actors, log, _ = runtime_with("a", "b")
    a = actors["a"]
    a.functions = [Recorder("a", log, lambda e: [a.send("b", Event(k)) for k in ("x", "y", "z")]
                            if e.kind == "go" else None)]
    actors["b"].functions = [Recorder("b", log)]
    runtime.submit(Stimulus([("a", Event("go"))]))
    assert [entry for entry in log if entry.startswith("b:") and entry != "b:end"] == [
        "b:x", "b:y", "b:z"
    ]


def test_exec_3_a_stimulus_submitted_during_another_one_waits() -> None:
    runtime, actors, log, _ = runtime_with("a")
    a = actors["a"]

    def reacts(event: Event) -> None:
        if event.kind == "first":
            runtime.submit(Stimulus([("a", Event("second"))]))
            a.post(Event("first_internal"))

    a.functions = [Recorder("f", log, reacts)]
    ends: list[str] = []
    runtime.on_stimulus_end = lambda: ends.append(log[-1])
    runtime.submit(Stimulus([("a", Event("first"))]))
    assert log == ["f:first", "f:first_internal", "a:end", "f:second", "a:end"]
    assert len(ends) == 2


def test_exec_4_start_in_start_order() -> None:
    runtime, actors, log, _ = runtime_with("entity", "source", "monitoring")
    for actor_id, actor in actors.items():
        actor.functions = [Recorder(actor_id, log)]
    runtime.start()
    starts = [entry for entry in log if entry.endswith(HA_START)]
    assert starts == [f"entity:{HA_START}", f"source:{HA_START}", f"monitoring:{HA_START}"]


# --- ARCH-11: loop guard --------------------------------------------------------------------------


def test_arch_11_internal_loop_is_stopped_and_logged(monkeypatch: Any) -> None:
    monkeypatch.setattr(actor_module, "INTERNAL_LIMIT", 10)
    runtime, actors, log, notify = runtime_with("a")
    a = actors["a"]
    a.functions = [Recorder("f", log, lambda e: a.post(Event("again")))]
    runtime.submit(Stimulus([("a", Event("go"))]))
    assert notify.logged("error", "Loop guard")
    runtime.submit(Stimulus([("a", Event("next")) ]))  # the runtime goes on
    assert "f:next" in log


def test_arch_11_loop_between_actors_is_stopped_and_logged(monkeypatch: Any) -> None:
    monkeypatch.setattr(runtime_module, "STEP_LIMIT", 20)
    runtime, actors, log, notify = runtime_with("a", "b")
    actors["a"].functions = [Recorder("a", log, lambda e: actors["a"].send("b", Event("ping")))]
    actors["b"].functions = [Recorder("b", log, lambda e: actors["b"].send("a", Event("pong")))]
    runtime.submit(Stimulus([("a", Event("go"))]))
    assert notify.logged("error", "too many steps")
    assert len(log) < 50


# --- Timers, unload -------------------------------------------------------------------------------


def test_arch_7_end_of_a_timer_cancelled_or_restarted_is_ignored() -> None:
    runtime, actors, log, _ = runtime_with("a")
    a = actors["a"]
    a.functions = [Recorder("f", log)]
    a.timers.start("t", 10)
    assert a.timers.running("t")
    a.timers.start("t", 10)  # restarted: the first end is stale
    got = lambda: [entry for entry in log if entry.startswith("f:")]  # noqa: E731
    runtime.submit(Stimulus([("a", Event(TIMEOUT, "timer", ("t", 1)))]))
    assert got() == []
    runtime.submit(Stimulus([("a", Event(TIMEOUT, "timer", ("t", 2)))]))
    assert got() == [f"f:{TIMEOUT}"]
    assert not a.timers.running("t")
    runtime.submit(Stimulus([("a", Event(TIMEOUT, "timer", ("t", 2)))]))  # ended already
    assert got() == [f"f:{TIMEOUT}"]


def test_end_1_unload_stops_at_once() -> None:
    runtime, actors, log, _ = runtime_with("a", "b")
    a = actors["a"]
    a.functions = [Recorder("a", log)]
    actors["b"].functions = [Recorder("b", log)]
    a.timers.start("t", 10)
    a.post(Event("left_over"))
    runtime.stop()
    assert not a.timers.running("t")
    assert log == [f"a:{HA_UNLOAD}", f"b:{HA_UNLOAD}"]
    runtime.submit(Stimulus([("a", Event("after"))]))
    runtime.send("a", Event("after"))
    assert "a:after" not in log


def test_arch_3_stimulus_queue() -> None:
    queue = StimulusQueue()
    assert queue.take() is None
    queue.put(Stimulus())
    queue.put(Stimulus())
    assert len(queue) == 2
    queue.clear()
    assert len(queue) == 0


def test_end_1_unload_during_a_stimulus_drops_the_next_ones() -> None:
    runtime, actors, log, _ = runtime_with("a")
    a = actors["a"]

    def reacts(event: Event) -> None:
        if event.kind == "first":
            runtime.submit(Stimulus([("a", Event("second"))]))
            runtime.stop()

    a.functions = [Recorder("f", log, reacts)]
    runtime.submit(Stimulus([("a", Event("first"))]))
    assert "f:second" not in log
