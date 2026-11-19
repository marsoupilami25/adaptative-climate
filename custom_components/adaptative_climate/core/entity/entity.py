"""The AC entity actor, its problems, its Repairs issues and its view (spec §1.3, §2.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import TYPE_CHECKING, Any

from ..model.entry_config import EntryConfig
from ..model.events import HA_START, HA_UNLOAD, M_DOWN, M_UP, U_SET_MODE, U_SET_SETTINGS, Event
from ..model.ports import (
    ExternalSensorPort,
    NotifyPort,
    RepairsPort,
    StorePort,
    TemperatureSensorPort,
    TimerPort,
)
from ..model.problems import (
    GAP_SENSOR_SOURCE,
    GAP_SOURCES,
    SENSOR_SOURCES,
    SENSOR_TEMPERATURES,
    SENSOR_WITHOUT_VALUE,
    SOURCE_UNUSABLE,
    Problem,
    ProblemTracker,
)
from ..model.values import (
    FAN_SWING_SETTINGS,
    HEAT_COOL,
    HIGH,
    LOW,
    OFF,
    PHASES,
    SINGLE,
    TARGET_TEMP_HIGH,
    TARGET_TEMP_LOW,
    TEMPERATURE,
    TEMPERATURE_SETTINGS,
    as_number,
)
from ..runtime.actor import Actor
from . import reference, targets
from .capabilities import CapabilitiesManagement
from .mode import WAITING_PHASE, ModeManagement
from .sending import Sending
from .settings import SettingsManagement
from .state import INIT, NO_SOURCE, STATE_OFF, STATE_ON, WAITING, EntityStateManagement
from .stored import PART, restore

if TYPE_CHECKING:
    from ..source.source import Source, SourceState

ENTITY = "AC"
MONITORING = "monitoring"

# Refusals of a user request (ENT-TGT-7, ENT-FAN-4)
FEATURE_NOT_SUPPORTED = "feature_not_supported"
TEMPERATURE_OUT_OF_RANGE = "temperature_out_of_range"
LOW_ABOVE_HIGH = "low_above_high"
SETTING_NOT_AVAILABLE = "setting_not_available"
INVALID_OPTION = "invalid_option"

EPSILON = 1e-6


@dataclass
class ClimateView:
    """What the climate view shows (ARCHITECTURE ARCH-8)."""

    available: bool = False
    hvac_mode: str | None = None
    hvac_modes: list[str] = field(default_factory=list)
    hvac_action: str | None = None
    current_temperature: float | None = None
    temperature: float | None = None
    target_temp_low: float | None = None
    target_temp_high: float | None = None
    min_temp: float = 7.0
    max_temp: float = 35.0
    step: float = 0.5
    features: int = 0
    values: dict[str, str | None] = field(default_factory=dict)
    options: dict[str, list[str]] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)


class ACEntity(Actor):
    """The AC entity: decides the mode and drives its sources (spec §1.3)."""

    def __init__(
        self,
        entry: EntryConfig,
        sources: dict[str, Source],
        sensor_port: TemperatureSensorPort | None,
        xs_ports: dict[str, ExternalSensorPort],
        timer_port: TimerPort,
        store: StorePort,
        repairs: RepairsPort,
        notify: NotifyPort,
    ) -> None:
        super().__init__(ENTITY, timer_port)
        self.entry = entry
        self.sources = sources
        self.sensor_port = sensor_port
        self.xs_ports = xs_ports
        self.repairs = repairs
        self.notify = notify
        self._store = store
        self.sending = Sending(self)
        self.stm = EntityStateManagement(self)
        self.mom = ModeManagement(self)
        self.cam = CapabilitiesManagement(self)
        self.sem = SettingsManagement(self)
        self.stored, self._config_changed = restore(
            store.load(PART), entry, self.sem.fan.memory_keys()
        )
        # The order of §1.3: a step is deterministic (ARCHITECTURE §4.2)
        self.functions = [self.stm, self.mom, self.cam, self.sem]
        self.refusal: str | None = None
        self._problems = ProblemTracker()
        self._issues: dict[str, dict[str, tuple[str, dict[str, str]]]] = {}

    # --- Frame -----------------------------------------------------------------

    def step(self, event: Event) -> None:
        """A user request is checked first: a refused one is not handled (ENT-STATE-4)."""
        if event.kind in (U_SET_MODE, U_SET_SETTINGS):
            self.refusal = None
            if self.stm.state in (INIT, NO_SOURCE):
                return  # unavailable: Home Assistant does not call it (ENT-NOSRC-3)
            self.refusal = self._check_user(event)
            if self.refusal is not None:
                return
        super().step(event)

    def before_step(self, event: Event) -> None:
        """Start and unload of the entity."""
        if event.kind == HA_START:
            self.sending.reset()
            if self._config_changed:
                self.notify.log("info", "Configuration changed: the entity starts off")
            self.save()  # the fingerprint it runs with (ARCHITECTURE §8)
        elif event.kind == HA_UNLOAD:
            for group in list(self._issues):
                self._set_issues(group, {})

    def end_of_step(self) -> None:
        """Hook: send to the sources (ENT-SEND-3), tell the problems (MON-SEND-1)."""
        if self.stm.state != INIT:
            self.sending.flush()
        self.sem.adopt_all.clear()
        ups, downs = self._problems.diff(self._judge_problems())
        for problem in ups:
            self.send(MONITORING, Event(M_UP, self.actor_id, problem))
        for problem in downs:
            self.send(MONITORING, Event(M_DOWN, self.actor_id, problem))
        self._check_mode_issues()

    def save(self) -> None:
        """`save`: write the stored data."""
        self._store.save(PART, self.stored.to_dict())

    # --- Reading the sources ----------------------------------------------------------

    def source_state(self, source_id: str | None) -> SourceState:
        """state@S."""
        return self.sources[source_id].state  # type: ignore[index]

    def any_available(self) -> bool:
        """At least one source available."""
        return any(source.state.available for source in self.sources.values())

    def mode_available(self, mode: str) -> bool:
        """The source of m is available; bi-source: one phase source (ENT-HVAC-2, 3)."""
        return any(self.source_state(s).available for s in self.entry.sources_of(mode))

    def context(self) -> tuple[str, str, str, bool] | None:
        """(active source, source mode, mode or phase, is a phase) in ON(m) / WAITING(m)."""
        mode = self.stm.operating_mode()
        if mode is None:
            return None
        if self.entry.is_bi(mode):
            phase = self.mom.phase
            if phase is None:
                return None
            return self.entry.phase_source(phase), phase, phase, True
        source_id = self.entry.source_of(mode)
        return (source_id, mode, mode, False) if source_id else None

    def active_source(self) -> str | None:
        """The source of the current mode (of the current phase); None in OFF."""
        context = self.context()
        return context[0] if context else None

    def last_used_mode(self) -> str | None:
        """The last used mode, if still configured (ENT-STATE-2)."""
        last = self.stored.last_used
        return last if last in self.entry.modes else None

    def turn_on_mode(self) -> str:
        """The mode turn_on would start: the last used mode, else the first configured."""
        return self.last_used_mode() or self.entry.modes[0]

    def sensor_temperature(self) -> float | None:
        """temperature@T."""
        return self.sensor_port.temperature() if self.sensor_port else None

    # --- User requests (ENT-STATE-4, ENT-TGT-7, ENT-FAN-4) -----------------------------

    def _check_user(self, event: Event) -> str | None:
        if event.kind == U_SET_MODE:
            return self.stm.check_mode(event.value)[1]
        request: dict[str, Any] = event.value
        if "hvac_mode" in request:
            refusal = self.stm.check_mode(request["hvac_mode"])[1]
            if refusal:
                return refusal
        if TEMPERATURE in request and not self.cam.has_single():
            return FEATURE_NOT_SUPPORTED
        if (TARGET_TEMP_LOW in request or TARGET_TEMP_HIGH in request) and not self.cam.has_low_high():
            return FEATURE_NOT_SUPPORTED
        low, high = self.shown_range()
        for name in TEMPERATURE_SETTINGS:
            if name in request:
                value = as_number(request[name])
                if value is None or value < low - EPSILON or value > high + EPSILON:
                    return TEMPERATURE_OUT_OF_RANGE
        if (
            TARGET_TEMP_LOW in request
            and TARGET_TEMP_HIGH in request
            and request[TARGET_TEMP_LOW] > request[TARGET_TEMP_HIGH]
        ):
            return LOW_ABOVE_HIGH
        for setting in FAN_SWING_SETTINGS:
            if setting in request:
                _, options = self.sem.fan.shown(setting)
                if not options:
                    return SETTING_NOT_AVAILABLE
                if request[setting] not in options:
                    return INVALID_OPTION
        return None

    def shown_range(self) -> tuple[float, float]:
        """ENT-RANGE-2: the range of m in ON(m) / WAITING(m), the widest in OFF."""
        mode = self.stm.operating_mode()
        return self.cam.mode_range(mode) if mode else self.cam.widest_range()

    # --- Problems (spec §4.2, §4.3) ------------------------------------------------------

    def _judge_problems(self) -> list[Problem]:
        entry = self.entry
        delay = entry.monitoring_delay_timer
        problems: list[Problem] = []
        state = self.stm.state
        stored_mode = self.stored.mode
        unusable: list[str] = []
        if stored_mode != OFF and state != INIT:
            if state == WAITING:
                unusable = entry.sources_of(self.stm.mode)
            elif state == NO_SOURCE:
                unusable = entry.sources_of(stored_mode)
            elif state == STATE_ON and entry.is_bi(self.stm.mode) and self.mom.state == WAITING_PHASE:
                unusable = [self.active_source()]  # MON-SRC-1: only the source of the phase
        for source_id in unusable:
            if source_id and self.source_state(source_id).unusable:
                problems.append(
                    Problem(
                        SOURCE_UNUSABLE,
                        (source_id,),
                        SENSOR_SOURCES,
                        delay,
                        f"{source_id} is unusable",
                        {"source": source_id},
                    )
                )
        if state == INIT:
            return problems
        gap = entry.monitoring_gap
        sensor = self.sensor_temperature()
        if entry.temperature_sensor and sensor is None:
            problems.append(
                Problem(
                    SENSOR_WITHOUT_VALUE,
                    (entry.temperature_sensor,),
                    SENSOR_TEMPERATURES,
                    delay,
                    f"{entry.temperature_sensor} has no valid value",
                    {"sensor": entry.temperature_sensor},
                )
            )
        readings = [
            (source_id, value)
            for source_id in self.sources
            if (value := reference.reading(self, source_id)) is not None
        ]
        if sensor is not None:
            for source_id, value in readings:
                if abs(sensor - value) > gap:
                    problems.append(
                        Problem(
                            GAP_SENSOR_SOURCE,
                            (source_id,),
                            SENSOR_TEMPERATURES,
                            delay,
                            f"{entry.temperature_sensor} ({sensor}) and {source_id} ({value}) "
                            f"differ by more than {gap}",
                            {
                                "sensor": entry.temperature_sensor,
                                "source": source_id,
                                "temperatures": [sensor, value],
                                "gap": round(abs(sensor - value), 2),
                            },
                        )
                    )
        for (first, a), (second, b) in combinations(readings, 2):
            if abs(a - b) > gap:
                problems.append(
                    Problem(
                        GAP_SOURCES,
                        (first, second),
                        SENSOR_TEMPERATURES,
                        delay,
                        f"{first} ({a}) and {second} ({b}) differ by more than {gap}",
                        {
                            "sources": [first, second],
                            "temperatures": [a, b],
                            "gap": round(abs(a - b), 2),
                        },
                    )
                )
        return problems

    # --- Repairs issues (ENT-HVAC-5, ENT-FAN-7, ENT-FAN-8) ----------------------------------

    def _set_issues(self, group: str, wanted: dict[str, tuple[str, dict[str, str]]]) -> None:
        raised = self._issues.setdefault(group, {})
        for issue_id in list(raised):
            if issue_id not in wanted:
                del raised[issue_id]
                self.repairs.clear_issue(issue_id)
        for issue_id, (key, placeholders) in wanted.items():
            if raised.get(issue_id) != (key, placeholders):
                raised[issue_id] = (key, placeholders)
                self.repairs.raise_issue(issue_id, key, placeholders)
                self.notify.log("warning", f"Repairs issue {key}: {placeholders}")

    def _check_mode_issues(self) -> None:
        """ENT-HVAC-5: a source that does not offer a mode it serves; never seen: not judged."""
        wanted: dict[str, tuple[str, dict[str, str]]] = {}
        for source in self.sources.values():
            offered = source.capabilities.hvac_modes
            if offered is None:
                continue
            for mode in sorted(source.cfg.served_source_modes - set(offered)):
                wanted[f"{self.entry.entry_id}_{mode}_not_supported"] = (
                    "mode_not_supported",
                    {"name": self.entry.name, "entity_id": source.cfg.entity_id, "mode": mode},
                )
        self._set_issues("modes", wanted)

    def check_sync_issues(self) -> None:
        """ENT-FAN-7, ENT-FAN-8: configuration errors of sync_modes and bi_source_sync."""
        entry = self.entry
        fan = self.sem.fan
        wanted: dict[str, tuple[str, dict[str, str]]] = {}
        if HEAT_COOL in entry.sync_modes and entry.bi_source:
            wanted[f"{entry.entry_id}_sync_heat_cool_bi_source"] = (
                "sync_heat_cool_bi_source",
                {"name": entry.name},
            )
        groups: list[tuple[str, list[tuple[str, str, str]]]] = [
            ("sync", [(m, *c) for m in fan.sync_modes() if (c := self.cam.mode_context(m))])
        ]
        if entry.bi_source and entry.bi_source_sync:
            groups.append(("bi_source", [(p, *self.cam.phase_context(p)) for p in PHASES]))
        for group, members in groups:
            for setting in FAN_SWING_SETTINGS:
                discovered = [
                    (label, self.cam.options(source_id, mode, setting))
                    for label, source_id, mode in members
                    if self.cam.caps(source_id, mode) is not None
                ]
                if not any(options is not None for _, options in discovered):
                    continue
                for label, options in discovered:
                    if options is None:
                        wanted[f"{entry.entry_id}_{group}_{label}_{setting}"] = (
                            "sync_setting_missing",
                            {"name": entry.name, "mode": label, "setting": setting},
                        )
        self._set_issues("sync", wanted)

    # --- View (ARCHITECTURE ARCH-8, spec §2.2) ----------------------------------------------

    def view(self) -> ClimateView:
        """What the climate entity shows now."""
        entry = self.entry
        state = self.stm.state
        view = ClimateView(hvac_modes=[OFF, *entry.modes])
        view.step = self.cam.step()
        view.features = self.cam.features()
        view.min_temp, view.max_temp = self.shown_range()
        view.attributes = {
            "active_entity_id": None,
            "phase": None,
            "mode_entity_ids": {
                m: entry.mode_sources[m] for m in entry.modes if not entry.is_bi(m)
            },
            "unavailable_modes": [m for m in entry.modes if not self.mode_available(m)],
            "foreign_modes": {
                source_id: source.state.mode
                for source_id, source in self.sources.items()
                if source.state.state == "ON"
                and source.state.mode not in source.cfg.served_source_modes
            },
            "saved_targets": {
                "low": self.stored.targets[LOW],
                "high": self.stored.targets[HIGH],
                "single": self.stored.targets[SINGLE],
            },
            "saved_settings": {k: dict(v) for k, v in self.stored.memory.items()},
            "target_gaps": [],
        }
        if state in (INIT, NO_SOURCE):
            return view
        view.available = True
        view.current_temperature = reference.reference(self)
        mode = self.stm.operating_mode()
        if state == STATE_OFF:
            view.hvac_mode = OFF
            view.hvac_action = OFF
        elif state == STATE_ON:
            view.hvac_mode = mode
            active = self.active_source()
            view.hvac_action = self.sources[active].action if active else None
        view.attributes["active_entity_id"] = self.active_source()
        if entry.is_bi(mode):
            view.attributes["phase"] = self.mom.phase
        shown, gaps = targets.shown(self)
        view.temperature = shown[TEMPERATURE]
        view.target_temp_low = shown[TARGET_TEMP_LOW]
        view.target_temp_high = shown[TARGET_TEMP_HIGH]
        view.attributes["target_gaps"] = gaps
        for setting in FAN_SWING_SETTINGS:
            value, options = self.sem.fan.shown(setting)
            view.values[setting] = value
            view.options[setting] = options
        return view
