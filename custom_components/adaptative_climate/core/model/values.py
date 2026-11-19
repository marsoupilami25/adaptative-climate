"""Values of the core: modes and their order, settings, capabilities, comparison.

Pure Python (ARCHITECTURE ARCH-1). Spec §0, §1.1.2, §1.2.2.1, SRC-SET-4.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
import math
from typing import Any

# --- Modes (spec §0: mode order) -------------------------------------------

OFF = "off"
HEAT = "heat"
COOL = "cool"
HEAT_COOL = "heat_cool"
AUTO = "auto"
DRY = "dry"
FAN_ONLY = "fan_only"

MODE_ORDER: tuple[str, ...] = (OFF, HEAT, COOL, HEAT_COOL, AUTO, DRY, FAN_ONLY)
MODES: tuple[str, ...] = MODE_ORDER[1:]
PHASES: tuple[str, ...] = (HEAT, COOL)

UNAVAILABLE = "unavailable"
UNKNOWN = "unknown"


def mode_index(mode: str) -> int:
    """Position of a mode in the mode order (unknown modes last)."""
    try:
        return MODE_ORDER.index(mode)
    except ValueError:
        return len(MODE_ORDER)


def other_phase(phase: str) -> str:
    """The other phase of a bi-source heat_cool."""
    return COOL if phase == HEAT else HEAT


# --- Features of a climate entity (Home Assistant ClimateEntityFeature) -----

FEATURE_TARGET_TEMPERATURE = 1
FEATURE_TARGET_TEMPERATURE_RANGE = 2
FEATURE_FAN_MODE = 8
FEATURE_SWING_MODE = 32
FEATURE_TURN_OFF = 128
FEATURE_TURN_ON = 256
FEATURE_SWING_HORIZONTAL_MODE = 512

# --- Settings (spec §0, §1.2.5) ---------------------------------------------

TEMPERATURE = "temperature"
TARGET_TEMP_LOW = "target_temp_low"
TARGET_TEMP_HIGH = "target_temp_high"
FAN_MODE = "fan_mode"
SWING_MODE = "swing_mode"
SWING_HORIZONTAL_MODE = "swing_horizontal_mode"

TEMPERATURE_SETTINGS: tuple[str, ...] = (TEMPERATURE, TARGET_TEMP_LOW, TARGET_TEMP_HIGH)
FAN_SWING_SETTINGS: tuple[str, ...] = (FAN_MODE, SWING_MODE, SWING_HORIZONTAL_MODE)
SETTINGS: tuple[str, ...] = TEMPERATURE_SETTINGS + FAN_SWING_SETTINGS

#: The capability attribute holding the options of each fan/swing setting.
OPTIONS_OF: Mapping[str, str] = {
    FAN_MODE: "fan_modes",
    SWING_MODE: "swing_modes",
    SWING_HORIZONTAL_MODE: "swing_horizontal_modes",
}
#: The feature a source declares for each fan/swing setting.
FEATURE_OF: Mapping[str, int] = {
    FAN_MODE: FEATURE_FAN_MODE,
    SWING_MODE: FEATURE_SWING_MODE,
    SWING_HORIZONTAL_MODE: FEATURE_SWING_HORIZONTAL_MODE,
}

# --- Temperature targets of the entity (spec §1.3.4.3) ----------------------

LOW = "low"
HIGH = "high"
SINGLE = "T"
TARGETS: tuple[str, ...] = (LOW, HIGH, SINGLE)

# Case of a source in a mode (ENT-FEAT-1).
CASE_LOW_HIGH = "low_high"
CASE_SINGLE = "single"
CASE_NONE = "none"

# --- Capabilities (spec §1.2.2.1) -------------------------------------------

CAP_NUMBERS: tuple[str, ...] = ("min_temp", "max_temp", "target_temp_step")
CAP_LISTS: tuple[str, ...] = ("fan_modes", "swing_modes", "swing_horizontal_modes")


@dataclass
class ModeCaps:
    """Capabilities of a source in one mode, as last read in that mode."""

    supported_features: int = 0
    min_temp: float | None = None
    max_temp: float | None = None
    target_temp_step: float | None = None
    fan_modes: list[str] = field(default_factory=list)
    swing_modes: list[str] = field(default_factory=list)
    swing_horizontal_modes: list[str] = field(default_factory=list)
    low_high_seen: bool = False

    def has(self, feature: int) -> bool:
        """Whether the source declares the feature in that mode."""
        return bool(self.supported_features & feature)

    def options(self, setting: str) -> list[str] | None:
        """Options of a fan/swing setting; None when the capability is missing."""
        if not self.has(FEATURE_OF[setting]):
            return None
        return list(getattr(self, OPTIONS_OF[setting]))

    def case(self) -> str:
        """The case of the source in that mode (ENT-FEAT-1, ENT-FEAT-2)."""
        rng = self.has(FEATURE_TARGET_TEMPERATURE_RANGE)
        single = self.has(FEATURE_TARGET_TEMPERATURE)
        if rng and (not single or self.low_high_seen):
            return CASE_LOW_HIGH
        if single:
            return CASE_SINGLE
        return CASE_NONE

    def to_dict(self) -> dict[str, Any]:
        """Stored form."""
        return {
            "supported_features": self.supported_features,
            "min_temp": self.min_temp,
            "max_temp": self.max_temp,
            "target_temp_step": self.target_temp_step,
            "fan_modes": list(self.fan_modes),
            "swing_modes": list(self.swing_modes),
            "swing_horizontal_modes": list(self.swing_horizontal_modes),
            "low_high_seen": self.low_high_seen,
        }

    @classmethod
    def from_dict(cls, data: Any) -> ModeCaps | None:
        """Restore; each invalid value is dropped (SRC-DATA-5)."""
        if not isinstance(data, Mapping):
            return None
        caps = cls()
        features = data.get("supported_features")
        if isinstance(features, int) and not isinstance(features, bool) and features >= 0:
            caps.supported_features = features
        for name in CAP_NUMBERS:
            setattr(caps, name, as_number(data.get(name)))
        for name in CAP_LISTS:
            value = data.get(name)
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                setattr(caps, name, list(value))
        caps.low_high_seen = data.get("low_high_seen") is True
        return caps


@dataclass(frozen=True)
class Snapshot:
    """State and attributes of an entity of Home Assistant, as last seen."""

    state: str
    attributes: Mapping[str, Any] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        """Exists, and its state is not unavailable / unknown (spec §0)."""
        return self.state not in (UNAVAILABLE, UNKNOWN)

    def get(self, name: str) -> Any:
        """An attribute, None when missing."""
        return self.attributes.get(name)


def is_usable(snapshot: Snapshot | None) -> bool:
    """Usable: the entity exists and is not unavailable / unknown."""
    return snapshot is not None and snapshot.usable


# --- Numbers ----------------------------------------------------------------


def as_number(value: Any) -> float | None:
    """A finite number, or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def as_text_list(value: Any) -> list[str] | None:
    """A list of strings, or None when missing / invalid."""
    if not isinstance(value, (list, tuple)):
        return None
    return [str(v) for v in value if v is not None]


