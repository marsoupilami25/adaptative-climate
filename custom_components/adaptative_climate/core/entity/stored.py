"""Stored data of the AC entity (spec §1.3.6), fingerprint check at start (ARCHITECTURE §8)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..model.entry_config import EntryConfig
from ..model.values import FAN_SWING_SETTINGS, OFF, PHASES, TARGETS, as_number

PART = "entity"


@dataclass
class EntityStored:
    """Mode, last used mode, phase, temperature targets, fan/swing memory."""

    mode: str = OFF
    last_used: str | None = None
    phase: str | None = None
    targets: dict[str, float | None] = field(default_factory=lambda: dict.fromkeys(TARGETS))
    memory: dict[str, dict[str, str]] = field(default_factory=dict)
    fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Stored form."""
        return {
            "mode": self.mode,
            "last_used": self.last_used,
            "phase": self.phase,
            "targets": dict(self.targets),
            "memory": {key: dict(values) for key, values in self.memory.items()},
            "fingerprint": self.fingerprint,
        }


def restore(data: Any, entry: EntryConfig, memory_keys: set[str]) -> tuple[EntityStored, bool]:
    """Restore each value alone (ENT-DATA-1, ENT-DATA-2); second: configuration changed."""
    stored = EntityStored(fingerprint=entry.fingerprint)
    if not isinstance(data, Mapping):
        return stored, False
    mode = data.get("mode")
    if isinstance(mode, str) and mode in entry.modes:
        stored.mode = mode
    last_used = data.get("last_used")
    if isinstance(last_used, str) and last_used in entry.modes:
        stored.last_used = last_used
    phase = data.get("phase")
    if phase in PHASES and stored.mode == "heat_cool" and entry.bi_source:
        stored.phase = phase
    targets = data.get("targets")
    if isinstance(targets, Mapping):
        for name in TARGETS:
            stored.targets[name] = as_number(targets.get(name))
    memory = data.get("memory")
    if isinstance(memory, Mapping):
        for key, values in memory.items():
            if key not in memory_keys or not isinstance(values, Mapping):
                continue  # memory of a mode no longer configured: dropped
            kept = {
                name: value
                for name, value in values.items()
                if name in FAN_SWING_SETTINGS and isinstance(value, str)
            }
            if kept:
                stored.memory[key] = kept
    # Configuration changed (ENT-INIT-4): stored mode off, phase forgotten.
    previous = data.get("fingerprint")
    changed = isinstance(previous, str) and bool(previous) and previous != entry.fingerprint
    if changed:
        stored.mode = OFF
        stored.phase = None
    return stored, changed
