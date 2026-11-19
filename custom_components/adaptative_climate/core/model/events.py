"""The events of the spec (§1.1.2, §1.2.1, §1.3.1, §4.4).

An event is a message `X=>Y_name`: its kind names it, `sender` is the actor
or the entity of Home Assistant it comes from, `value` carries its argument
(a mode, settings, a temperature, a snapshot...).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Home Assistant -> actors
HA_START = "HA=>X_start"
HA_UNLOAD = "HA=>X_unload"

# User -> AC entity
U_SET_MODE = "U=>AC_set_mode"  # value: mode, or None for turn_on (ENT-STATE-8)
U_SET_SETTINGS = "U=>AC_set_settings"  # value: dict of settings (+ hvac_mode)

# Temperature sensor -> AC entity
T_TEMPERATURE = "T=>AC_temperature"  # value: temperature@T or None

# Source -> AC entity (sender: the source id)
S_UNDISCOVERED = "S=>AC_undiscovered"
S_OFF = "S=>AC_off"
S_ON = "S=>AC_on"  # value: mode
S_UNUSABLE = "S=>AC_unusable"
S_USABLE = "S=>AC_usable"
S_SETTINGS = "S=>AC_settings"  # value: dict of settings, as read
S_TEMPERATURE = "S=>AC_temperature"  # value: temperature or None
S_CAPABILITIES = "S=>AC_capabilities"
S_ACTION = "S=>AC_action"  # value: hvac_action or None

#: The events that tell the state of a source (its first state included).
S_STATE_EVENTS = (S_UNDISCOVERED, S_OFF, S_ON, S_UNUSABLE)

# AC entity -> source
AC_REQUEST = "AC=>S_request"  # value: mode or off
AC_SETTINGS = "AC=>S_settings"  # value: dict of settings, on the scale of the source

# Source entity -> source (value: the snapshot, None when removed)
SE_OFF = "SE=>S_off"
SE_ON = "SE=>S_on"
SE_UNAVAILABLE = "SE=>S_unavailable"
SE_UNKNOWN = "SE=>S_unknown"
SE_ATTRIBUTES = "SE=>S_attributes"
SE_CALL_FAILED = "SE=>S_call_failed"  # value: the Call

SE_CHANGES = (SE_OFF, SE_ON, SE_ATTRIBUTES)
SE_NOT_USABLE = (SE_UNAVAILABLE, SE_UNKNOWN)
SE_SNAPSHOT_EVENTS = SE_CHANGES + SE_NOT_USABLE

# External sensor entity -> AC entity (sender: the external sensor entity id)
XS_USABLE = "XS=>AC_usable"
XS_CALL_FAILED = "XS=>AC_call_failed"

# Source or AC entity -> monitoring (value: the Problem)
M_UP = "X=>M_up"
M_DOWN = "X=>M_down"

# End of a timer: value is (timer name, start number) (ARCHITECTURE ARCH-7)
TIMEOUT = "timeout"

# Between the functions of a source
SDSM_RESTORED = "Sdsm=>Sstm_restored"
SDSM_DISCOVERED = "Sdsm=>Sstm_discovered"
SDSM_SERVED_MODE_LOST = "Sdsm=>Sx_served_mode_lost"
SDSM_SERVED_MODES_BACK = "Sdsm=>Sstm_served_modes_back"
SSTM_SEND = "Sstm=>Smrc_send"  # value: r
SSTM_MODE_CHANGED = "Sstm=>Ssrm_mode_changed"  # value: x
SSTM_TAKEOVER = "Sstm=>Ssrm_takeover"  # value: x
SSTM_UNUSABLE = "Sstm=>Ssrm_unusable"
SSTM_BACK = "Sstm=>Ssrm_back"  # value: m
SSTM_RESTORED = "Sstm=>Ssrm_restored"  # value: m
SMRC_CONFIRMED = "Smrc=>Ssrm_confirmed"  # value: m

# Between the functions of the AC entity
ACCAM_CAPABILITIES_CHANGED = "ACcam=>ACsem_capabilities_changed"
ACSEM_TARGETS_CHANGED = "ACsem=>ACmom_targets_changed"
ACSTM_ENTERED = "ACstm=>ACmom_entered"
ACSTM_LEFT = "ACstm=>ACmom_left"


@dataclass(frozen=True, slots=True)
class Event:
    """One event of the spec."""

    kind: str
    sender: str = ""
    value: Any = None

    def is_timeout(self, name: str) -> bool:
        """Whether this is the end of the timer `name`."""
        return self.kind == TIMEOUT and self.value[0] == name


@dataclass(frozen=True, slots=True)
class Call:
    """A service call to a source entity (S=>SE_*), as given back on error."""

    service: str  # set_hvac_mode, set_temperature, set_fan_mode...
    retry: bool = False  # the call made on Ssrm_send_retry_timeout (SRC-SET-7)


SET_HVAC_MODE = "set_hvac_mode"
SET_TEMPERATURE = "set_temperature"
SET_FAN_MODE = "set_fan_mode"
SET_SWING_MODE = "set_swing_mode"
SET_SWING_HORIZONTAL_MODE = "set_swing_horizontal_mode"
