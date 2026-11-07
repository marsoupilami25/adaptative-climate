"""Constants for Adaptative Climate."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from homeassistant.components.climate import HVACMode

DOMAIN: Final = "adaptative_climate"

DEFAULT_NAME: Final = "Adaptative Climate"

# Optional limits that narrow the temperature range of the sources.
CONF_MIN_TEMP: Final = "min_temp"
CONF_MAX_TEMP: Final = "max_temp"

CONF_HEAT_ENTITY: Final = "heat_entity"
CONF_COOL_ENTITY: Final = "cool_entity"
CONF_AUTO_ENTITY: Final = "auto_entity"
CONF_DRY_ENTITY: Final = "dry_entity"
CONF_FAN_ONLY_ENTITY: Final = "fan_only_entity"

# Modes whose fan and swing settings are kept in sync.
CONF_SYNC_MODES: Final = "sync_modes"

# Source climate entity option for each Adaptative Climate mode. Each mode is
# sent to its source as the HVAC mode of the same name. HEAT_COOL comes later.
MODE_SOURCE_KEYS: Final[dict[HVACMode, str]] = {
    HVACMode.HEAT: CONF_HEAT_ENTITY,
    HVACMode.COOL: CONF_COOL_ENTITY,
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


def sync_modes(settings: Mapping[str, Any]) -> set[HVACMode]:
    """Return the synchronized modes that have a source."""
    sources = mode_sources(settings)
    return {
        HVACMode(mode)
        for mode in settings.get(CONF_SYNC_MODES) or []
        if mode in sources
    }
