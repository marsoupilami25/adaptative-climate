"""Store port (ARCHITECTURE §7): one Store per entry, one part per actor."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from ...const import DOMAIN

STORE_VERSION = 1
SAVE_DELAY = 1


def entry_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    """The Store of an entry, kept across reloads so that a pending write is not lost."""
    stores: dict[str, Store[dict[str, Any]]] = hass.data.setdefault(DOMAIN, {}).setdefault(
        "stores", {}
    )
    if entry_id not in stores:
        stores[entry_id] = Store(hass, STORE_VERSION, f"{DOMAIN}.{entry_id}")
    return stores[entry_id]


def forget_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    """The Store of a deleted entry, no longer kept."""
    store = entry_store(hass, entry_id)
    hass.data[DOMAIN]["stores"].pop(entry_id, None)
    return store


class StoreAdapter:
    """The parts of an entry: restored at start, saved after each stimulus (ARCH-9)."""

    def __init__(self, store: Store[dict[str, Any]], data: Any, parts: set[str]) -> None:
        self._store = store
        stored = data.get("parts") if isinstance(data, dict) else None
        stored = stored if isinstance(stored, dict) else {}
        # A part no longer configured is dropped (SRC-DATA-9)
        self._data: dict[str, Any] = {"parts": {k: v for k, v in stored.items() if k in parts}}
        self._dirty = len(self._data["parts"]) != len(stored)

    def load(self, part: str) -> Any:
        """The stored part at start."""
        return self._data["parts"].get(part)

    def save(self, part: str, data: Any) -> None:
        """Mark the part changed."""
        self._data["parts"][part] = data
        self._dirty = True

    def flush(self) -> None:
        """After the stimulus: write what changed."""
        if self._dirty:
            self._dirty = False
            self._store.async_delay_save(lambda: self._data, SAVE_DELAY)
