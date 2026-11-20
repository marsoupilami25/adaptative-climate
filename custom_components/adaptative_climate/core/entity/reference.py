"""Reference temperature (spec §1.3.5.1) and local temperatures (§1.3.3.2.2).

Computed from the data (`temperature@T`, `temperature@S`), read at each
computation (ENT-REF-7).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..model.values import COOL, HEAT, clean

if TYPE_CHECKING:
    from .entity import ACEntity


def reading(entity: ACEntity, source_id: str) -> float | None:
    """Reading of a source: temperature@S minus its offset (ENT-REF-5)."""
    temperature = entity.sources[source_id].temperature
    if temperature is None:
        return None
    return clean(temperature - entity.entry.offset_of(source_id))


def sensor(entity: ACEntity) -> float | None:
    """temperature@T, None without temperature sensor or valid value (ENT-REF-1)."""
    return entity.sensor_temperature()


def _phase_readings(entity: ACEntity) -> list[float]:
    values = []
    sources = []
    for phase in (HEAT, COOL):
        source_id = entity.entry.phase_source(phase)
        if source_id not in sources:
            sources.append(source_id)
            value = reading(entity, source_id)
            if value is not None:
                values.append(value)
    return values


def reference(entity: ACEntity) -> float | None:
    """The reference temperature (ENT-REF-1 to ENT-REF-6)."""
    value = sensor(entity)
    if value is not None:
        return value
    entry = entity.entry
    mode = entity.stm.operating_mode()
    if mode is None:
        mode = entity.last_used_mode()
        if mode is None:
            # OFF, no mode ever used: the first available source, in mode order
            for each in entry.modes:
                for source_id in entry.sources_of(each):
                    if entity.source_state(source_id).available:
                        return reading(entity, source_id)
            # Safety net (not reached): with no source available, the entity is NO_SOURCE
            return None
    if entry.is_bi(mode):
        values = _phase_readings(entity)
        return clean(sum(values) / len(values)) if values else None
    source_id = entry.source_of(mode)
    return reading(entity, source_id) if source_id else None


def local_temperatures(entity: ACEntity) -> tuple[float | None, float | None]:
    """(local low, local high) temperatures of the bi-source mode (ENT-WANT-2)."""
    value = sensor(entity)
    if value is not None:
        return value, value
    values = _phase_readings(entity)
    if not values:
        return None, None
    return max(values), min(values)
