"""ACsem: settings management of the AC entity (spec §1.3.5).

Entry point of the four parts: reference temperature, external sensors,
temperature targets, fan/swing values and memories.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..model.events import (
    ACCAM_CAPABILITIES_CHANGED,
    ACSEM_TARGETS_CHANGED,
    S_SETTINGS,
    U_SET_SETTINGS,
    Event,
)
from ..model.values import (
    CASE_LOW_HIGH,
    CASE_SINGLE,
    FAN_SWING_SETTINGS,
    HIGH,
    LOW,
    TARGET_TEMP_HIGH,
    TARGET_TEMP_LOW,
    TEMPERATURE,
    TEMPERATURE_SETTINGS,
)
from . import targets
from .external_sensors import ExternalSensors
from .fan_swing import FanSwing

if TYPE_CHECKING:
    from .entity import ACEntity


class SettingsManagement:
    """ACsem: temperature targets, fan/swing, external sensors."""

    def __init__(self, entity: ACEntity) -> None:
        self._entity = entity
        self.external = ExternalSensors(entity)
        self.fan = FanSwing(entity)
        #: Sources followed (AC.follow) in this stimulus: their settings are adopted.
        self.adopt_all: set[str] = set()

    def handle(self, event: Event) -> None:
        """Events of the settings management."""
        self.external.handle(event)
        kind = event.kind
        if kind == U_SET_SETTINGS:
            self._user(event.value)
        elif kind == S_SETTINGS:
            self._reported(event.sender, event.value)
        elif kind == ACCAM_CAPABILITIES_CHANGED:
            self._capabilities_changed(geometry_changed=event.value)

    # --- Expected settings of the active source (ENT-SEND-1) -----------------------

    def settings_for(self, source_id: str, mode: str, label: str, phase: bool) -> dict[str, Any]:
        """Settings sent to a source in a source mode; none for a mode not discovered (ENT-CAP-5)."""
        if self._entity.cam.caps(source_id, mode) is None:
            return {}
        values: dict[str, Any] = targets.send_values(self._entity, source_id, mode, label, phase)
        values.update(self.fan.send_values(source_id, mode, label, phase))
        return values

    def refresh_expected(self, keys: set[str] | None = None) -> None:
        """Compute again the settings expected from the active source."""
        entity = self._entity
        context = entity.context()
        if context is None:
            return
        source_id, mode, label, phase = context
        if entity.sending.expected[source_id].state != mode:
            # Safety net (not reached): the active source is always expected in its mode
            return
        values = self.settings_for(source_id, mode, label, phase)
        entity.sending.expect_settings(source_id, values, keys)

    # --- User (ENT-SET-1) ---------------------------------------------------------

    def _user(self, request: dict[str, Any]) -> None:
        entity = self._entity
        if targets.user_set(entity, request):
            entity.post(Event(ACSEM_TARGETS_CHANGED))
            self.refresh_expected(set(TEMPERATURE_SETTINGS))
        changed = set()
        for setting in FAN_SWING_SETTINGS:
            if setting in request and self.fan.user_set(setting, request[setting]):
                changed.add(setting)
        if changed:
            self.refresh_expected(changed)

    # --- Reported by the active source (ENT-SET-2) -------------------------------

    def _reported(self, source_id: str, values: dict[str, Any]) -> None:
        entity = self._entity
        context = entity.context()
        if context is None or context[0] != source_id or entity.stm.operating_mode() is None:
            return  # from any other source: ignored
        _, mode, label, phase = context
        sending = entity.sending
        case = entity.cam.case(source_id, mode)
        offset = entity.entry.offset_of(source_id)
        taken: dict[str, float] = {}
        for name, value in values.items():
            if name in TEMPERATURE_SETTINGS:
                if case == CASE_SINGLE and name == TEMPERATURE:
                    taken[targets.single_target(label, phase)] = value - offset
                elif case == CASE_LOW_HIGH and name == TARGET_TEMP_LOW:
                    taken[LOW] = value - offset
                elif case == CASE_LOW_HIGH and name == TARGET_TEMP_HIGH:
                    taken[HIGH] = value - offset
                else:
                    # Safety net (not reached): a source only reports the targets of its case
                    continue
                sending.reported_setting(source_id, name, value)
            elif name in FAN_SWING_SETTINGS:
                key = self.fan.key_of(label, phase)
                if (
                    source_id not in self.adopt_all
                    and self.fan.remembered(key, name) is not None
                    and name not in sending.sent[source_id].settings
                ):
                    # A value for a capability just discovered: the remembered one is sent (ENT-FANV-5)
                    sending.reported_setting(source_id, name, value, sent_only=True)
                    continue
                self.fan.adopt(name, value)
                sending.reported_setting(source_id, name, value)
        if taken:
            targets.takeover(entity, taken)
            entity.post(Event(ACSEM_TARGETS_CHANGED))

    # --- Capabilities changed (ENT-CAP-7) -------------------------------------------

    def _capabilities_changed(self, geometry_changed: bool) -> None:
        entity = self._entity
        if geometry_changed:
            targets.bring_in_line(entity)  # ENT-TGT-4
            entity.post(Event(ACSEM_TARGETS_CHANGED))
        taken = self.fan.check_memory()  # ENT-FANV-3
        self.refresh_expected()
        context = entity.context()
        if context is not None and taken:
            entity.sending.expect_settings(context[0], taken, set(taken))

    # --- Entering OPER --------------------------------------------------------------

    def leave_init(self) -> None:
        """ENT-INIT-1, ENT-TGT-4: the kept targets brought back in line."""
        targets.bring_in_line(self._entity)

    def enter_oper(self) -> None:
        """ENT-TGT-10: the missing targets taken from the sources."""
        targets.first_targets(self._entity)
