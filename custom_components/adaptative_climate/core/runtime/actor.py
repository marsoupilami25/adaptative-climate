"""Frame of an actor: queues, steps, end-of-step hook, timers (EXEC-1, ARCH-5, ARCH-7)."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Protocol

from ..model.events import TIMEOUT, Event
from ..model.ports import TimerPort

if TYPE_CHECKING:
    from .runtime import Runtime

#: Internal events of one step beyond which a loop is assumed (ARCH-11).
INTERNAL_LIMIT = 1000


class LoopGuardError(Exception):
    """Two functions keep triggering each other: a bug (ARCH-11)."""


class Function(Protocol):
    """A function of an actor, with its own state machine."""

    def handle(self, event: Event) -> None:
        """Handle the events its state machine knows, ignore the others."""


class ActorTimers:
    """The timers of an actor: the decision side (ARCH-7).

    Each start carries a number; an end whose timer was cancelled or
    restarted since is ignored.
    """

    def __init__(self, owner: str, port: TimerPort) -> None:
        self._owner = owner
        self._port = port
        self._numbers: dict[str, int] = {}
        self._running: set[str] = set()

    def start(self, name: str, seconds: float) -> None:
        """Start, or restart, a timer."""
        number = self._numbers.get(name, 0) + 1
        self._numbers[name] = number
        self._running.add(name)
        self._port.start(self._owner, name, number, max(seconds, 0.0))

    def cancel(self, name: str) -> None:
        """Cancel a timer, if it runs."""
        if name in self._running:
            self._running.discard(name)
            self._numbers[name] = self._numbers.get(name, 0) + 1
            self._port.cancel(self._owner, name)

    def running(self, name: str) -> bool:
        """Whether the timer runs."""
        return name in self._running

    def accept(self, event: Event) -> bool:
        """Whether an end of timer is current; it then no longer runs."""
        name, number = event.value
        if name in self._running and self._numbers.get(name) == number:
            self._running.discard(name)
            return True
        return False

    def cancel_all(self) -> None:
        """Cancel every timer (END-1)."""
        for name in list(self._running):
            self.cancel(name)


class Actor:
    """An actor: external queue (held by the runtime), internal queue, functions."""

    def __init__(self, actor_id: str, timer_port: TimerPort) -> None:
        self.actor_id = actor_id
        self.timers = ActorTimers(actor_id, timer_port)
        self.functions: list[Function] = []
        self._internal: deque[Event] = deque()
        self._runtime: Runtime | None = None

    def attach(self, runtime: Runtime) -> None:
        """Given to the runtime."""
        self._runtime = runtime

    # --- Sending ---------------------------------------------------------------

    def send(self, target: str, event: Event) -> None:
        """Send an event to another actor: its external queue."""
        assert self._runtime is not None
        self._runtime.send(target, event)

    def post(self, event: Event) -> None:
        """Send an event to the functions of this actor: the internal queue."""
        self._internal.append(event)

    # --- Step (EXEC-1) ---------------------------------------------------------

    def step(self, event: Event) -> None:
        """One event of the external queue, then the internal queue until empty."""
        if event.kind == TIMEOUT and not self.timers.accept(event):
            return
        self.before_step(event)
        for function in self.functions:
            function.handle(event)
        count = 0
        while self._internal:
            count += 1
            if count > INTERNAL_LIMIT:
                raise LoopGuardError(f"{self.actor_id}: internal events keep coming")
            internal = self._internal.popleft()
            for function in self.functions:
                function.handle(internal)

    def before_step(self, event: Event) -> None:
        """Called before the functions get an external event."""

    def end_of_step(self) -> None:
        """Hook: both queues are empty (ARCH-5)."""

    def drop_internal(self) -> None:
        """Drop the internal events left (loop guard, END-1)."""
        self._internal.clear()