def clean(value: float) -> float:
    """Remove the floating point noise."""
    return round(value, 6) + 0.0


def round_to_step(value: float, step: float, direction: int = 0) -> float:
    """Round on a step: nearest (0), up (1) or down (-1)."""
    ratio = value / step
    if direction > 0:
        count = math.ceil(ratio - 1e-9)
    elif direction < 0:
        count = math.floor(ratio + 1e-9)
    else:
        count = math.floor(ratio + 0.5 + 1e-9)
    return clean(count * step)


def clamp(value: float, low: float, high: float) -> float:
    """Bring a value into a range."""
    return min(max(value, low), high)


def steps_gcd(steps: Iterable[float]) -> float | None:
    """The largest value that divides every step exactly (ENT-STEP-1)."""
    scale = 10000
    result = 0
    for step in steps:
        units = round(step * scale)
        if units > 0:
            result = math.gcd(result, units)
    return result / scale if result else None


# --- Comparison of values (SRC-SET-4, ENT-FAN-5) -----------------------------


def same_option(a: Any, b: Any) -> bool:
    """Fan/swing values: the same ignoring case."""
    if a is None or b is None:
        return a is b
    return str(a).casefold() == str(b).casefold()


def match_option(value: Any, options: Iterable[str] | None) -> str | None:
    """The option matching a value ignoring case, as the options spell it."""
    if value is None or options is None:
        return None
    for option in options:
        if same_option(option, value):
            return option
    return None


def same_temperature(a: Any, b: Any, step: float) -> bool:
    """Temperatures: the same when their gap is strictly less than one step."""
    na, nb = as_number(a), as_number(b)
    if na is None or nb is None:
        return na is None and nb is None
    return abs(na - nb) < step - 1e-9


def same_setting(name: str, a: Any, b: Any, step: float) -> bool:
    """Compare a setting shown with the value sent (SRC-SET-4)."""
    if name in TEMPERATURE_SETTINGS:
        return same_temperature(a, b, step)
    return same_option(a, b)


# --- Units ------------------------------------------------------------------

CELSIUS = "°C"
FAHRENHEIT = "°F"
KELVIN = "K"
TEMPERATURE_UNITS = (CELSIUS, FAHRENHEIT, KELVIN)


def convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
    """Convert a temperature between °C, °F and K."""
    if from_unit == to_unit:
        return value
    if from_unit == FAHRENHEIT:
        celsius = (value - 32) / 1.8
    elif from_unit == KELVIN:
        celsius = value - 273.15
    else:
        celsius = value
    if to_unit == FAHRENHEIT:
        return celsius * 1.8 + 32
    if to_unit == KELVIN:
        return celsius + 273.15
    return celsius
