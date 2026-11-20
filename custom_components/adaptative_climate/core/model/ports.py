"""The ports of the core (ARCHITECTURE ARCH-2, §6).

What the core needs from outside, said in its own words. The component
`ha/adapters` implements them with Home Assistant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .events import Call
from .values import Snapshot


class SourceEntityPort(Protocol):
    """A source entity: its snapshot at start, and the service calls S=>SE_*."""

    def snapshot(self) -> Snapshot | None:
        """The state and attributes now; None when missing (SRC-DATA-4)."""

    def call(self, call: Call, data: dict[str, Any]) -> None:
        """Launch a service call, not awaited (ARCH-4). Errors come back as SE=>S_call_failed."""


class TemperatureSensorPort(Protocol):
    """The temperature sensor."""

    def temperature(self) -> float | None:
        """temperature@T: in the unit of Home Assistant, None when not valid (CFG-SENS-6)."""


@dataclass(frozen=True)
class ExternalSensorAttributes:
    """attributes@XS (spec §1.1.2)."""

    unit: str | None
    step: float | None
    minimum: float | None
    maximum: float | None


class ExternalSensorPort(Protocol):
    """An external sensor entity."""

    def attributes(self) -> ExternalSensorAttributes | None:
        """attributes@XS; None when not usable."""

    def set_value(self, value: float) -> None:
        """AC=>XS_set_value(v), not awaited. Errors come back as XS=>AC_call_failed."""


class TimerPort(Protocol):
    """Timers: decided in the core, waited by Home Assistant (ARCH-7)."""

    def start(self, owner: str, name: str, number: int, seconds: float) -> None:
        """Start (or restart) the timer `name` of the actor `owner`."""

    def cancel(self, owner: str, name: str) -> None:
        """Cancel the timer `name` of the actor `owner`."""


class StorePort(Protocol):
    """Stored data of the entry, one part per actor (ARCHITECTURE §7)."""

    def load(self, part: str) -> Any:
        """The stored part at start, None when missing."""

    def save(self, part: str, data: Any) -> None:
        """Mark the part changed; written after the stimulus (ARCH-9)."""


class RepairsPort(Protocol):
    """Repairs issues of Home Assistant."""

    def raise_issue(self, issue_id: str, key: str, placeholders: dict[str, str]) -> None:
        """Raise (or update) an issue."""

    def clear_issue(self, issue_id: str) -> None:
        """Remove an issue."""


class NotifyPort(Protocol):
    """Logs and the event adaptative_climate_problem."""

    def log(self, level: str, message: str) -> str:
        """Log at a level (debug, info, warning, error); returns the text logged."""

    def fire_problem(self, data: dict[str, Any]) -> None:
        """Fire the event adaptative_climate_problem."""


class ClockPort(Protocol):
    """Time of Home Assistant."""

    def now(self) -> str:
        """Now, ISO format."""
