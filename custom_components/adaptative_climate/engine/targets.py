"""Targets kept by the entity.

TargetStore holds the targets wanted by the user: single, low (heating
setpoint) and high (cooling setpoint). The sources get them rounded and
in their range, but the stored values stay as they are.

- Item access: store[target].
- apply_gap: keeps the low target a gap below the high one. The target
  just set stays and the other one moves; if it cannot follow (keep
  holds it in a range), the target just set moves back, unless give_way
  is False (a change made on a source is kept). keep is given by the
  caller, so this works without Home Assistant.
- restore / as_dict: saved across restarts, bad values dropped.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.climate import ATTR_TARGET_TEMP_HIGH, ATTR_TARGET_TEMP_LOW

from .model import SAVED_TARGETS, TARGETS
from .util import is_number, same_temperature

# Returns the value kept for a target set to a value (see TargetSync.keep).
type KeepFunc = Callable[[str, float], float]


class TargetStore:
    """Targets wanted by the user, kept across restarts.

    The sources receive them rounded and in their range, but they stay as
    they are. The low target (heating setpoint) stays a gap below the high
    one (cooling setpoint).
    """

    def __init__(self) -> None:
        """Initialize without targets."""
        self._values: dict[str, float | None] = dict.fromkeys(TARGETS)

    def __getitem__(self, target: str) -> float | None:
        """Return a target."""
        return self._values[target]

    def __setitem__(self, target: str, value: float | None) -> None:
        """Set a target."""
        self._values[target] = value

    def has_range(self) -> bool:
        """Return True when both the low and high targets are set."""
        return (
            self._values[ATTR_TARGET_TEMP_LOW] is not None
            and self._values[ATTR_TARGET_TEMP_HIGH] is not None
        )

    def restore(self, data: dict[str, Any]) -> None:
        """Read the targets saved before a restart, dropping bad values."""
        for target, name in SAVED_TARGETS.items():
            value = data.get(name)
            self._values[target] = float(value) if is_number(value) else None

    def as_dict(self) -> dict[str, Any]:
        """Return the data saved across restarts."""
        return {name: self._values[target] for target, name in SAVED_TARGETS.items()}

    def gap_respected(self, gap: float) -> bool:
        """Return True when the low target is at least gap below the high one."""
        low = self._values[ATTR_TARGET_TEMP_LOW]
        high = self._values[ATTR_TARGET_TEMP_HIGH]
        return (
            low is None
            or high is None
            or low <= high - gap
            or same_temperature(low, high - gap)
        )

    def apply_gap(
        self, changed: list[str], gap: float, keep: KeepFunc, *, give_way: bool = True
    ) -> None:
        """Keep the low target gap below the high one.

        The target just set stays; the other one moves, as keep returns it.
        If it cannot follow (keep holds it in a range), the target just set
        moves back as far as needed, unless give_way is False (a change made
        on a source is kept). When both were set, the high target moves.
        """
        low_high = {ATTR_TARGET_TEMP_LOW, ATTR_TARGET_TEMP_HIGH}
        if not low_high & set(changed) or self.gap_respected(gap):
            return
        pivot = (
            ATTR_TARGET_TEMP_LOW if ATTR_TARGET_TEMP_LOW in changed else ATTR_TARGET_TEMP_HIGH
        )
        other = ATTR_TARGET_TEMP_HIGH if pivot == ATTR_TARGET_TEMP_LOW else ATTR_TARGET_TEMP_LOW
        moves = ((other, pivot), (pivot, other)) if give_way else ((other, pivot),)
        for moved, fixed in moves:
            sign = 1 if moved == ATTR_TARGET_TEMP_HIGH else -1
            fixed_value = self._values[fixed]
            assert fixed_value is not None
            self._values[moved] = keep(moved, fixed_value + sign * gap)
            if self.gap_respected(gap):
                return
