"""What each source showed it offers, kept until it shows otherwise.

Once a source has been seen usable, its capabilities are known: range,
step, features, fan and swing options, HVAC modes. They are kept while the
source is unavailable and across restarts, so the entity does not change
when a source goes away. The last values seen win: a usable source showing
other values replaces them. A source never seen is unknown.

A source seen with low/high values once uses them for good: it may hide
them while off.

KnownCapabilities is kept by the coordinator, which records every source
update; Sources records what it reads too.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_FAN_MODES,
    ATTR_HVAC_MODES,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_SWING_HORIZONTAL_MODES,
    ATTR_SWING_MODES,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TARGET_TEMP_STEP,
)
from homeassistant.const import ATTR_SUPPORTED_FEATURES, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import State

from .engine.util import is_number

# Attributes kept while a source is away.
CAPABILITY_ATTRS = (
    ATTR_MIN_TEMP,
    ATTR_MAX_TEMP,
    ATTR_TARGET_TEMP_STEP,
    ATTR_SUPPORTED_FEATURES,
    ATTR_FAN_MODES,
    ATTR_SWING_MODES,
    ATTR_SWING_HORIZONTAL_MODES,
    ATTR_HVAC_MODES,
)

_NUMBERS = {ATTR_MIN_TEMP, ATTR_MAX_TEMP, ATTR_TARGET_TEMP_STEP, ATTR_SUPPORTED_FEATURES}


def _valid(attr: str, value: Any) -> bool:
    """Return True for a value that can be kept for a capability."""
    if value is None:
        return True
    if attr in _NUMBERS:
        return is_number(value)
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


class KnownCapabilities:
    """Capabilities of each configured source, as last seen while usable."""

    def __init__(self, entity_ids: list[str]) -> None:
        """Initialize with nothing known."""
        self._entity_ids = entity_ids
        self._known: dict[str, dict[str, Any]] = {}
        # Sources seen with low/high values.
        self._range_seen: set[str] = set()

    def record(self, entity_id: str, state: State | None) -> None:
        """Keep what a usable source shows. An unusable one changes nothing."""
        if (
            entity_id not in self._entity_ids
            or state is None
            or state.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}
        ):
            return
        attributes = state.attributes
        known = self._known.setdefault(entity_id, {})
        for attr in CAPABILITY_ATTRS:
            value = attributes.get(attr)
            # Kept as plain values: they are saved across restarts.
            if attr == ATTR_SUPPORTED_FEATURES and is_number(value):
                value = int(value)
            elif isinstance(value, (list, tuple)):
                value = [str(item) for item in value]
            known[attr] = value
        if is_number(attributes.get(ATTR_TARGET_TEMP_LOW)) or is_number(
            attributes.get(ATTR_TARGET_TEMP_HIGH)
        ):
            self._range_seen.add(entity_id)

    def seen(self, entity_id: str | None) -> bool:
        """Return True when a source has been seen usable once."""
        return entity_id in self._known

    def get(self, entity_id: str | None, attr: str) -> Any:
        """Return the last value a source showed for a capability (None if unknown)."""
        if entity_id is None:
            return None
        return self._known.get(entity_id, {}).get(attr)

    def range_seen(self, entity_id: str | None) -> bool:
        """Return True when a source has shown low/high values once."""
        return entity_id in self._range_seen

    def as_dict(self) -> dict[str, Any]:
        """Return what is known of the configured sources, saved across restarts."""
        return {
            "known": {
                entity_id: dict(values)
                for entity_id, values in self._known.items()
                if entity_id in self._entity_ids
            },
            "range_seen": [
                entity_id for entity_id in self._entity_ids if entity_id in self._range_seen
            ],
        }

    def restore(self, data: dict[str, Any]) -> None:
        """Read what was known before a restart, for the configured sources.

        A source already seen since the start keeps what it shows now.
        Bad values are dropped.
        """
        raw = data.get("known")
        if isinstance(raw, dict):
            for entity_id, values in raw.items():
                if (
                    entity_id not in self._entity_ids
                    or entity_id in self._known
                    or not isinstance(values, dict)
                ):
                    continue
                self._known[entity_id] = {
                    attr: values.get(attr)
                    for attr in CAPABILITY_ATTRS
                    if _valid(attr, values.get(attr))
                }
        seen = data.get("range_seen")
        if isinstance(seen, list):
            self._range_seen |= {
                entity_id for entity_id in seen if entity_id in self._entity_ids
            }
