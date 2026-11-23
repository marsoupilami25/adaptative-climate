"""The test bench: Home Assistant instances, devices, sensors, time.

One bench per test. It runs Home Assistant instances one after the other, on
the same storage (`hass_storage`), as a real installation that restarts:

- `start(yaml)`: Home Assistant starts. It loads its config entries from the
  storage, shows the devices and sensors, then sets up the integration with
  the YAML given (`adaptative_climate:` of `configuration.yaml`, §3.2).
- `restart(yaml)`: Home Assistant stops (it writes its pending data), then
  starts again. The devices keep their state meanwhile.
- `close()`: the end of the test: the entries are unloaded, Home Assistant
  stops.

The bench knows Home Assistant and the names of the spec only: the domain,
the entity ids of §2.1, the options of §3.1, the event and the issues of §4.4.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from contextlib import AsyncExitStack
from datetime import timedelta
import logging
from typing import Any

from freezegun.api import FrozenDateTimeFactory

from homeassistant import loader
from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.helpers import entity_registry as er, frame, issue_registry as ir
from homeassistant.setup import async_setup_component
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM, UnitSystem

from dev.ha_test import (
    MockModule,
    MockPlatform,
    async_fire_time_changed,
    async_test_home_assistant,
    mock_integration,
    mock_platform,
)

from .ac import AC
from .devices import Device, bind_devices
from .flows import drive
from .sensors import ExternalSensor, RoomSensor

DOMAIN = "adaptative_climate"
PROBLEM_EVENT = "adaptative_climate_problem"
BENCH = "bench"

_LOGGER = logging.getLogger(__name__)


class Bench:
    """Home Assistant with the integration under test, and the world around it."""

    def __init__(self, storage: dict[str, Any], freezer: FrozenDateTimeFactory) -> None:
        self.storage = storage
        self.freezer = freezer
        self.devices: dict[str, Device] = {}
        self.sensors: dict[str, RoomSensor] = {}
        self.externals: dict[str, ExternalSensor] = {}
        self.units: UnitSystem = METRIC_SYSTEM
        self.yaml: list[dict[str, Any]] | None = None
        #: The `adaptative_climate_problem` events of every instance, in order.
        self.events: list[Event] = []
        self._hass: HomeAssistant | None = None
        self._stack: AsyncExitStack | None = None
        self._exceptions: list[BaseException] = []
        #: The entity registry, kept across restarts as Home Assistant does.
        self._registry: list[dict[str, Any]] = []
        self.starts = 0

    # --- The world ------------------------------------------------------------------------

    def device(self, entity_id: str, modes: list[str], **values: Any) -> Device:
        """A device and its source entity (`climate.*`), serving the HVAC modes given."""
        assert entity_id not in self.devices, entity_id
        device = Device(entity_id=entity_id, hvac_modes=list(modes), **values)
        self.devices[entity_id] = device
        return device

    def sensor(self, entity_id: str, value: float | str | None = 20.0, **values: Any) -> RoomSensor:
        """A sensor entity (`sensor.*`), the temperature sensor of an entry."""
        assert entity_id not in self.sensors, entity_id
        sensor = RoomSensor(entity_id=entity_id, value=value, **values)
        self.sensors[entity_id] = sensor
        return sensor

    def external(self, entity_id: str, **values: Any) -> ExternalSensor:
        """An external sensor entity (`number.*` / `input_number.*`) of a device."""
        assert entity_id not in self.externals, entity_id
        external = ExternalSensor(entity_id=entity_id, **values)
        self.externals[entity_id] = external
        return external

    def fahrenheit(self) -> None:
        """Home Assistant in °F from the next start."""
        self.units = US_CUSTOMARY_SYSTEM

    # --- Home Assistant -------------------------------------------------------------------

    @property
    def hass(self) -> HomeAssistant:
        assert self._hass is not None, "Home Assistant is not running"
        return self._hass

    @property
    def running(self) -> bool:
        return self._hass is not None

    async def start(self, yaml: list[dict[str, Any]] | None = None, *, setup: bool = True) -> None:
        """Home Assistant starts, with that YAML for the integration (None: no YAML).

        `setup=False`: the integration is not set up (to set the scene first);
        `setup_integration()` does it.
        """
        assert self._hass is None, "already running"
        self.yaml = yaml
        self.starts += 1
        stack = AsyncExitStack()
        hass = await stack.enter_async_context(async_test_home_assistant())
        self._stack = stack
        self._hass = hass
        self._catch_exceptions(hass)
        frame.async_setup(hass)  # as the `hass` fixture does
        hass.data.pop(loader.DATA_CUSTOM_COMPONENTS, None)  # custom integrations enabled
        hass.config.units = self.units
        # The config entries of the previous instance, from the storage
        hass.config_entries = ConfigEntries(hass, {"_": "not empty"})
        await hass.config_entries.async_initialize()
        hass.bus.async_listen(PROBLEM_EVENT, self._event)
        restored = self._restore_registry(hass)
        await self._show_world(hass)
        if setup:
            await self.setup_integration()
        # As Home Assistant at its start: a registered entity without state is unavailable
        registry = er.async_get(hass)
        for entity_id in restored:
            entry = registry.async_get(entity_id)
            if entry is not None and not entry.disabled and hass.states.get(entity_id) is None:
                entry.write_unavailable_state(hass)

    async def setup_integration(self) -> None:
        """Home Assistant sets up the integration: YAML import, then its entries."""
        config = {DOMAIN: self.yaml} if self.yaml is not None else {}
        assert await async_setup_component(self.hass, DOMAIN, config)
        await self.hass.async_block_till_done()

    async def stop(self) -> None:
        """Home Assistant stops: it writes its pending data; the entries are not unloaded."""
        hass = self.hass
        await hass.async_block_till_done()
        self._keep_registry(hass)
        await hass.async_stop(force=True)
        await self._end_instance()

    async def restart(self, yaml: Any = ..., *, setup: bool = True) -> None:
        """Home Assistant stops, then starts again (same YAML unless given)."""
        await self.stop()
        await self.start(self.yaml if yaml is ... else yaml, setup=setup)

    async def close(self) -> None:
        """End of the test: the entries are unloaded (END-1), Home Assistant stops."""
        if self._hass is not None:
            hass = self._hass
            for entry in hass.config_entries.async_entries():
                if entry.state is ConfigEntryState.LOADED:
                    await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()
            await hass.async_stop(force=True)
            await self._end_instance()
        if self._exceptions:
            raise self._exceptions[0]

    async def _end_instance(self) -> None:
        assert self._stack is not None
        stack, self._stack, self._hass = self._stack, None, None
        await stack.aclose()
        await asyncio.sleep(0)  # the test instance is forgotten on the next loop iteration
        for device in self.devices.values():
            device.hass = device.entity = device.add_entities = None
        for item in (*self.sensors.values(), *self.externals.values()):
            item.hass = None

    def _keep_registry(self, hass: HomeAssistant) -> None:
        """The entity registry is saved when Home Assistant stops."""
        self._registry = [
            {
                "domain": entry.domain,
                "platform": entry.platform,
                "unique_id": entry.unique_id,
                "object_id": entry.entity_id.split(".", 1)[1],
                "config_entry_id": entry.config_entry_id,
            }
            for entry in er.async_get(hass).entities.values()
        ]

    def _restore_registry(self, hass: HomeAssistant) -> list[str]:
        """The entity registry is loaded when Home Assistant starts.

        The entities of a config entry deleted meanwhile are gone with it.
        """
        registry = er.async_get(hass)
        restored = []
        for item in self._registry:
            config_entry = None
            if item["config_entry_id"] is not None:
                config_entry = hass.config_entries.async_get_entry(item["config_entry_id"])
                if config_entry is None:
                    continue
            entry = registry.async_get_or_create(
                item["domain"],
                item["platform"],
                item["unique_id"],
                suggested_object_id=item["object_id"],
                config_entry=config_entry,
            )
            restored.append(entry.entity_id)
        return restored

    def _catch_exceptions(self, hass: HomeAssistant) -> None:
        """An exception in the event loop fails the test, as with the `hass` fixture."""
        loop = hass.loop
        previous = loop.get_exception_handler()

        def handler(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
            self._exceptions.append(context.get("exception") or Exception(context["message"]))
            if previous is not None:
                previous(loop, context)
            else:
                loop.default_exception_handler(context)

        loop.set_exception_handler(handler)

    @callback
    def _event(self, event: Event) -> None:
        self.events.append(event)

    async def _show_world(self, hass: HomeAssistant) -> None:
        """The devices and sensors appear in the new instance."""

        async def setup_platform(
            hass: HomeAssistant, config: Any, add_entities: Any, discovery_info: Any = None
        ) -> None:
            bind_devices(hass, self.devices.values(), add_entities)

        mock_integration(hass, MockModule(BENCH))
        mock_platform(hass, f"{BENCH}.climate", MockPlatform(async_setup_platform=setup_platform))
        assert await async_setup_component(hass, "climate", {"climate": [{"platform": BENCH}]})
        for sensor in self.sensors.values():
            sensor.hass = hass
            sensor.write()
        for external in self.externals.values():
            external.hass = hass
            external.write()
        for domain in {external.domain for external in self.externals.values()}:
            hass.services.async_register(domain, "set_value", self._set_value)
        await hass.async_block_till_done()

    @callback
    def _set_value(self, call: ServiceCall) -> None:
        entity_ids = call.data["entity_id"]
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        for entity_id in entity_ids:
            self.externals[entity_id].receive(call)

    # --- Config entries -------------------------------------------------------------------

    def entries(self) -> list[ConfigEntry]:
        """The config entries of the integration."""
        return self.hass.config_entries.async_entries(DOMAIN)

    def entry(self, name: str) -> ConfigEntry:
        """The config entry of that name (its title)."""
        found = [entry for entry in self.entries() if entry.title.casefold() == name.casefold()]
        assert len(found) == 1, f"{len(found)} entries named {name}"
        return found[0]

    def has_entry(self, name: str) -> bool:
        return any(entry.title.casefold() == name.casefold() for entry in self.entries())

    async def create_entry(self, **options: Any) -> Any:
        """A user creates an entry in the UI with these options (config flow)."""
        flow = self.hass.config_entries.flow
        result = await flow.async_init(DOMAIN, context={"source": "user"})
        result = await drive(flow, result, options)
        await self.hass.async_block_till_done()
        return result

    async def change_options(self, name: str, **options: Any) -> Any:
        """A user changes the options of an entry in the UI (options flow).

        The form shows the current configuration; the options given change it,
        `None` clears one.
        """
        manager = self.hass.config_entries.options
        result = await manager.async_init(self.entry(name).entry_id)
        result = await drive(manager, result, options)
        await self.hass.async_block_till_done()
        return result

    def has_options(self, name: str) -> bool:
        """The entry offers options in the UI."""
        return bool(self.entry(name).supports_options)

    async def reload(self, name: str) -> None:
        """Reload asked from Home Assistant, without configuration change."""
        assert await self.hass.config_entries.async_reload(self.entry(name).entry_id) in (
            True,
            None,
        )
        await self.hass.async_block_till_done()

    async def unload(self, name: str) -> None:
        """Home Assistant unloads the entry (END-1)."""
        assert await self.hass.config_entries.async_unload(self.entry(name).entry_id)
        await self.hass.async_block_till_done()

    async def delete(self, name: str) -> None:
        """The user deletes the entry (END-3)."""
        await self.hass.config_entries.async_remove(self.entry(name).entry_id)
        await self.hass.async_block_till_done()

    # --- What is shown --------------------------------------------------------------------

    def ac(self, name: str) -> AC:
        """The AC entity of an entry, and its monitoring sensors."""
        return AC(self, name)

    def issues(self) -> list[ir.IssueEntry]:
        """The active Repairs issues of the integration."""
        registry = ir.async_get(self.hass)
        return [
            issue
            for (domain, _), issue in registry.issues.items()
            if domain == DOMAIN and issue.active
        ]

    def problem_events(self, **match: Any) -> list[dict[str, Any]]:
        """The data of the `adaptative_climate_problem` events, matching the values given."""
        return [
            dict(event.data)
            for event in self.events
            if all(event.data.get(key) == value for key, value in match.items())
        ]

    def stored_about(self, entry_id: str) -> list[str]:
        """The keys of the storage, outside Home Assistant itself, that refer to an entry."""
        return [
            key
            for key, value in self.storage.items()
            if not key.startswith("core.")
            and (entry_id in key or entry_id in json.dumps(value, default=str))
        ]

    # --- Time -------------------------------------------------------------------------------

    async def advance(self, seconds: float, *, step: float = 1.0) -> None:
        """Let time pass, by steps, the timers ending on their way."""
        remaining = float(seconds)
        while remaining > 1e-9:
            delta = min(step, remaining)
            self.freezer.tick(timedelta(seconds=delta))
            async_fire_time_changed(self.hass)
            await self.hass.async_block_till_done()
            remaining -= delta

    async def settle(self) -> None:
        """Let Home Assistant handle what is pending."""
        await self.hass.async_block_till_done()


def yaml_entry(name: str, **options: Any) -> dict[str, Any]:
    """One entry of `adaptative_climate:` in the YAML."""
    return {"name": name, **options}


def without(options: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    """The options without some keys."""
    return {key: value for key, value in options.items() if key not in keys}
