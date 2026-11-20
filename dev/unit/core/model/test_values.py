"""core/model/values.py: modes, numbers, comparisons, conversions."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.adaptative_climate.core.model.values import (
    ModeCaps,
    convert_temperature,
    mode_index,
    same_option,
    steps_gcd,
)


def test_mode_index_unknown_mode_last() -> None:
    assert mode_index("heat") < mode_index("fan_only") < mode_index("boost")


@pytest.mark.parametrize(
    ("value", "from_unit", "to_unit", "expected"),
    [
        (20.0, "°C", "°C", 20.0),
        (68.0, "°F", "°C", 20.0),
        (293.15, "K", "°C", 20.0),
        (20.0, "°C", "°F", 68.0),
        (20.0, "°C", "K", 293.15),
        (68.0, "°F", "K", 293.15),
        (293.15, "K", "°F", 68.0),
    ],
)
def test_convert_temperature(value: float, from_unit: str, to_unit: str, expected: float) -> None:
    assert convert_temperature(value, from_unit, to_unit) == pytest.approx(expected)


@pytest.mark.parametrize(("a", "b", "same"), [
    (None, None, True), ("low", None, False), (None, "low", False),
    ("Low", "LOW", True), ("1", "low", False),
])
def test_same_option(a: Any, b: Any, same: bool) -> None:
    """SRC-SET-4, ENT-FAN-5: ignoring case; no other name matched."""
    assert same_option(a, b) is same


def test_steps_gcd() -> None:
    """ENT-STEP-1."""
    assert steps_gcd([0.5, 1.0]) == pytest.approx(0.5)
    assert steps_gcd([0.5, 0.2]) == pytest.approx(0.1)
    assert steps_gcd([]) is None


@pytest.mark.parametrize("data", [None, "caps", [1, 2], 3])
def test_mode_caps_restore_something_else_than_a_mapping(data: Any) -> None:
    """SRC-DATA-5: a stored part of the wrong type is dropped."""
    assert ModeCaps.from_dict(data) is None


def test_mode_caps_restore_drops_each_invalid_value() -> None:
    caps = ModeCaps.from_dict(
        {
            "supported_features": "many",
            "min_temp": 10,
            "max_temp": "hot",
            "target_temp_step": -1,
            "fan_modes": "low",
            "swing_modes": ["off", 3],
            "low_high_seen": "yes",
        }
    )
    assert caps is not None
    assert caps.min_temp == 10.0
    assert caps.max_temp is None
    assert caps.fan_modes in ([], None)
