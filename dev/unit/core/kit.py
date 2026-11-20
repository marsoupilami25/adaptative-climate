"""The core of an entry, without Home Assistant: fake ports and a manual clock.

`Core` builds the actors as the host does (`ha/entry/host.py`): the entity,
its sources, the monitoring, in start order (EXEC-4), around a runtime.
The test drives it with stimuli (start, changes of the source entities,
user requests, time) and reads the fakes (calls, store, logs, issues).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from custom_components.adaptative_climate.config.options.builder import build
from custom_components.adaptative_climate.core.entity.entity import ACEntity
from custom_components.adaptative_climate.core.model.events import (
    SE_ATTRIBUTES,
    SE_OFF,
    SE_ON,
    SE_UNAVAILABLE,
    SE_UNKNOWN,
    TIMEOUT,
    Call,
    Event,
)
from custom_components.adaptative_climate.core.model.ports import ExternalSensorAttributes
from custom_components.adaptative_climate.core.model.values import Snapshot
from custom_components.adaptative_climate.core.monitoring.monitoring import Monitoring
from custom_components.adaptative_climate.core.runtime.runtime import Runtime
from custom_components.adaptative_climate.core.runtime.stimulus_queue import Stimulus
from custom_components.adaptative_climate.core.source.source import Source

ENTRY_ID = "entry"


class Clock:
    """Seconds since the start of the test."""

    def __init__(self) -> None:
        self.now_s = 0.0

    def now(self) -> str:
        return f"t+{self.now_s:.0f}s"


class FakeTimers:
    """Timers on the manual clock; their ends are stimuli given by `Core.advance`."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.running: dict[tuple[str, str], tuple[int, float]] = {}

    def start(self, owner: str, name: str, number: int, seconds: float) -> None:
        self.running[(owner, name)] = (number, self.clock.now_s + seconds)

    def cancel(self, owner: str, name: str) -> None:
        self.running.pop((owner, name), None)

    def due(self) -> list[tuple[float, str, str, int]]:
        """The timers ended now, earliest first."""
        ended = [
            (when, owner, name, number)
            for (owner, name), (number, when) in self.running.items()
            if when <= self.clock.now_s + 1e-9
        ]
        return sorted(ended)


class FakeStore:
    """The parts of the stored data; `saved` keeps what was written."""

    def __init__(self, parts: dict[str, Any] | None = None) -> None:
        self.parts: dict[str, Any] = dict(parts or {})
        self.saved: list[str] = []

    def load(self, part: str) -> Any:
        return self.parts.get(part)

    def save(self, part: str, data: Any) -> None:
        self.parts[part] = data
        self.saved.append(part)


class FakeNotify:
    def __init__(self) -> None:
        self.logs: list[tuple[str, str]] = []
        self.events: list[dict[str, Any]] = []

    def log(self, level: str, message: str) -> str:
        self.logs.append((level, message))
        return message

    def fire_problem(self, data: dict[str, Any]) -> None:
        self.events.append(data)

    def logged(self, level: str, text: str = "") -> list[str]:
        return [message for lvl, message in self.logs if lvl == level and text in message]


class FakeRepairs:
    def __init__(self) -> None:
        self.issues: dict[str, tuple[str, dict[str, str]]] = {}

    def raise_issue(self, issue_id: str, key: str, placeholders: dict[str, str]) -> None:
        self.issues[issue_id] = (key, placeholders)

    def clear_issue(self, issue_id: str) -> None:
        self.issues.pop(issue_id, None)


@dataclass
class FakeSourceEntity:
    """A source entity: its snapshot, and the calls it gets."""

    entity_id: str
    current: Snapshot | None = None
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def snapshot(self) -> Snapshot | None:
        return self.current

    def call(self, call: Call, data: dict[str, Any]) -> None:
        self.calls.append((call.service, dict(data)))

    def modes_asked(self) -> list[str]:
        return [data["hvac_mode"] for service, data in self.calls if service == "set_hvac_mode"]


@dataclass
class FakeSensor:
    value: float | None = 20.0

    def temperature(self) -> float | None:
        return self.value


