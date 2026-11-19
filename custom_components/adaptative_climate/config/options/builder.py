"""Builds the configuration model and its fingerprint (ARCHITECTURE ARCH-10, §8, §9)."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from typing import Any

from homeassistant.const import UnitOfTemperature
from homeassistant.util.unit_conversion import TemperatureConverter

from ...core.model.entry_config import EntryConfig, SourceConfig
from ...core.model.values import COOL, HEAT, HEAT_COOL, MODE_ORDER, MODES
from .schema import (
    CONF_BI_SOURCE_SYNC,
    CONF_EXTERNAL_SENSOR_RESEND_TIMER,
    CONF_MAX_TEMP,
    CONF_MIN_GAP,
    CONF_MIN_TEMP,
    CONF_MONITORING_DELAY_TIMER,
    CONF_MONITORING_GAP,
    CONF_NAME,
    CONF_PHASE_HYSTERESIS,
    CONF_REMOVAL_CONFIRMATION_TIMER,
    CONF_REQUEST_CONFIRMATION_TIMER,
    CONF_REQUEST_RETRY_TIMER,
    CONF_SETTLE_TIMER,
    CONF_SYNC_MODES,
    CONF_TEMPERATURE_SENSOR,
    defaults,
    entity_key,
    external_key,
    offset_key,
)


def normalize(data: Mapping[str, Any], unit: str) -> dict[str, Any]:
    """Every option, with its default when not given."""
    result = defaults(unit)
    result.update({k: v for k, v in data.items() if v is not None})
    return result


def mode_sources(data: Mapping[str, Any]) -> dict[str, str]:
    """The source entity of each mode with one of its own (CFG-MODE-1)."""
    return {m: data[entity_key(m)] for m in MODES if data.get(entity_key(m))}


def is_bi_source(data: Mapping[str, Any]) -> bool:
    """heat_entity and cool_entity, without heat_cool_entity (CFG-MODE-3)."""
    sources = mode_sources(data)
    return HEAT in sources and COOL in sources and HEAT_COOL not in sources


def configured_modes(data: Mapping[str, Any]) -> list[str]:
    """Configured modes, in mode order (ENT-HVAC-1)."""
    sources = mode_sources(data)
    modes = set(sources)
    if is_bi_source(data):
        modes.add(HEAT_COOL)
    return sorted(modes, key=MODE_ORDER.index)


def served_modes(data: Mapping[str, Any]) -> dict[str, list[str]]:
    """Source entity -> the modes it is configured for (`<mode>_entity`), in mode order."""
    result: dict[str, list[str]] = {}
    for mode, entity_id in mode_sources(data).items():
        result.setdefault(entity_id, []).append(mode)
    return result


def source_options(data: Mapping[str, Any], unit: str) -> dict[str, tuple[str | None, float]]:
    """Source entity -> (external sensor, offset) (CFG-SENS-2, CFG-SENS-4)."""
    values = normalize(data, unit)
    result = {}
    for entity_id, modes in served_modes(data).items():
        mode = modes[0]
        external = values.get(external_key(mode)) or None
        offset = 0.0 if external else float(values.get(offset_key(mode), 0.0))
        result[entity_id] = (external, offset)
    return result


def fingerprint(data: Mapping[str, Any]) -> str:
    """A digest of the configuration of the entry."""
    text = json.dumps(dict(data), sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def build(entry_id: str, data: Mapping[str, Any], unit: str) -> EntryConfig:
    """The immutable model given to the core."""
    values = normalize(data, unit)
    sources_of = mode_sources(values)
    bi_source = is_bi_source(values)
    options = source_options(values, unit)
    sources = []
    for entity_id, modes in served_modes(values).items():
        external, offset = options[entity_id]
        sources.append(
            SourceConfig(
                entity_id=entity_id,
                modes=tuple(modes),
                served_source_modes=frozenset(modes),
                offset=offset,
                external_sensor=external,
            )
        )
    sources.sort(key=lambda s: s.first_mode_index)
    externals: list[str] = []
    for source in sources:
        if source.external_sensor and source.external_sensor not in externals:
            externals.append(source.external_sensor)
    if unit == UnitOfTemperature.FAHRENHEIT:
        default_min = round(TemperatureConverter.convert(7, UnitOfTemperature.CELSIUS, unit), 1)
        default_max = round(TemperatureConverter.convert(35, UnitOfTemperature.CELSIUS, unit), 1)
        default_step = 1.0
    else:
        default_min, default_max, default_step = 7.0, 35.0, 0.5
    sensor = values.get(CONF_TEMPERATURE_SENSOR)
    return EntryConfig(
        entry_id=entry_id,
        name=values[CONF_NAME],
        unit=unit,
        modes=tuple(configured_modes(values)),
        mode_sources=sources_of,
        bi_source=bi_source,
        sources=tuple(sources),
        temperature_sensor=sensor or None,
        external_sensors=tuple(externals) if sensor else (),
        phase_hysteresis=float(values[CONF_PHASE_HYSTERESIS]),
        removal_confirmation_timer=float(values[CONF_REMOVAL_CONFIRMATION_TIMER]),
        request_confirmation_timer=float(values[CONF_REQUEST_CONFIRMATION_TIMER]),
        settle_timer=float(values[CONF_SETTLE_TIMER]),
        external_sensor_resend_timer=float(values[CONF_EXTERNAL_SENSOR_RESEND_TIMER]),
        request_retry_timer=float(values[CONF_REQUEST_RETRY_TIMER]),
        monitoring_gap=float(values[CONF_MONITORING_GAP]),
        monitoring_delay_timer=float(values[CONF_MONITORING_DELAY_TIMER]),
        min_temp=_optional_float(values.get(CONF_MIN_TEMP)),
        max_temp=_optional_float(values.get(CONF_MAX_TEMP)),
        min_gap=float(values[CONF_MIN_GAP]),
        sync_modes=tuple(values.get(CONF_SYNC_MODES) or ()),
        bi_source_sync=bool(values.get(CONF_BI_SOURCE_SYNC)),
        default_min_temp=default_min,
        default_max_temp=default_max,
        default_step=default_step,
        fingerprint=fingerprint(data),
    )


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
