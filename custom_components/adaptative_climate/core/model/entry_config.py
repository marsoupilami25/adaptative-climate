"""Configuration model of an entry, immutable (ARCHITECTURE ARCH-10, §8, §9).

Built by `config/options/builder.py` from a checked configuration. It gives
the core what it derives from the configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .values import COOL, HEAT, HEAT_COOL, MODE_ORDER


@dataclass(frozen=True)
class SourceConfig:
    """One source per source entity (spec §0)."""

    entity_id: str
    #: Entity modes this source entity is configured for (`<mode>_entity`).
    modes: tuple[str, ...]
    #: Source modes it serves: its modes, and the phase of a bi-source heat_cool.
    served_source_modes: frozenset[str]
    offset: float = 0.0
    external_sensor: str | None = None

    @property
    def first_mode_index(self) -> int:
        """Mode order of the first mode it serves (ENT-TGT-10)."""
        indexes = [MODE_ORDER.index(m) for m in self.served_source_modes]
        return min(indexes) if indexes else len(MODE_ORDER)


@dataclass(frozen=True)
class EntryConfig:
    """What the core derives from the configuration of an entry."""

    entry_id: str
    name: str
    unit: str
    #: Configured modes in mode order, `off` excepted (ENT-HVAC-1).
    modes: tuple[str, ...]
    #: Source entity of each mode with a source of its own (`<mode>_entity`).
    mode_sources: dict[str, str]
    #: heat_cool is bi-source (CFG-MODE-3).
    bi_source: bool
    #: Sources in mode order of the first mode each one serves.
    sources: tuple[SourceConfig, ...]
    temperature_sensor: str | None = None
    #: External sensor entities, each one kept once (ENT-EXT-1).
    external_sensors: tuple[str, ...] = ()
    phase_hysteresis: float = 1.0
    removal_confirmation_timer: float = 60
    request_confirmation_timer: float = 30
    settle_timer: float = 12
    external_sensor_resend_timer: float = 900
    request_retry_timer: float = 300
    monitoring_gap: float = 2.0
    monitoring_delay_timer: float = 900
    min_temp: float | None = None
    max_temp: float | None = None
    min_gap: float = 1.0
    sync_modes: tuple[str, ...] = ()
    bi_source_sync: bool = False
    #: Home Assistant defaults, in the unit of Home Assistant (SRC-DATA-1, ENT-STEP-1).
    default_min_temp: float = 7.0
    default_max_temp: float = 35.0
    default_step: float = 0.5
    #: Digest of the configuration (ARCHITECTURE §8).
    fingerprint: str = ""
    source_by_id: dict[str, SourceConfig] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        """Index the sources by entity id."""
        self.source_by_id.update({s.entity_id: s for s in self.sources})

    # --- Modes and sources (spec §1.3.3.1) ------------------------------------

    def is_bi(self, mode: str | None) -> bool:
        """Whether the mode is the bi-source heat_cool."""
        return mode == HEAT_COOL and self.bi_source

    def source_of(self, mode: str) -> str | None:
        """Source entity of a mono-source mode; None for the bi-source heat_cool."""
        if self.is_bi(mode):
            return None
        return self.mode_sources.get(mode)

    def phase_source(self, phase: str) -> str:
        """Source of a phase of the bi-source heat_cool."""
        return self.mode_sources[phase]

    def sources_of(self, mode: str) -> list[str]:
        """The source of `m`; the two phase sources for a bi-source heat_cool."""
        if self.is_bi(mode):
            result = [self.mode_sources[HEAT]]
            if self.mode_sources[COOL] not in result:
                result.append(self.mode_sources[COOL])
            return result
        source = self.mode_sources.get(mode)
        return [source] if source else []

    def is_served(self, source_id: str, mode: str) -> bool:
        """A mode a source entity runs is served when it is the source of it (spec §0)."""
        return self.mode_sources.get(mode) == source_id and not self.is_bi(mode)

    def offset_of(self, source_id: str) -> float:
        """Offset of a source entity (CFG-SENS-1, CFG-SENS-4)."""
        source = self.source_by_id.get(source_id)
        return source.offset if source else 0.0
