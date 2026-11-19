"""Expected / sent: what the entity sends to its sources (ENT-SEND, §1.3.2.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..model.events import AC_REQUEST, AC_SETTINGS, Event
from ..model.values import OFF, TARGET_TEMP_HIGH, TARGET_TEMP_LOW, same_setting

if TYPE_CHECKING:
    from .entity import ACEntity


@dataclass
class Expectation:
    """A state (off, or a source mode) and the settings of its mode."""

    state: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)


class Sending:
    """expected(S) and sent(S) of each source (ENT-SEND-1, ENT-SEND-2)."""

    def __init__(self, entity: ACEntity) -> None:
        self._entity = entity
        self.expected: dict[str, Expectation] = {}
        self.sent: dict[str, Expectation] = {}
        self.reset()

    def reset(self) -> None:
        """At HA=>AC_start, sent(S) is empty: everything is sent again."""
        for source_id in self._entity.sources:
            self.expected[source_id] = Expectation()
            self.sent[source_id] = Expectation()

    # --- Activities ------------------------------------------------------------

    def expect_only(self, active: str | None, state: str | None, settings: dict[str, Any]) -> None:
        """`active` expected in `state` with its settings; every other source off.

        UNDISCOVERED sources are left as they are (ENT-SEND-3). With `active`
        None, every source is expected off.
        """
        for source_id in self._entity.sources:
            if self._entity.source_state(source_id).undiscovered:
                continue
            if source_id == active:
                self.expected[source_id] = Expectation(state, dict(settings))
            else:
                self.expected[source_id] = Expectation(OFF, {})

    def expect_others_off(self, keep: list[str]) -> None:
        """Every source not in `keep` (and not UNDISCOVERED) expected off."""
        for source_id in self._entity.sources:
            if source_id in keep or self._entity.source_state(source_id).undiscovered:
                continue
            self.expected[source_id] = Expectation(OFF, {})

    def expect_settings(self, source_id: str, settings: dict[str, Any], keys: set[str] | None = None) -> None:
        """Settings expected from the active source: all of them, or only `keys`."""
        expectation = self.expected[source_id]
        if keys is None:
            expectation.settings = dict(settings)
            return
        for name in keys:
            if name in settings:
                expectation.settings[name] = settings[name]
            else:
                expectation.settings.pop(name, None)

    # --- Reported by a source (ENT-SEND-2) ---------------------------------------

    def reported_state(self, source_id: str, state: str) -> None:
        """A state reported: written in both; the source withdrew its settings."""
        self.expected[source_id] = Expectation(state, {})
        self.sent[source_id] = Expectation(state, {})

    def reported_setting(self, source_id: str, name: str, value: Any, sent_only: bool = False) -> None:
        """A setting reported by the active source."""
        self.sent[source_id].settings[name] = value
        if not sent_only:
            self.expected[source_id].settings[name] = value

    # --- Hook (ENT-SEND-3) ---------------------------------------------------------

    def flush(self) -> None:
        """Send the difference between expected(S) and sent(S), then sent := expected."""
        entity = self._entity
        for source_id in entity.sources:
            if entity.source_state(source_id).undiscovered:
                continue
            expected = self.expected[source_id]
            sent = self.sent[source_id]
            if expected.state is None:
                continue
            if expected.state != sent.state:
                entity.send(source_id, Event(AC_REQUEST, entity.actor_id, expected.state))
                sent.state = expected.state
                sent.settings = {}
            if expected.state == OFF:
                continue
            step = entity.cam.source_step(source_id, expected.state)
            diff = {
                name: value
                for name, value in expected.settings.items()
                if name not in sent.settings
                or not same_setting(name, sent.settings[name], value, step)
            }
            if TARGET_TEMP_LOW in diff or TARGET_TEMP_HIGH in diff:
                for name in (TARGET_TEMP_LOW, TARGET_TEMP_HIGH):
                    if name in expected.settings:
                        diff[name] = expected.settings[name]
            if diff:
                entity.send(source_id, Event(AC_SETTINGS, entity.actor_id, diff))
                sent.settings.update(diff)
