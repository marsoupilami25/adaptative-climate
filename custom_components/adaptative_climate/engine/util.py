"""Value helpers: pure functions, no Home Assistant state.

- is_number: a number, not a boolean.
- same_temperature / changed: compare temperatures, ignoring float noise.
- same_value / match_option: compare setting values ignoring case, and
  find an option spelled as the source spells it.
"""

from __future__ import annotations

import math
from typing import Any


def is_number(value: Any) -> bool:
    """Return True for a number (not a boolean)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def same_temperature(a: Any, b: Any) -> bool:
    """Return True when two temperatures are equal, ignoring float noise."""
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return False
    return math.isclose(a, b, abs_tol=1e-6)


def changed(a: Any, b: Any) -> bool:
    """Return True when a target reading changed."""
    return a != b and not same_temperature(a, b)


def same_value(a: Any, b: Any) -> bool:
    """Return True when two setting values are equal, ignoring case."""
    if isinstance(a, str) and isinstance(b, str):
        return a.lower() == b.lower()
    return a == b


def match_option(options: list[Any], value: str) -> str | None:
    """Return the option equal to value, ignoring case, as the source spells it."""
    wanted = value.lower()
    return next(
        (option for option in options if isinstance(option, str) and option.lower() == wanted),
        None,
    )
