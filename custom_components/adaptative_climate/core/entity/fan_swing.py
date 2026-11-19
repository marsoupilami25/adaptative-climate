"""Fan and swing values and memories of the AC entity (spec §1.3.5.4, §1.3.4.6)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..model.values import FAN_SWING_SETTINGS, MODE_ORDER, PHASES, match_option

if TYPE_CHECKING:
    from .entity import ACEntity

SYNC = "sync"
BI_SOURCE = "bi_source"


class FanSwing:
    """Memories of the modes (ENT-FANV-1, ENT-FANV-2) and the values not shared."""

    def __init__(self, entity: ACEntity) -> None:
        self._entity = entity
        #: A value chosen in the current mode that its memory cannot hold (ENT-FANV-3).
        self.not_shared: dict[str, str] = {}

    # --- Memories ------------------------------------------------------------------

    def sync_modes(self) -> list[str]:
        """The synchronized modes: configured, a bi-source heat_cool excepted (ENT-FAN-7)."""
        entry = self._entity.entry
        return sorted(
            (m for m in set(entry.sync_modes) if m in entry.modes and not entry.is_bi(m)),
            key=MODE_ORDER.index,
        )

    def all_synced(self) -> bool:
        """Every configured mode is in sync_modes, a bi-source heat_cool excepted (ENT-FAN-3)."""
        entry = self._entity.entry
        modes = [m for m in entry.modes if not entry.is_bi(m)]
        return bool(modes) and set(modes) <= set(self.sync_modes())

    def key_of(self, label: str, phase: bool) -> str:
        """Memory of a mode, or of a phase of the bi-source heat_cool."""
        if phase and self._entity.entry.bi_source_sync:
            return BI_SOURCE
        return SYNC if label in self.sync_modes() else label

    def memory_keys(self) -> set[str]:
        """Memories of the configured modes (ENT-FANV-1)."""
        entry = self._entity.entry
        keys = {self.key_of(m, False) for m in entry.modes if not entry.is_bi(m)}
        if entry.bi_source:
            keys |= {self.key_of(p, True) for p in PHASES}
        return keys

    def contributors(self, key: str) -> list[tuple[str, str]]:
        """(source, source mode) of the modes sharing a memory, in mode order."""
        cam = self._entity.cam
        if key == BI_SOURCE:
            return [cam.phase_context(p) for p in PHASES]
        modes = self.sync_modes() if key == SYNC else [key]
        return [c for m in modes if (c := cam.mode_context(m)) is not None]

    def shared_options(self, key: str, setting: str) -> list[str] | None:
        """Options offered by all the modes of a memory (ENT-FAN-6, ENT-FAN-8).

        Modes not discovered, or without the setting, are left out; None when
        no mode is left. Written as the first mode writes them.
        """
        cam = self._entity.cam
        lists = [
            options
            for source_id, mode in self.contributors(key)
            if (options := cam.options(source_id, mode, setting)) is not None
        ]
        if not lists:
            return None
        return [o for o in lists[0] if all(match_option(o, other) for other in lists[1:])]

    def remembered(self, key: str, setting: str) -> str | None:
        """The value remembered in a memory."""
        return self._entity.stored.memory.get(key, {}).get(setting)

    def remember(self, key: str, setting: str, value: str) -> bool:
        """Remember a value if the memory can hold it (ENT-FANV-3)."""
        option = match_option(value, self.shared_options(key, setting))
        if option is None:
            return False
        self._entity.stored.memory.setdefault(key, {})[setting] = option
        self._entity.save()
        return True

    # --- Current context -------------------------------------------------------------

    def current_key(self) -> str | None:
        """Memory of the current mode (of the current phase for the bi-source heat_cool)."""
        context = self._entity.context()
        if context is None:
            return None
        _, _, label, phase = context
        return self.key_of(label, phase)

    def send_values(self, source_id: str, mode: str, label: str, phase: bool) -> dict[str, str]:
        """Values sent to a source in a mode: the remembered ones (ENT-FANV-6)."""
        cam = self._entity.cam
        key = self.key_of(label, phase)
        result = {}
        for setting in FAN_SWING_SETTINGS:
            options = cam.options(source_id, mode, setting)
            if options is None:
                continue
            value = self.not_shared.get(setting) or self.remembered(key, setting)
            option = match_option(value, options)
            if option is not None:
                result[setting] = option
        return result

    def shown(self, setting: str) -> tuple[str | None, list[str]]:
        """Value and options shown (ENT-FAN-3, ENT-FANV-8)."""
        entity = self._entity
        if entity.stm.operating_mode() is None:
            if not self.all_synced():
                return None, []
            options = self.shared_options(SYNC, setting) or []
            value = self.remembered(SYNC, setting)
            return (match_option(value, options) or value) if value else None, options
        context = entity.context()
        if context is None:
            return None, []
        source_id, mode, label, phase = context
        options = entity.cam.options(source_id, mode, setting)
        if options is None:
            return None, []
        value = self.not_shared.get(setting) or self.remembered(self.key_of(label, phase), setting)
        return (match_option(value, options) or value) if value else None, options

    # --- Changes ------------------------------------------------------------------------

    def user_set(self, setting: str, value: str) -> bool:
        """ENT-FANV-4, ENT-FANV-9. True when the active source must get it."""
        entity = self._entity
        if entity.stm.operating_mode() is None:
            if self.all_synced():
                self.remember(SYNC, setting, value)
            return False
        key = self.current_key()
        if key is None:
            return False
        if self.remember(key, setting, value):
            self.not_shared.pop(setting, None)
        else:
            self.not_shared[setting] = value
        return True

    def adopt(self, setting: str, value: str) -> None:
        """A value taken from the active source (takeover, empty memory: ENT-FANV-4, 5)."""
        key = self.current_key()
        if key is None:
            return
        if self.remember(key, setting, value):
            self.not_shared.pop(setting, None)
        else:
            context = self._entity.context()
            options = self._entity.cam.options(context[0], context[1], setting) if context else None
            self.not_shared[setting] = match_option(value, options) or value

    def check_memory(self) -> dict[str, Any]:
        """ENT-FANV-3: remove the remembered values no longer offered.

        Returns the values taken from the source entity of the current mode,
        now expected from it.
        """
        entity = self._entity
        memory = entity.stored.memory
        current = self.current_key()
        context = entity.context()
        taken: dict[str, Any] = {}
        for key in list(memory):
            values = memory[key]
            for setting in list(values):
                shared = self.shared_options(key, setting)
                if shared is None or match_option(values[setting], shared):
                    continue
                removed = values.pop(setting)
                entity.save()
                if key != current or context is None:
                    continue
                source_id, mode = context[0], context[1]
                options = entity.cam.options(source_id, mode, setting)
                if match_option(removed, options):
                    self.not_shared[setting] = removed  # still offered: stays the value shown
                    continue
                shown = entity.sources[source_id].settings.get(setting)
                if shown is not None:
                    self.adopt(setting, shown)
                    taken[setting] = shown
            if not values:
                del memory[key]
        return taken
