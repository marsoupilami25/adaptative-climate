"""Sdsm: data storage management of a source (spec §1.2.2).

Stored data, restore at HA=>S_start, update on each change of the source
entity, removal confirmation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..model.events import (
    HA_START,
    S_CAPABILITIES,
    SDSM_DISCOVERED,
    SDSM_RESTORED,
    SDSM_SERVED_MODE_LOST,
    SDSM_SERVED_MODES_BACK,
    SE_CHANGES,
    SE_NOT_USABLE,
    TIMEOUT,
    Event,
)
from ..model.values import (
    CAP_LISTS,
    CAP_NUMBERS,
    MODES,
    OFF,
    SETTINGS,
    TARGET_TEMP_HIGH,
    TARGET_TEMP_LOW,
    ModeCaps,
    Snapshot,
    as_number,
    as_text_list,
    is_usable,
)

if TYPE_CHECKING:
    from .source import Source

REMOVAL = "removal:"
HVAC_MODES = "hvac_modes"
FEATURES = "supported_features"


@dataclass
class SourceData:
    """Stored data of a source (spec §1.2.2.1)."""

    #: OFF or ON(m): "off" or the mode. Never UNDISCOVERED / UNUSABLE.
    state: str = OFF
    #: None while the source is not discovered (SRC-DATA-3).
    hvac_modes: list[str] | None = None
    #: Capabilities per discovered mode (SRC-DATA-1).
    modes: dict[str, ModeCaps] = field(default_factory=dict)
    #: Kept settings of the setting request management (SRC-SET-1).
    kept: dict[str, Any] = field(default_factory=dict)

    @property
    def discovered(self) -> bool:
        """The source is discovered once its hvac_modes is known."""
        return self.hvac_modes is not None

    def caps(self, mode: str) -> ModeCaps | None:
        """Capabilities of a discovered mode; None when the mode is not discovered."""
        return self.modes.get(mode)

    def to_dict(self) -> dict[str, Any]:
        """Stored form."""
        return {
            "state": self.state,
            "hvac_modes": None if self.hvac_modes is None else list(self.hvac_modes),
            "modes": {mode: caps.to_dict() for mode, caps in self.modes.items()},
            "kept": dict(self.kept),
        }


def restore_data(stored: Any) -> tuple[SourceData, bool]:
    """Restore each value alone (SRC-DATA-4, SRC-DATA-5). Second: a state was stored."""
    data = SourceData()
    if not isinstance(stored, Mapping):
        return data, False
    has_state = False
    state = stored.get("state")
    if isinstance(state, str) and (state == OFF or state in MODES):
        data.state = state
        has_state = True
    modes = as_text_list(stored.get("hvac_modes"))
    if modes is not None and all(isinstance(m, str) for m in stored["hvac_modes"]):
        data.hvac_modes = modes
    caps = stored.get("modes")
    if isinstance(caps, Mapping):
        for mode, value in caps.items():
            if isinstance(mode, str) and mode in MODES:
                restored = ModeCaps.from_dict(value)
                if restored is not None:
                    data.modes[mode] = restored
    kept = stored.get("kept")
    if isinstance(kept, Mapping):
        for name, value in kept.items():
            if name in SETTINGS and (as_number(value) is not None or isinstance(value, str)):
                data.kept[name] = value
    return data, has_state


@dataclass(frozen=True)
class Pending:
    """A value, or an item, going through the removal confirmation."""

    scope: str  # "hvac_modes", or a mode for a mode capability
    name: str  # the attribute
    item: Any = None  # the item of a value made of items; None for a number

    @property
    def key(self) -> str:
        """Name of its timer."""
        return f"{REMOVAL}{self.scope}|{self.name}|{self.item}"


class StorageManagement:
    """Sdsm: permanent, it does not depend on the state of the source."""

    def __init__(self, source: Source) -> None:
        self._source = source
        self._pending: dict[str, Pending] = {}

    @property
    def data(self) -> SourceData:
        """The stored data."""
        return self._source.data

    def handle(self, event: Event) -> None:
        """Events of the data storage management."""
        kind = event.kind
        if kind == HA_START:
            self._restore()
        elif kind in SE_CHANGES:
            if is_usable(self._source.snapshot):
                self._update(self._source.snapshot, at_start=False)
        elif kind in SE_NOT_USABLE:
            self._cancel_all()  # SRC-DATA-11
        elif kind == TIMEOUT and event.value[0].startswith(REMOVAL):
            self._confirm_removal(event.value[0])

    # --- Restore (§1.2.2.2) ----------------------------------------------------

    def _restore(self) -> None:
        source = self._source
        if not source.has_stored_state:
            source.save()  # state := OFF, save
        snapshot = source.port.snapshot()
        source.prev_snapshot = None
        source.snapshot = snapshot
        if self.data.discovered:
            if is_usable(snapshot):
                self._update(snapshot, at_start=True)
        elif is_usable(snapshot):
            self._discover(snapshot, at_start=True)
        source.post(Event(SDSM_RESTORED))

    # --- Update (§1.2.2.3) -----------------------------------------------------

    def _discover(self, snapshot: Snapshot, at_start: bool) -> None:
        """First read of the source entity: the source is discovered (SRC-DATA-6)."""
        self.data.hvac_modes = as_text_list(snapshot.get(HVAC_MODES)) or []
        running = snapshot.state if snapshot.state != OFF else None
        if running is not None:
            self.data.modes[running] = self._read_caps(snapshot)
        self._source.save()
        if not at_start:
            self._source.post(Event(SDSM_DISCOVERED))
            self._source.send_ac(S_CAPABILITIES)  # SRC-DATA-12

    def _update(self, snapshot: Snapshot, at_start: bool) -> None:
        if not self.data.discovered:
            self._discover(snapshot, at_start)
            return
        source = self._source
        changed = False
        removals: list[Pending] = []
        served_missing = not source.served_offered()

        # hvac_modes, item by item
        shown = as_text_list(snapshot.get(HVAC_MODES)) or []
        stored = self.data.hvac_modes or []
        for item in shown:
            pending = Pending(HVAC_MODES, HVAC_MODES, item)
            self._cancel(pending)
            if item not in stored:
                stored.append(item)
                changed = True
        for item in stored:
            if item not in shown:
                removals.append(Pending(HVAC_MODES, HVAC_MODES, item))
        self.data.hvac_modes = stored

        # capabilities of the mode it runs in
        running = snapshot.state if snapshot.state != OFF else None
        for pending in list(self._pending.values()):
            if pending.scope != HVAC_MODES and pending.scope != running:
                self._cancel(pending)  # SRC-DATA-11: the source entity left its mode
        if running is not None:
            caps = self.data.modes.get(running)
            if caps is None:
                self.data.modes[running] = self._read_caps(snapshot)
                changed = True
            else:
                changed |= self._compare_caps(running, caps, snapshot, removals)

        for pending in removals:
            if pending.key not in self._pending:
                self._pending[pending.key] = pending
                if source.entry.removal_confirmation_timer > 0:
                    source.timers.start(pending.key, source.entry.removal_confirmation_timer)

        if changed:
            source.save()
        lost = self._remove_now()  # removal_confirmation_timer 0: removed at once
        if changed or lost is not None:
            source.send_ac(S_CAPABILITIES)
        if served_missing and source.served_offered() and not at_start:
            source.post(Event(SDSM_SERVED_MODES_BACK))
        if lost:
            source.post(Event(SDSM_SERVED_MODE_LOST))

    def _read_caps(self, snapshot: Snapshot) -> ModeCaps:
        caps = ModeCaps()
        features = snapshot.get(FEATURES)
        if isinstance(features, int) and not isinstance(features, bool):
            caps.supported_features = max(features, 0)
        for name in CAP_NUMBERS:
            setattr(caps, name, as_number(snapshot.get(name)))
        for name in CAP_LISTS:
            setattr(caps, name, as_text_list(snapshot.get(name)) or [])
        caps.low_high_seen = _low_high_shown(snapshot)
        return caps

    def _compare_caps(
        self, mode: str, caps: ModeCaps, snapshot: Snapshot, removals: list[Pending]
    ) -> bool:
        changed = False
        # supported_features: a set of features, compared feature by feature
        features = snapshot.get(FEATURES)
        shown_bits = features if isinstance(features, int) and not isinstance(features, bool) else 0
        for bit in _bits(shown_bits):
            self._cancel(Pending(mode, FEATURES, bit))
            if not caps.supported_features & bit:
                caps.supported_features |= bit
                changed = True
        for bit in _bits(caps.supported_features):
            if not shown_bits & bit:
                removals.append(Pending(mode, FEATURES, bit))
        # numbers
        for name in CAP_NUMBERS:
            value = as_number(snapshot.get(name))
            pending = Pending(mode, name)
            if value is None:
                if getattr(caps, name) is not None:
                    removals.append(pending)
                continue
            self._cancel(pending)
            if getattr(caps, name) != value:
                setattr(caps, name, value)
                changed = True
        # lists, item by item
        for name in CAP_LISTS:
            shown = as_text_list(snapshot.get(name)) or []
            stored: list[str] = getattr(caps, name)
            for item in shown:
                self._cancel(Pending(mode, name, item))
                if item not in stored:
                    stored.append(item)
                    changed = True
            for item in stored:
                if item not in shown:
                    removals.append(Pending(mode, name, item))
        # low_high_seen (SRC-DATA-8), never removed
        if not caps.low_high_seen and _low_high_shown(snapshot):
            caps.low_high_seen = True
            changed = True
        return changed

    # --- Removal confirmation ----------------------------------------------------

    def _cancel(self, pending: Pending) -> None:
        if self._pending.pop(pending.key, None) is not None:
            self._source.timers.cancel(pending.key)

    def _cancel_all(self) -> None:
        for pending in list(self._pending.values()):
            self._cancel(pending)

    def _remove_now(self) -> bool | None:
        """Removal confirmation of 0 s: removed at once. None when nothing removed."""
        if self._source.entry.removal_confirmation_timer > 0 or not self._pending:
            return None
        lost = False
        for pending in list(self._pending.values()):
            del self._pending[pending.key]
            lost |= self._remove(pending)
        self._source.save()
        return lost

    def _confirm_removal(self, key: str) -> None:
        pending = self._pending.pop(key, None)
        if pending is None:
            return
        lost = self._remove(pending)
        self._source.save()
        self._source.send_ac(S_CAPABILITIES)
        if lost:
            self._source.post(Event(SDSM_SERVED_MODE_LOST))

    def _remove(self, pending: Pending) -> bool:
        """Remove a value; True when a served source mode was removed."""
        if pending.scope == HVAC_MODES:
            if self.data.hvac_modes and pending.item in self.data.hvac_modes:
                self.data.hvac_modes.remove(pending.item)
            return pending.item in self._source.cfg.served_source_modes
        caps = self.data.modes.get(pending.scope)
        if caps is None:
            return False
        if pending.name == FEATURES:
            caps.supported_features &= ~pending.item
        elif pending.name in CAP_NUMBERS:
            setattr(caps, pending.name, None)
        else:
            items: list[str] = getattr(caps, pending.name)
            if pending.item in items:
                items.remove(pending.item)
        return False


def _bits(value: int) -> list[int]:
    return [1 << i for i in range(value.bit_length()) if value & (1 << i)]


def _low_high_shown(snapshot: Snapshot) -> bool:
    return (
        as_number(snapshot.get(TARGET_TEMP_LOW)) is not None
        and as_number(snapshot.get(TARGET_TEMP_HIGH)) is not None
    )
