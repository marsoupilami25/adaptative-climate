"""Definitions shared by the engine: constants, a data type, type aliases.

No logic here, and no import from the rest of the engine: every module
can import it.

Targets:
- TARGETS: the targets kept by the entity, named like the source
  attributes (temperature, target_temp_low, target_temp_high).
- SINGLE_TARGETS: the target behind the single target of heat (low, the
  heating setpoint) and cool (high, the cooling setpoint). Other modes
  use the single target itself.
- TARGET_FEATURES: the feature a source needs to get each target.
- SAVED_TARGETS: the name of each target in the saved data.
- TargetGap: a target the entity shows otherwise than it keeps it (out of
  reach of the active source).

Combined HEAT_COOL:
- PHASES: the modes it switches between (heat, cool).

Fan and swing settings:
- Setting: describes one setting (feature, value and options attributes,
  service), so the three of them are handled by one loop.
- SETTINGS: fan, swing and horizontal swing.
- SYNC_KEY: the memory key shared by the synchronized modes.

Timing:
- SETTLE_TIME: how long a source may report its own targets, or the
  previous phase, after entering a mode.
- REQUEST_TIME: how long a source may take to show a mode asked by the
  entity; entering a mode later counts as a change made elsewhere.

Type aliases:
- MemoryData: memory key -> setting attribute -> value.
- TargetKey: (mode, phase of the combined HEAT_COOL or None). When it
  changes, the mode changed and the targets must be sent again.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_SWING_HORIZONTAL_MODE,
    ATTR_SWING_HORIZONTAL_MODES,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_SWING_HORIZONTAL_MODE,
    SERVICE_SET_SWING_MODE,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE

# Targets kept by the entity, named like the source attributes. The low target
# is the heating setpoint and the high target the cooling setpoint: the single
# target of heat is the low one, the one of cool the high one, and HEAT_COOL
# shows both, like auto on a source with low/high. The single target only
# serves dry, and auto on a source without low/high.
TARGETS = (ATTR_TEMPERATURE, ATTR_TARGET_TEMP_LOW, ATTR_TARGET_TEMP_HIGH)

# Target behind the single target, in the modes that have a setpoint.
SINGLE_TARGETS = {
    HVACMode.HEAT: ATTR_TARGET_TEMP_LOW,
    HVACMode.COOL: ATTR_TARGET_TEMP_HIGH,
}

# Feature a source needs to get a target attribute.
TARGET_FEATURES = {
    ATTR_TEMPERATURE: ClimateEntityFeature.TARGET_TEMPERATURE,
    ATTR_TARGET_TEMP_LOW: ClimateEntityFeature.TARGET_TEMPERATURE_RANGE,
    ATTR_TARGET_TEMP_HIGH: ClimateEntityFeature.TARGET_TEMPERATURE_RANGE,
}

# Name of each target in the saved data.
SAVED_TARGETS = {
    ATTR_TEMPERATURE: "target_temperature",
    ATTR_TARGET_TEMP_LOW: "target_temperature_low",
    ATTR_TARGET_TEMP_HIGH: "target_temperature_high",
}

# Modes the combined HEAT_COOL switches between.
PHASES = (HVACMode.HEAT, HVACMode.COOL)


@dataclass(frozen=True)
class TargetGap:
    """A target shown otherwise than kept: the active source cannot reach it.

    The target is kept in the widest range of its sources; the active source
    gets it, and the entity shows it, in the range of that source.
    """

    # Target attribute of the entity (temperature, target_temp_low,
    # target_temp_high). In heat, temperature shows the low target.
    attribute: str
    # The target shown, as kept.
    saved: float
    shown: float

    def as_dict(self) -> dict[str, str | float]:
        """Return the gap as a state attribute."""
        return {"attribute": self.attribute, "saved": self.saved, "shown": self.shown}


@dataclass(frozen=True)
class Setting:
    """A fan or swing setting, taken from the source of the current mode."""

    feature: ClimateEntityFeature
    # Attribute holding the value, also the field of the service call.
    attr: str
    # Attribute listing the options.
    options_attr: str
    service: str


# Settings taken from the source of the current mode only: a heater has no
# fan, an AC has one. Each mode remembers them (see SettingsMemory).
FAN = Setting(
    ClimateEntityFeature.FAN_MODE,
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    SERVICE_SET_FAN_MODE,
)
SWING = Setting(
    ClimateEntityFeature.SWING_MODE,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    SERVICE_SET_SWING_MODE,
)
SWING_HORIZONTAL = Setting(
    ClimateEntityFeature.SWING_HORIZONTAL_MODE,
    ATTR_SWING_HORIZONTAL_MODE,
    ATTR_SWING_HORIZONTAL_MODES,
    SERVICE_SET_SWING_HORIZONTAL_MODE,
)
SETTINGS: tuple[Setting, ...] = (FAN, SWING, SWING_HORIZONTAL)

# Memory key shared by the synchronized modes. Other modes use their own name.
SYNC_KEY = "sync"

# After a source enters a mode, it may report its own target for that mode
# late, in a later update: until the source shows the target sent to it, or
# during this time at most, the targets it shows are ignored. Integrations
# polling the device usually refresh right after a command, then at most
# every 10 s (Home Assistant debounce of refresh requests).
SETTLE_TIME = timedelta(seconds=12)

# A source entering a mode the entity asked for within this time was
# switched by the entity: it gets the targets. Otherwise it was turned on
# elsewhere (remote, app) and its targets are taken. Cloud devices may take
# a while to show the new mode.
REQUEST_TIME = timedelta(seconds=30)

# Remembered settings: memory key -> setting attribute -> value.
type MemoryData = dict[str, dict[str, str]]

# What the targets are sent for: the mode, and the phase of the combined
# HEAT_COOL (None otherwise).
type TargetKey = tuple[HVACMode, HVACMode | None]
