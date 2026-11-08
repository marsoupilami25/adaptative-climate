"""Fan and swing settings remembered by each mode.

Each mode remembers the fan and swing settings of its source and sends
them back when the entity switches to it.

- Memory keys: the name of the mode, or SYNC_KEY for the synchronized
  modes, which share one memory. A shared value must be accepted by all
  the synchronized sources (common_options, can_remember); a source that
  does not offer the setting at all does not count.
- observe: on each update of the active source. Entering a mode only
  fills settings still unknown (the source may still show its own).
  Within a mode, every change is remembered, wherever it comes from.
- async_send: after a mode switch (ModeTracker.async_activate). Each
  value is matched to the options of the source ignoring case, and sent
  as the source spells it, unless it already has it. A shared value no
  longer common is replaced by the current value of the source. Errors
  are logged, the mode switch goes on.
- restore / as_dict: saved across restarts, for the configured modes only.
- options: what a source offers for a setting, also used by the entity
  for its supported features.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import HVACMode
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from ..coordinator import AdaptativeClimateCoordinator
from .model import SETTINGS, SYNC_KEY, MemoryData, Setting
from .sources import Sources
from .util import match_option, same_value

_LOGGER = logging.getLogger(__name__)


class SettingsMemory:
    """Fan and swing settings of each mode, sent back when the mode is entered.

    The synchronized modes share one memory, which only keeps values that
    all their sources accept.
    """

    def __init__(self, coordinator: AdaptativeClimateCoordinator, sources: Sources) -> None:
        """Initialize an empty memory."""
        self._coordinator = coordinator
        self._sources = sources
        self._data: MemoryData = {}

    def restore(self, data: dict[str, Any]) -> None:
        """Read the settings saved before a restart, dropping bad values."""
        raw = data.get("memory")
        if not isinstance(raw, dict):
            self._data = {}
            return
        attrs = {setting.attr for setting in SETTINGS}
        self._data = {
            key: {
                attr: value
                for attr, value in values.items()
                if attr in attrs and isinstance(value, str)
            }
            for key, values in raw.items()
            if isinstance(values, dict)
        }

    def as_dict(self) -> dict[str, Any]:
        """Return the data saved across restarts: the configured modes only."""
        sync = self._coordinator.sync_modes
        keys = {str(mode) for mode in self._sources.mode_sources if mode not in sync}
        if sync:
            keys.add(SYNC_KEY)
        return {
            "memory": {
                key: values for key, values in self._data.items() if key in keys and values
            }
        }

    def key(self, mode: HVACMode) -> str:
        """Return the memory key of a mode: shared by the synchronized modes."""
        return SYNC_KEY if mode in self._coordinator.sync_modes else str(mode)

    def options(self, entity_id: str | None, setting: Setting) -> list[Any]:
        """Return the options a source offers for a setting (empty when none)."""
        if setting.feature not in self._sources.features(entity_id):
            return []
        return self._sources.attr(entity_id, setting.options_attr) or []

    def common_options(self, setting: Setting) -> set[str]:
        """Return the options, in lower case, shared by the synchronized sources.

        Only the usable sources that offer the setting count: a radiator
        without a fan does not empty the fan options of the others.
        """
        common: set[str] | None = None
        mode_sources = self._sources.mode_sources
        entity_ids = {mode_sources[mode] for mode in self._coordinator.sync_modes}
        for entity_id in entity_ids:
            options = self.options(entity_id, setting)
            if not options:
                continue
            lowered = {option.lower() for option in options if isinstance(option, str)}
            common = lowered if common is None else common & lowered
        return common or set()

    def can_remember(self, mode: HVACMode, setting: Setting, value: Any) -> bool:
        """Return True when a value can be remembered for a mode.

        A synchronized mode only keeps values that all synchronized sources
        accept, so the shared value can always be sent back to them.
        """
        if not isinstance(value, str):
            return False
        if mode not in self._coordinator.sync_modes:
            return True
        return value.lower() in self.common_options(setting)

    @callback
    def observe(
        self, mode: HVACMode, values: dict[str, Any], before: dict[str, Any] | None
    ) -> None:
        """Remember the settings of the active source.

        Entering a mode (before is None) only fills a memory that is still
        empty: the source may still show its own settings before they are
        sent back. Within a mode, every setting change is remembered,
        wherever it comes from.
        """
        memory = self._data.setdefault(self.key(mode), {})
        for setting in SETTINGS:
            value = values[setting.attr]
            if before is None:
                if setting.attr in memory:
                    continue
            elif value == before[setting.attr]:
                continue
            # The same value in another case (sent back to a source) is kept as is.
            if self.can_remember(mode, setting, value) and not same_value(
                memory.get(setting.attr), value
            ):
                memory[setting.attr] = value

    async def async_send(self, mode: HVACMode, entity_id: str) -> None:
        """Send the remembered settings of a mode to its source.

        A value the source does not offer, or already has, is not sent. A
        shared value that is no longer common (the sources changed) is
        replaced by the current value of the source, when it can be
        remembered. A source error is logged without failing the mode change.
        """
        memory = self._data.get(self.key(mode), {})
        for setting in SETTINGS:
            value = memory.get(setting.attr)
            if value is None:
                continue
            if mode in self._coordinator.sync_modes and (
                value.lower() not in self.common_options(setting)
            ):
                del memory[setting.attr]
                current = self._sources.attr(entity_id, setting.attr)
                if self.can_remember(mode, setting, current):
                    memory[setting.attr] = current
                continue
            option = match_option(self.options(entity_id, setting), value)
            if option is None or same_value(
                self._sources.attr(entity_id, setting.attr), option
            ):
                continue
            try:
                await self._sources.async_call(
                    setting.service, entity_id, {setting.attr: option}
                )
            except HomeAssistantError as err:
                _LOGGER.warning(
                    "Could not restore %s %s on %s: %s",
                    setting.attr,
                    option,
                    entity_id,
                    err,
                )
