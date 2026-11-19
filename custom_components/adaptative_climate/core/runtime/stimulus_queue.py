"""The stimulus queue of an entry (ARCHITECTURE ARCH-3).

Every stimulus enters it; the runtime takes the next one only when the
handling of the current one has ended (EXEC-3).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from ..model.events import Event


@dataclass
class Stimulus:
    """What comes from outside the entry: its initial events, per actor."""

    initial: list[tuple[str, Event]] = field(default_factory=list)


class StimulusQueue:
    """First in, first out."""

    def __init__(self) -> None:
        self._queue: deque[Stimulus] = deque()

    def put(self, stimulus: Stimulus) -> None:
        """Add a stimulus at the end."""
        self._queue.append(stimulus)

    def take(self) -> Stimulus | None:
        """The next stimulus, None when empty."""
        return self._queue.popleft() if self._queue else None

    def clear(self) -> None:
        """Drop the stimuli waiting (END-1)."""
        self._queue.clear()

    def __len__(self) -> int:
        return len(self._queue)
