"""Source entity port: S=>SE_* calls; state changes turned into SE=>S_* events (ARCHITECTURE §6)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import State

from ...core.model.events import (
    SE_ATTRIBUTES,
    SE_CALL_FAILED,
    SE_OFF,
    SE_ON,
    SE_UNAVAILABLE,
    SE_UNKNOWN,
    Call,
    Event,
)
from ...core.model.values import Snapshot

if TYPE_CHECKING:
    from ..entry.host import EntryHost

_LOGGER = logging.getLogger(__package__)


def to_snapshot(state: State | None) -> Snapshot | None:
    """The state and attributes of an entity; None when it does not exist."""
    if state is None:
        return None
    return Snapshot(state.state, dict(state.attributes))


def classify(old: State | None, new: State | None) -> str:
    """The event of a state change of a source entity (spec §1.1.2)."""
    if new is None or new.state == STATE_UNAVAILABLE:
        return SE_UNAVAILABLE
    if new.state == STATE_UNKNOWN:
        return SE_UNKNOWN
    if old is None or old.state != new.state:
        return SE_OFF if new.state == STATE_OFF else SE_ON
    return SE_ATTRIBUTES


class SourceEntityAdapter:
    """A source entity, through Home Assistant."""

    def __init__(self, host: EntryHost, entity_id: str) -> None:
        self._host = host
        self._entity_id = entity_id

    def snapshot(self) -> Snapshot | None:
        """The state and attributes now."""
        return to_snapshot(self._host.hass.states.get(self._entity_id))

    def call(self, call: Call, data: dict[str, Any]) -> None:
        """Launched after the stimulus, not awaited (ARCH-4)."""
        self._host.launch(self._call(call, data))

    async def _call(self, call: Call, data: dict[str, Any]) -> None:
        try:
            await self._host.hass.services.async_call(
                CLIMATE_DOMAIN,
                call.service,
                {ATTR_ENTITY_ID: self._entity_id, **data},
                blocking=True,
            )
        except Exception as err:  # noqa: BLE001 - any error of the call comes back as an event
            _LOGGER.debug("%s %s(%s) failed: %s", self._entity_id, call.service, data, err)
            self._host.submit(
                self._entity_id, Event(SE_CALL_FAILED, self._entity_id, call)
            )