@dataclass
class FakeExternal:
    attrs: ExternalSensorAttributes | None = field(
        default_factory=lambda: ExternalSensorAttributes("°C", 0.5, 5.0, 35.0)
    )
    written: list[float] = field(default_factory=list)

    def attributes(self) -> ExternalSensorAttributes | None:
        return self.attrs

    def set_value(self, value: float) -> None:
        self.written.append(value)


def climate(state: str, modes: list[str], **attributes: Any) -> Snapshot:
    """The snapshot of a climate entity: `state`, its `hvac_modes`, its attributes."""
    features = attributes.pop("supported_features", 1 | 128 | 256)  # target, off, on
    values = {
        "hvac_modes": ["off", *modes],
        "supported_features": features,
        "min_temp": 7.0,
        "max_temp": 35.0,
        "temperature": 20.0,
        "current_temperature": 20.0,
        **attributes,
    }
    return Snapshot(state, values)


def classify(old: Snapshot | None, new: Snapshot | None) -> str:
    """As the source entity adapter does (`ha/adapters/source_entity.py`)."""
    if new is None or new.state == "unavailable":
        return SE_UNAVAILABLE
    if new.state == "unknown":
        return SE_UNKNOWN
    if old is None or old.state != new.state:
        return SE_OFF if new.state == "off" else SE_ON
    return SE_ATTRIBUTES


class Core:
    """An entry: its configuration (as in the YAML), stored data, source entities."""

    def __init__(
        self,
        config: dict[str, Any],
        *,
        snapshots: dict[str, Snapshot | None] | None = None,
        stored: dict[str, Any] | None = None,
        sensor: float | None = None,
        unit: str = "°C",
    ) -> None:
        self.clock = Clock()
        self.timers = FakeTimers(self.clock)
        self.store = FakeStore(stored)
        self.notify = FakeNotify()
        self.repairs = FakeRepairs()
        self.model = build(ENTRY_ID, {"name": "Living room", **config}, unit)
        self.runtime = Runtime(self.notify)
        snapshots = snapshots or {}
        self.entities = {
            cfg.entity_id: FakeSourceEntity(cfg.entity_id, snapshots.get(cfg.entity_id))
            for cfg in self.model.sources
        }
        self.sources = {
            cfg.entity_id: Source(
                cfg, self.model, self.entities[cfg.entity_id], self.timers, self.store, self.notify
            )
            for cfg in self.model.sources
        }
        self.sensor = FakeSensor(sensor) if self.model.temperature_sensor else None
        self.externals = {eid: FakeExternal() for eid in self.model.external_sensors}
        self.entity = ACEntity(
            self.model,
            self.sources,
            self.sensor,
            dict(self.externals),
            self.timers,
            self.store,
            self.repairs,
            self.notify,
        )
        self.monitoring = Monitoring(
            self.model, self.timers, self.notify, self.clock, lambda s: f"binary_sensor.{s}"
        )
        self.runtime.add_actor(self.entity)
        for source in self.sources.values():
            self.runtime.add_actor(source)
        self.runtime.add_actor(self.monitoring)

    # --- Stimuli -------------------------------------------------------------------

    def start(self) -> None:
        self.runtime.start()

    def stimulus(self, *initial: tuple[str, Event]) -> None:
        self.runtime.submit(Stimulus(list(initial)))

    def change(self, entity_id: str, new: Snapshot | None) -> None:
        """The source entity changes (its state machine sees it as Home Assistant reports it)."""
        fake = self.entities[entity_id]
        kind = classify(fake.current, new)
        fake.current = new
        self.stimulus((entity_id, Event(kind, entity_id, new)))

    def user(self, kind: str, value: Any = None) -> None:
        self.stimulus((self.entity.actor_id, Event(kind, "U", value)))

    def advance(self, seconds: float) -> None:
        """Time passes; each timer ended is a stimulus, in order."""
        target = self.clock.now_s + seconds
        while True:
            pending = [t for t in self.timers.running.items() if t[1][1] <= target + 1e-9]
            if not pending:
                break
            (owner, name), (number, when) = min(pending, key=lambda t: t[1][1])
            self.clock.now_s = max(self.clock.now_s, when)
            del self.timers.running[(owner, name)]
            self.stimulus((owner, Event(TIMEOUT, "timer", (name, number))))
        self.clock.now_s = target
