"""The source actor: its four functions, its data @S, its problems (spec §1.2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..model.entry_config import EntryConfig, SourceConfig
from ..model.events import M_DOWN, M_UP, SE_SNAPSHOT_EVENTS, Event
from ..model.ports import NotifyPort, SourceEntityPort, StorePort, TimerPort
from ..model.problems import (
    SENSOR_SOURCES,
    SETTING_NOT_APPLIED,
    SETTING_NOT_APPLIED_MIN_DELAY,
    SOURCE_NOT_DISCOVERED,
    SOURCE_OUT_OF_SYNC,
    Problem,
    ProblemTracker,
)
from ..model.values import ModeCaps, Snapshot, as_number, is_usable
from ..runtime.actor import Actor
from .confirmation import ModeRequestConfirmation
from .settings import SettingRequestManagement, shown_settings
from .state import STATE_OFF, STATE_ON, UNDISCOVERED, UNUSABLE, StateManagement
from .storage import SourceData, StorageManagement, restore_data

MONITORING = "monitoring"


@dataclass(frozen=True)
class SourceState:
    """state@S: UNDISCOVERED, OFF, ON(m) or UNUSABLE, with its stored state."""

    state: str
    mode: str | None
    stored: str  # off or m: the state it goes back to from UNUSABLE

    @property
    def available(self) -> bool:
        """In OFF or ON(x) (spec §0)."""
        return self.state in (STATE_OFF, STATE_ON)

    @property
    def undiscovered(self) -> bool:
        """In UNDISCOVERED (or not started yet)."""
        return self.state not in (STATE_OFF, STATE_ON, UNUSABLE)

    @property
    def unusable(self) -> bool:
        """In UNUSABLE."""
        return self.state == UNUSABLE

    def runs(self, mode: str) -> bool:
        """Runs `mode`: ON(mode), or its stored state when UNUSABLE (ENT-WANT-1)."""
        if self.state == STATE_ON:
            return self.mode == mode
        if self.state == UNUSABLE:
            return self.stored == mode
        return False


class Source(Actor):
    """One source per source entity, local to its entry (spec §0)."""

    def __init__(
        self,
        cfg: SourceConfig,
        entry: EntryConfig,
        port: SourceEntityPort,
        timer_port: TimerPort,
        store: StorePort,
        notify: NotifyPort,
    ) -> None:
        super().__init__(cfg.entity_id, timer_port)
        self.cfg = cfg
        self.entry = entry
        self.port = port
        self.notify = notify
        self._store = store
        self.data, self.has_stored_state = restore_data(store.load(self.part))
        self.snapshot: Snapshot | None = None
        self.prev_snapshot: Snapshot | None = None
        self.dsm = StorageManagement(self)
        self.stm = StateManagement(self)
        self.mrc = ModeRequestConfirmation(self)
        self.srm = SettingRequestManagement(self)
        # Sdsm first (EXEC-1, ARCHITECTURE §4.1)
        self.functions = [self.dsm, self.stm, self.mrc, self.srm]
        self._problems = ProblemTracker()

    @property
    def part(self) -> str:
        """Part of the store of this source (ARCHITECTURE §7)."""
        return f"source:{self.cfg.entity_id}"

    # --- Frame -----------------------------------------------------------------

    def before_step(self, event: Event) -> None:
        """A change of the source entity carries its snapshot: keep the last one."""
        if event.kind in SE_SNAPSHOT_EVENTS:
            self.prev_snapshot = self.snapshot
            self.snapshot = event.value

    def end_of_step(self) -> None:
        """Hook: tell the monitoring the problems that began or ended (MON-SEND-1)."""
        ups, downs = self._problems.diff(self._judge_problems())
        for problem in ups:
            self.send(MONITORING, Event(M_UP, self.actor_id, problem))
        for problem in downs:
            self.send(MONITORING, Event(M_DOWN, self.actor_id, problem))

    def save(self) -> None:
        """`save`: write the stored data (ARCH-9)."""
        self.has_stored_state = True
        self._store.save(self.part, self.data.to_dict())

    def send_ac(self, kind: str, value: Any = None) -> None:
        """Send an event S=>AC_*."""
        self.send("AC", Event(kind, self.actor_id, value))

    # --- Helpers of the functions -----------------------------------------------

    def served_offered(self) -> bool:
        """Every served source mode is in the stored hvac_modes (§1.2.3.5)."""
        modes = self.data.hvac_modes or []
        return all(mode in modes for mode in self.cfg.served_source_modes)

    def current_caps(self) -> ModeCaps | None:
        """Capabilities of the mode of ON(m)."""
        mode = self.stm.mode if self.stm.state == STATE_ON else None
        return self.data.caps(mode) if mode else None

    def temp_step(self) -> float:
        """Temperature step of the source in its mode, for comparisons (SRC-SET-4)."""
        caps = self.current_caps()
        if caps is not None and caps.target_temp_step:
            return caps.target_temp_step
        return self.entry.default_step

    # --- Data @S (spec §1.1.2) ----------------------------------------------------

    @property
    def state(self) -> SourceState:
        """state@S."""
        return SourceState(self.stm.state, self.stm.mode, self.data.state)

    @property
    def capabilities(self) -> SourceData:
        """capabilities@S: the stored capabilities, whatever the state (read only)."""
        return self.data

    @property
    def temperature(self) -> float | None:
        """temperature@S, as read; None when UNDISCOVERED or UNUSABLE."""
        if not self.stm.operating or not is_usable(self.snapshot):
            return None
        return as_number(self.snapshot.get("current_temperature"))

    @property
    def action(self) -> str | None:
        """action@S; None when UNDISCOVERED or UNUSABLE."""
        if not self.stm.operating or not is_usable(self.snapshot):
            return None
        action = self.snapshot.get("hvac_action")
        return str(action) if action is not None else None

    @property
    def settings(self) -> dict[str, Any]:
        """settings@S, as read; empty when UNDISCOVERED or UNUSABLE."""
        if not self.stm.operating:
            return {}
        return shown_settings(self.snapshot)

    # --- Problems (spec §4.2) -----------------------------------------------------

    def _judge_problems(self) -> list[Problem]:
        entry = self.entry
        delay = entry.monitoring_delay_timer
        entity_id = self.cfg.entity_id
        problems: list[Problem] = []
        if self.stm.state == UNDISCOVERED:
            problems.append(
                Problem(
                    SOURCE_NOT_DISCOVERED,
                    (entity_id,),
                    SENSOR_SOURCES,
                    delay,
                    f"{entity_id} was never seen usable",
                    {"source": entity_id},
                )
            )
        if self.mrc.running and self.mrc.out_of_sync:
            problems.append(
                Problem(
                    SOURCE_OUT_OF_SYNC,
                    (entity_id,),
                    SENSOR_SOURCES,
                    delay,
                    f"{entity_id} does not show {self.mrc.request}",
                    {"source": entity_id, "requested": self.mrc.request},
                )
            )
        for name in self.srm.not_applied():
            problems.append(
                Problem(
                    SETTING_NOT_APPLIED,
                    (entity_id, name),
                    SENSOR_SOURCES,
                    max(delay, SETTING_NOT_APPLIED_MIN_DELAY),
                    f"{entity_id} does not apply {name} {self.data.kept.get(name)}",
                    {
                        "source": entity_id,
                        "setting": name,
                        "sent": self.data.kept.get(name),
                        "shown": shown_settings(self.snapshot).get(name),
                    },
                )
            )
        return problems
