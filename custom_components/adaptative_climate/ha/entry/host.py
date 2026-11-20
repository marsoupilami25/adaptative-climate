"""Runtime host: the Home Assistant side of a runtime (ARCHITECTURE ARCH-3, ARCH-4, ARCH-8, ARCH-9).

It turns the callbacks of Home Assistant into stimuli, launches the
outgoing calls, writes the views and the store after each stimulus.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any, Protocol

from homeassistant.core import Event as HassEvent, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from ...core.entity.entity import ACEntity
from ...core.model.entry_config import EntryConfig
from ...core.model.events import T_TEMPERATURE, XS_USABLE, Event
from ...core.model.problems import SENSOR_SOURCES, SENSOR_TEMPERATURES
from ...core.monitoring.monitoring import Monitoring
from ...core.runtime.runtime import Runtime
from ...core.runtime.stimulus_queue import Stimulus
from ...core.source.source import Source
from ..adapters.notify import NotifyAdapter
from ..adapters.repairs import RepairsAdapter
from ..adapters.sensors import (
    ExternalSensorAdapter,
    TemperatureSensorAdapter,
    read_temperature,
    usable,
)
from ..adapters.source_entity import SourceEntityAdapter, classify, to_snapshot
from ..adapters.store import StoreAdapter
from ..adapters.timers import ClockAdapter, TimerAdapter


class View(Protocol):
    """A Home Assistant entity of the entry that shows the core (ARCH-8)."""

    def refresh(self) -> None:
        """Write the state if it changed."""


class EntryHost:
    """One per loaded entry: owns the runtime, its actors and its adapters."""

    def __init__(
        self,
        hass: HomeAssistant,
        model: EntryConfig,
        store: Store[dict[str, Any]],
        stored: Any,
    ) -> None:
        self.hass = hass
        self.model = model
        self.notify = NotifyAdapter(hass, model.name)
        self.timers = TimerAdapter(hass, self)
        parts = {"entity"} | {f"source:{s.entity_id}" for s in model.sources}
        self.store = StoreAdapter(store, stored, parts)
        self.repairs = RepairsAdapter(hass)
        self.runtime = Runtime(self.notify)
        self.runtime.on_stimulus_end = self._after_stimulus
        self._calls: list[Coroutine[Any, Any, None]] = []
        self._unsubscribe: list[Callable[[], None]] = []
        self._last_temperature: float | None = None
        self.views: list[View] = []
        self.sensor_entity_ids: dict[str, str | None] = {
            SENSOR_SOURCES: None,
            SENSOR_TEMPERATURES: None,
        }

        self.sources = {
            cfg.entity_id: Source(
                cfg,
                model,
                SourceEntityAdapter(self, cfg.entity_id),
                self.timers,
                self.store,
                self.notify,
            )
            for cfg in model.sources
        }
        self.sensor = (
            TemperatureSensorAdapter(hass, model.temperature_sensor)
            if model.temperature_sensor
            else None
        )
        self.entity = ACEntity(
            model,
            self.sources,
            self.sensor,
            {eid: ExternalSensorAdapter(self, eid) for eid in model.external_sensors},
            self.timers,
            self.store,
            self.repairs,
            self.notify,
        )
        self.monitoring = Monitoring(
            model, self.timers, self.notify, ClockAdapter(), self.sensor_entity_ids.get
        )
        # Start order: the entity before its sources (EXEC-4)
        self.runtime.add_actor(self.entity)
        for source in self.sources.values():
            self.runtime.add_actor(source)
        self.runtime.add_actor(self.monitoring)

    # --- Lifecycle (ARCHITECTURE §8) ------------------------------------------------

    def start(self) -> None:
        """Subscribe to the entities watched, then the start stimulus (EXEC-4)."""
        hass = self.hass
        self._unsubscribe.append(
            async_track_state_change_event(hass, list(self.sources), self._source_changed)
        )
        if self.sensor is not None:
            self._last_temperature = self.sensor.temperature()
            self._unsubscribe.append(
                async_track_state_change_event(
                    hass, [self.sensor.entity_id], self._sensor_changed
                )
            )
        if self.model.external_sensors:
            self._unsubscribe.append(
                async_track_state_change_event(
                    hass, list(self.model.external_sensors), self._external_changed
                )
            )
        self.runtime.start()

    def stop(self) -> None:
        """Unload (END-1): unsubscribe, cancel the timers, drop the stimuli waiting."""
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe.clear()
        self.runtime.stop()
        self.timers.cancel_all()
        self.repairs.clear_all()
        self.store.flush()
        # Safety net (not reached): the calls are launched at the end of each stimulus,
        # so none is waiting at unload; one that were would not be sent (END-1)
        for call in self._calls:
            call.close()
        self._calls.clear()

    # --- Stimuli (ARCH-3) ---------------------------------------------------------------

    def submit(self, actor_id: str, event: Event) -> None:
        """One stimulus with one initial event."""
        self.runtime.submit(Stimulus([(actor_id, event)]))

    def user_request(self, event: Event) -> str | None:
        """A user request: the refusal of the entity, if any (ENT-STATE-4)."""
        self.entity.refusal = None
        self.submit(self.entity.actor_id, event)
        return self.entity.refusal

    @callback
    def _source_changed(self, event: HassEvent[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        new = event.data["new_state"]
        kind = classify(event.data["old_state"], new)
        self.submit(entity_id, Event(kind, entity_id, to_snapshot(new)))

    @callback
    def _sensor_changed(self, event: HassEvent[EventStateChangedData]) -> None:
        value = read_temperature(self.hass, event.data["new_state"])
        if value == self._last_temperature:
            return
        self._last_temperature = value
        self.submit(self.entity.actor_id, Event(T_TEMPERATURE, "T", value))

    @callback
    def _external_changed(self, event: HassEvent[EventStateChangedData]) -> None:
        if usable(event.data["new_state"]) and not usable(event.data["old_state"]):
            self.submit(self.entity.actor_id, Event(XS_USABLE, event.data["entity_id"]))

    # --- After each stimulus (ARCH-4, ARCH-8, ARCH-9) -------------------------------------

    def launch(self, call: Coroutine[Any, Any, None]) -> None:
        """An outgoing call, launched after the stimulus, in the order it was sent."""
        self._calls.append(call)

    def _after_stimulus(self) -> None:
        for view in self.views:
            view.refresh()
        self.store.flush()
        calls, self._calls = self._calls, []
        for call in calls:
            self.hass.async_create_task(call, eager_start=False)
