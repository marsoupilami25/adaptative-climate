"""Constants for Adaptative Climate."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any, Final

from homeassistant.components.climate import HVACMode

DOMAIN: Final = "adaptative_climate"

DEFAULT_NAME: Final = "Adaptative Climate"

# Optional limits that narrow the temperature range of the sources.
CONF_MIN_TEMP: Final = "min_temp"
CONF_MAX_TEMP: Final = "max_temp"

# Optional minimum gap between the low (heating) and high (cooling) targets.
CONF_MIN_GAP: Final = "min_gap"
# Smallest gap, also the default: the combined HEAT_COOL keeps its phase
# between the two targets, so they must not meet.
MIN_GAP: Final = 1.0

# Optional minimum time, in minutes, the combined HEAT_COOL stays in a phase
# before switching to the other one by itself (0: no minimum). It keeps
# compressors from short cycles when the targets are close.
CONF_MIN_PHASE_DURATION: Final = "min_phase_duration"
DEFAULT_MIN_PHASE_DURATION: Final = 10

CONF_HEAT_ENTITY: Final = "heat_entity"
CONF_COOL_ENTITY: Final = "cool_entity"
CONF_HEAT_COOL_ENTITY: Final = "heat_cool_entity"
CONF_AUTO_ENTITY: Final = "auto_entity"
CONF_DRY_ENTITY: Final = "dry_entity"
CONF_FAN_ONLY_ENTITY: Final = "fan_only_entity"

# Optional sensor giving the room temperature.
CONF_TEMPERATURE_SENSOR: Final = "temperature_sensor"

# Modes whose fan and swing settings are kept in sync.
CONF_SYNC_MODES: Final = "sync_modes"

# Source climate entity option for each Adaptative Climate mode. Each mode is
# sent to its source as the HVAC mode of the same name. Without a heat_cool
# source, HEAT_COOL uses the heat and cool sources (see combined_heat_cool).
MODE_SOURCE_KEYS: Final[dict[HVACMode, str]] = {
    HVACMode.HEAT: CONF_HEAT_ENTITY,
    HVACMode.COOL: CONF_COOL_ENTITY,
    HVACMode.HEAT_COOL: CONF_HEAT_COOL_ENTITY,
    HVACMode.AUTO: CONF_AUTO_ENTITY,
    HVACMode.DRY: CONF_DRY_ENTITY,
    HVACMode.FAN_ONLY: CONF_FAN_ONLY_ENTITY,
}


def entry_settings(entry: Any) -> Mapping[str, Any]:
    """Return the current settings of a config entry.

    The options flow saves every setting, so options replace the initial
    data as a whole once they exist (this lets the user clear a source).
    """
    return entry.options or entry.data


def mode_sources(settings: Mapping[str, Any]) -> dict[HVACMode, str]:
    """Return the configured source entity for each mode, in display order."""
    return {
        mode: settings[key]
        for mode, key in MODE_SOURCE_KEYS.items()
        if settings.get(key)
    }


def combined_heat_cool(settings: Mapping[str, Any]) -> bool:
    """Return True when HEAT_COOL switches between the heat and cool sources.

    That is when it has no source of its own, but heat and cool have one.
    """
    return (
        not settings.get(CONF_HEAT_COOL_ENTITY)
        and bool(settings.get(CONF_HEAT_ENTITY))
        and bool(settings.get(CONF_COOL_ENTITY))
    )


def min_phase_duration(settings: Mapping[str, Any]) -> timedelta:
    """Return the minimum time the combined HEAT_COOL stays in a phase."""
    minutes = settings.get(CONF_MIN_PHASE_DURATION)
    if minutes is None:
        minutes = DEFAULT_MIN_PHASE_DURATION
    return timedelta(minutes=float(minutes))


def sync_modes(settings: Mapping[str, Any]) -> set[HVACMode]:
    """Return the synchronized modes that have a source."""
    sources = mode_sources(settings)
    return {
        HVACMode(mode)
        for mode in settings.get(CONF_SYNC_MODES) or []
        if mode in sources
    }
