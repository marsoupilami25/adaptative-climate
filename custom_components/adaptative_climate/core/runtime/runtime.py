"""The runtime of an entry: start order, stimulus handling, loop guard.

EXEC-1 to EXEC-4, ARCHITECTURE ARCH-3, ARCH-5, ARCH-11, §5.
"""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Callable

from ..model.events import HA_START, HA_UNLOAD, Event
from ..model.ports import NotifyPort
from .actor import Actor, LoopGuardError
from .stimulus_queue import Stimulus, StimulusQueue

#: Steps of one stimulus beyond which a loop is assumed (ARCH-11).
STEP_LIMIT = 1000


class Runtime:
    """Runs one entry: one stimulus at a time, handled to the end (EXEC-3).

    The external queues of the actors are kept as one queue of deliveries,
    in the order of sending: the order of each sender is kept (EXEC-2), and
    the order between senders is the order of sending in the entry.
    """

    def __init__(self, notify: NotifyPort) -> None:
        self._notify = notify
        self._actors: dict[str, Actor] = {}
        self._order: list[str] = []
        self._stimuli = StimulusQueue()
        self._deliveries: deque[tuple[str, Event]] = deque()
        self._pending: Counter[str] = Counter()
        self._busy = False
        self._stopped = False
        self._history: deque[str] = deque(maxlen=20)
        self.on_stimulus_end: Callable[[], None] | None = None

    # --- Actors ----------------------------------------------------------------

    def add_actor(self, actor: Actor) -> None:
        """Add an actor, in start order (EXEC-4: the entity first)."""
        actor.attach(self)
        self._actors[actor.actor_id] = actor
        self._order.append(actor.actor_id)

    def send(self, target: str, event: Event) -> None:
        """Put an event in the external queue of an actor."""
        if self._stopped or target not in self._actors:
            return
        self._deliveries.append((target, event))
        self._pending[target] += 1

    # --- Stimuli ---------------------------------------------------------------

    def start(self) -> None:
        """The start of the entry: one stimulus, in start order (EXEC-4)."""
        self.submit(Stimulus([(actor_id, Event(HA_START, "HA")) for actor_id in self._order]))

    def stop(self) -> None:
        """Unload (END-1): every actor stops at once; nothing more is handled."""
        self._stopped = True
        self._stimuli.clear()
        self._deliveries.clear()
        self._pending.clear()
        for actor in self._actors.values():
            actor.drop_internal()
            actor.timers.cancel_all()
            actor.step(Event(HA_UNLOAD, "HA"))

    def submit(self, stimulus: Stimulus) -> None:
        """Put a stimulus in the stimulus queue; handle the queue if idle (ARCH-3)."""
        if self._stopped:
            return
        self._stimuli.put(stimulus)
        if self._busy:
            return
        self._busy = True
        try:
            while (current := self._stimuli.take()) is not None:
                if self._stopped:
                    break
                self._handle(current)
                if self.on_stimulus_end is not None:
                    self.on_stimulus_end()
        finally:
            self._busy = False

    def _handle(self, stimulus: Stimulus) -> None:
        """Begins with the initial events; ends when every queue is empty."""
        for target, event in stimulus.initial:
            self.send(target, event)
        steps = 0
        self._history.clear()
        while self._deliveries:
            target, event = self._deliveries.popleft()
            self._pending[target] -= 1
            actor = self._actors[target]
            steps += 1
            self._history.append(f"{event.sender}->{target}: {event.kind}")
            try:
                if steps > STEP_LIMIT:
                    raise LoopGuardError("too many steps in one stimulus")
                actor.step(event)
                if self._pending[target] == 0:
                    actor.end_of_step()
            except LoopGuardError as err:
                self._notify.log(
                    "error",
                    f"Loop guard: {err}; last events: {list(self._history)}; "
                    "the events left are dropped",
                )
                self._deliveries.clear()
                self._pending.clear()
                for each in self._actors.values():
                    each.drop_internal()
                return
