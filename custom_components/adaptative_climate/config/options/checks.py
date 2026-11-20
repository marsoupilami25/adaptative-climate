"""CFG-CHECK-1: one function judges a configuration for the UI and the YAML alike (CFG-YAML-5)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from ...const import DOMAIN
from ...core.model.values import MODES
from .builder import mode_sources, normalize, served_modes, source_options
from .schema import (
    CONF_MAX_TEMP,
    CONF_MIN_GAP,
    CONF_MIN_TEMP,
    CONF_NAME,
    CONF_REQUEST_CONFIRMATION_TIMER,
    CONF_REQUEST_RETRY_TIMER,
    CONF_TEMPERATURE_SENSOR,
    GAPS,
    OFFSET_KEYS,
    OFFSET_LIMIT,
    TIMERS,
    external_key,
    offset_key,
    unit_index,
)

TEMPERATURE_UNITS = (UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.KELVIN)

Error = tuple[str, str]  # (error key, detail)


def check_config(
    hass: HomeAssistant, data: Mapping[str, Any], entry_id: str | None
) -> list[Error]:
    """The errors of a configuration; empty when it is accepted."""
    unit = hass.config.units.temperature_unit
    values = normalize(data, unit)
    errors: list[Error] = []
    errors += _check_ranges(values, unit)
    errors += _check_name(hass, values, entry_id)
    errors += _check_modes(hass, values)
    errors += _check_sensors(hass, values, unit)
    errors += _check_other_entries(hass, values, entry_id, unit)
    if values[CONF_REQUEST_RETRY_TIMER] < values[CONF_REQUEST_CONFIRMATION_TIMER]:
        errors.append(("retry_below_confirmation", ""))  # CFG-TIMER-1
    low, high = values.get(CONF_MIN_TEMP), values.get(CONF_MAX_TEMP)
    if low is not None and high is not None and high - low < values[CONF_MIN_GAP]:
        errors.append(("limits_too_close", ""))  # CFG-LIM-1
    return errors


def _check_ranges(values: Mapping[str, Any], unit: str) -> list[Error]:
    """An option outside the type or the range its table gives (§3.1)."""
    errors: list[Error] = []
    index = unit_index(unit)
    for key in OFFSET_KEYS:
        if abs(float(values[key])) > OFFSET_LIMIT[index]:
            errors.append(("out_of_range", key))
    for key, (_, minimum, excluded) in TIMERS.items():
        value = float(values[key])
        if value < minimum or (excluded and value <= minimum):
            errors.append(("out_of_range", key))
    for key, (_, minimum, excluded) in GAPS.items():
        value = float(values[key])
        if minimum is not None:
            low = minimum[index]
            if value < low or (excluded and value <= low):
                errors.append(("out_of_range", key))
    return errors


def _check_name(hass: HomeAssistant, values: Mapping[str, Any], entry_id: str | None) -> list[Error]:
    """CFG-NAME-1: unique among all the entries of the integration."""
    name = str(values.get(CONF_NAME, "")).strip()
    if not name:
        # Safety net (not reached): the YAML schema and the form both require a name
        return [("name_missing", "")]
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id != entry_id and entry.title.casefold() == name.casefold():
            return [("name_used", name)]
    return []


def _check_modes(hass: HomeAssistant, values: Mapping[str, Any]) -> list[Error]:
    """CFG-MODE-2, CFG-MODE-4, CFG-MODE-5."""
    sources = mode_sources(values)
    if not sources:
        return [("no_mode", "")]
    errors: list[Error] = []
    registry = er.async_get(hass)
    for entity_id, modes in served_modes(values).items():
        entry = registry.async_get(entity_id)
        if entry is not None and entry.platform == DOMAIN:
            errors.append(("source_is_ac_entity", entity_id))
            continue
        state = hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            continue
        offered = state.attributes.get("hvac_modes")
        if not isinstance(offered, (list, tuple)):
            # Safety net (not reached): a climate entity always lists its modes
            continue
        offered = [str(m) for m in offered]
        missing = [m for m in modes if m not in offered]
        if missing:
            errors.append(("mode_not_offered", f"{entity_id}: {', '.join(missing)}"))
    return errors


def _check_sensors(hass: HomeAssistant, values: Mapping[str, Any], unit: str) -> list[Error]:
    """CFG-SENS-2, CFG-SENS-4, CFG-SENS-6."""
    errors: list[Error] = []
    sensor = values.get(CONF_TEMPERATURE_SENSOR)
    if sensor:
        state = hass.states.get(sensor)
        sensor_unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) if state else None
        if sensor_unit is not None and sensor_unit not in TEMPERATURE_UNITS:
            errors.append(("sensor_not_temperature", f"{sensor}: {sensor_unit}"))
    sources = mode_sources(values)
    for mode in MODES:
        if mode not in sources:
            continue  # CFG-SENS-3: no effect without a source entity of its own
        if values.get(external_key(mode)):
            if not sensor:
                errors.append(("external_without_sensor", mode))
            if float(values.get(offset_key(mode), 0)) != 0:
                errors.append(("external_with_offset", mode))
    for entity_id, modes in served_modes(values).items():
        externals = {values.get(external_key(m)) or None for m in modes}
        if len(externals) > 1:
            errors.append(("source_inconsistent", f"{entity_id}: {', '.join(modes)}"))
            continue
        if externals == {None}:
            offsets = {float(values.get(offset_key(m), 0)) for m in modes}
            if len(offsets) > 1:
                errors.append(("source_inconsistent", f"{entity_id}: {', '.join(modes)}"))
    return errors


def _check_other_entries(
    hass: HomeAssistant, values: Mapping[str, Any], entry_id: str | None, unit: str
) -> list[Error]:
    """CFG-SENS-5: a source entity in several entries has the same options."""
    errors: list[Error] = []
    mine = source_options(values, unit)
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id == entry_id:
            continue
        theirs = source_options(entry.data, unit)
        their_modes = served_modes(entry.data)
        for entity_id, (external, offset) in mine.items():
            if entity_id not in theirs:
                continue
            other_external, other_offset = theirs[entity_id]
            if external != other_external or (external is None and offset != other_offset):
                errors.append(
                    (
                        "source_inconsistent_entries",
                        f"{entity_id}: {entry.title} ({', '.join(their_modes[entity_id])})",
                    )
                )
    return errors

