"""Ssrm: setting request management of a source (spec §1.2.5)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..model.events import (
    AC_SETTINGS,
    HA_START,
    S_SETTINGS,
    SE_ATTRIBUTES,
    SE_CALL_FAILED,
    SET_FAN_MODE,
    SET_HVAC_MODE,
    SET_SWING_HORIZONTAL_MODE,
    SET_SWING_MODE,
    SET_TEMPERATURE,
    SMRC_CONFIRMED,
    SSTM_BACK,
    SSTM_MODE_CHANGED,
    SSTM_RESTORED,
    SSTM_TAKEOVER,
    SSTM_UNUSABLE,
    Call,
    Event,
)
from ..model.values import (
    FAN_MODE,
    FAN_SWING_SETTINGS,
    OFF,
    SETTINGS,
    SWING_HORIZONTAL_MODE,
    SWING_MODE,
    TARGET_TEMP_HIGH,
    TARGET_TEMP_LOW,
    TEMPERATURE,
    Snapshot,
    as_number,
    is_usable,
    match_option,
    same_setting,
)

if TYPE_CHECKING:
    from .source import Source

HOLD = "HOLD"
SETTLE = "SETTLE"
ACTIVE = "ACTIVE"

SETTLE_TIMER = "settle"
RESYNC_TIMER = "resync"
SEND_RETRY_TIMER = "send_retry"

#: Fixed durations (CFG-TIMER-2).
RESYNC_SECONDS = 30 * 60
SEND_RETRY_SECONDS = 5

SERVICE_OF = {
    FAN_MODE: SET_FAN_MODE,
    SWING_MODE: SET_SWING_MODE,
    SWING_HORIZONTAL_MODE: SET_SWING_HORIZONTAL_MODE,
}


def shown_settings(snapshot: Snapshot | None) -> dict[str, Any]:
    """The settings the source entity shows now (`shown`)."""
    if not is_usable(snapshot):
        return {}
    result: dict[str, Any] = {}
    for name in SETTINGS:
        value = snapshot.get(name)
        if value is None:
            continue
        if name in FAN_SWING_SETTINGS:
            result[name] = str(value)
        elif (number := as_number(value)) is not None:
            result[name] = number
    return result


class SettingRequestManagement:
    """Ssrm: keeps, sends, protects and follows the settings."""

    def __init__(self, source: Source) -> None:
        self._source = source
        self.state = HOLD
        self.other_shown = False

    @property
    def kept(self) -> dict[str, Any]:
        """The kept settings, stored with the state of the source."""
        return self._source.data.kept

    def handle(self, event: Event) -> None:
        """Transitions of §1.2.5."""
        kind = event.kind
        source = self._source
        timers = source.timers
        if kind == HA_START:
            timers.start(RESYNC_TIMER, RESYNC_SECONDS)
        elif kind == AC_SETTINGS:
            self.kept.update(event.value)
            source.save()
            if self.state != HOLD:
                self.send()
        elif kind in (SMRC_CONFIRMED, SSTM_BACK):
            if self.state == HOLD:
                self._enter_settle()
        elif kind == SSTM_RESTORED:
            if self.state == HOLD:
                self.state = ACTIVE
        elif kind == SSTM_TAKEOVER and event.value != OFF:
            timers.cancel(SETTLE_TIMER)
            shown = shown_settings(source.snapshot)
            self._replace_kept(shown)
            timers.cancel(SEND_RETRY_TIMER)
            self.state = ACTIVE
            if shown:
                source.send_ac(S_SETTINGS, shown)
        elif kind in (SSTM_MODE_CHANGED, SSTM_TAKEOVER):
            timers.cancel(SETTLE_TIMER)
            self._replace_kept({})
            timers.cancel(SEND_RETRY_TIMER)
            self.state = HOLD
        elif kind == SSTM_UNUSABLE:
            timers.cancel(SETTLE_TIMER)
            timers.cancel(SEND_RETRY_TIMER)
            self.state = HOLD
        elif kind == SE_ATTRIBUTES:
            if self.state == SETTLE:
                self._settle_attributes()
            elif self.state == ACTIVE:
                self._takeover()
        elif event.is_timeout(SETTLE_TIMER):
            if self.state == SETTLE:
                self.state = ACTIVE
                if self.other_shown:
                    self.send()
        elif event.is_timeout(RESYNC_TIMER):
            if self.state != HOLD:
                self.send()
            timers.start(RESYNC_TIMER, RESYNC_SECONDS)
        elif event.is_timeout(SEND_RETRY_TIMER):
            if self.state != HOLD:
                self.send(retry=True)
        elif kind == SE_CALL_FAILED:
            call: Call = event.value
            if call.service == SET_HVAC_MODE:
                return
            if call.retry:
                source.notify.log(
                    "warning",
                    f"{source.cfg.entity_id}: {call.service} failed again; "
                    "the resync will send it again",
                )
            else:
                timers.start(SEND_RETRY_TIMER, SEND_RETRY_SECONDS)

    # --- States ----------------------------------------------------------------

    def _enter_settle(self) -> None:
        self.state = SETTLE
        self.other_shown = False
        self._source.timers.start(SETTLE_TIMER, self._source.entry.settle_timer)
        self.send()
        self._report(changed_only=False)

    def _replace_kept(self, settings: dict[str, Any]) -> None:
        self.kept.clear()
        self.kept.update(settings)
        self._source.save()

    # --- Composite activities ------------------------------------------------------

    def send(self, retry: bool = False) -> None:
        """Ssrm.send: each kept setting the source entity does not show (SRC-SET-4)."""
        source = self._source
        shown = shown_settings(source.snapshot)
        step = source.temp_step()
        kept = self.kept
        caps = source.current_caps()
        if TEMPERATURE in kept and not same_setting(
            TEMPERATURE, shown.get(TEMPERATURE), kept[TEMPERATURE], step
        ):
            source.port.call(Call(SET_TEMPERATURE, retry), {TEMPERATURE: kept[TEMPERATURE]})
        if TARGET_TEMP_LOW in kept or TARGET_TEMP_HIGH in kept:
            low = kept.get(TARGET_TEMP_LOW, shown.get(TARGET_TEMP_LOW))
            high = kept.get(TARGET_TEMP_HIGH, shown.get(TARGET_TEMP_HIGH))
            if (
                low is not None
                and high is not None
                and not (
                    same_setting(TARGET_TEMP_LOW, shown.get(TARGET_TEMP_LOW), low, step)
                    and same_setting(TARGET_TEMP_HIGH, shown.get(TARGET_TEMP_HIGH), high, step)
                )
            ):
                source.port.call(
                    Call(SET_TEMPERATURE, retry),
                    {TARGET_TEMP_LOW: low, TARGET_TEMP_HIGH: high},
                )
        for name in FAN_SWING_SETTINGS:
            if name not in kept:
                continue
            option = match_option(kept[name], caps.options(name) if caps else None)
            if option is None or same_setting(name, shown.get(name), option, step):
                continue
            source.port.call(Call(SERVICE_OF[name], retry), {name: option})

    def _report(self, changed_only: bool) -> None:
        """Ssrm.report: fan/swing without kept value shown (SRC-SET-12)."""
        source = self._source
        shown = shown_settings(source.snapshot)
        before = shown_settings(source.prev_snapshot)
        report = {}
        for name in FAN_SWING_SETTINGS:
            if name in self.kept or name not in shown:
                continue
            if changed_only and same_setting(name, before.get(name), shown[name], 1):
                continue
            report[name] = shown[name]
        if report:
            source.send_ac(S_SETTINGS, report)

    def _settle_attributes(self) -> None:
        """SETTLE: values shown for the kept settings ignored; other_shown noted."""
        source = self._source
        shown = shown_settings(source.snapshot)
        step = source.temp_step()
        for name, value in self.kept.items():
            if name in shown and not same_setting(name, shown[name], value, step):
                self.other_shown = True
        self._report(changed_only=True)

    def _takeover(self) -> None:
        """ACTIVE: a setting changed on the source entity is adopted (SRC-SET-11)."""
        source = self._source
        shown = shown_settings(source.snapshot)
        before = shown_settings(source.prev_snapshot)
        step = source.temp_step()
        changes = {}
        for name, value in shown.items():
            if name in before and same_setting(name, before[name], value, step):
                continue
            if name in self.kept and same_setting(name, self.kept[name], value, step):
                continue
            changes[name] = value
        if changes:
            self.kept.update(changes)
            source.save()
            source.send_ac(S_SETTINGS, changes)

    # --- Monitoring (SRC-SET-9) -------------------------------------------------------

    def not_applied(self) -> list[str]:
        """In ACTIVE, the kept settings the source entity does not show."""
        if self.state != ACTIVE:
            return []
        source = self._source
        shown = shown_settings(source.snapshot)
        step = source.temp_step()
        caps = source.current_caps()
        result = []
        for name, value in self.kept.items():
            if name in FAN_SWING_SETTINGS:
                value = match_option(value, caps.options(name) if caps else None)
                if value is None:
                    continue  # not offered: not sent
            if not same_setting(name, shown.get(name), value, step):
                result.append(name)
        return result
