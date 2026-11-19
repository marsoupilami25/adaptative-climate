"""Options of spec §3.1: types, ranges, defaults (in the unit of Home Assistant, CFG-UNIT-1)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.const import UnitOfTemperature
from homeassistant.data_entry_flow import section
from homeassistant.helpers import config_validation as cv, selector

from ...core.model.values import MODES

CONF_NAME = "name"
CONF_TEMPERATURE_SENSOR = "temperature_sensor"
CONF_PHASE_HYSTERESIS = "phase_hysteresis"
CONF_REMOVAL_CONFIRMATION_TIMER = "removal_confirmation_timer"
CONF_REQUEST_CONFIRMATION_TIMER = "request_confirmation_timer"
CONF_SETTLE_TIMER = "settle_timer"
CONF_EXTERNAL_SENSOR_RESEND_TIMER = "external_sensor_resend_timer"
CONF_REQUEST_RETRY_TIMER = "request_retry_timer"
CONF_MONITORING_GAP = "monitoring_gap"
CONF_MONITORING_DELAY_TIMER = "monitoring_delay_timer"
CONF_MIN_TEMP = "min_temp"
CONF_MAX_TEMP = "max_temp"
CONF_MIN_GAP = "min_gap"
CONF_SYNC_MODES = "sync_modes"
CONF_BI_SOURCE_SYNC = "bi_source_sync"


def entity_key(mode: str) -> str:
    """`<mode>_entity`."""
    return f"{mode}_entity"


def offset_key(mode: str) -> str:
    """`<mode>_offset`."""
    return f"{mode}_offset"


def external_key(mode: str) -> str:
    """`<mode>_external_sensor`."""
    return f"{mode}_external_sensor"


ENTITY_KEYS = tuple(entity_key(m) for m in MODES)
OFFSET_KEYS = tuple(offset_key(m) for m in MODES)
EXTERNAL_KEYS = tuple(external_key(m) for m in MODES)

TIMER_KEYS = (
    CONF_REMOVAL_CONFIRMATION_TIMER,
    CONF_REQUEST_CONFIRMATION_TIMER,
    CONF_SETTLE_TIMER,
    CONF_EXTERNAL_SENSOR_RESEND_TIMER,
    CONF_REQUEST_RETRY_TIMER,
)

#: Durations in seconds: default, minimum, minimum excluded (§3.1.4, §3.1.5).
TIMERS: dict[str, tuple[float, float, bool]] = {
    CONF_REMOVAL_CONFIRMATION_TIMER: (60, 0, False),
    CONF_REQUEST_CONFIRMATION_TIMER: (30, 0, True),
    CONF_SETTLE_TIMER: (12, 0, True),
    CONF_EXTERNAL_SENSOR_RESEND_TIMER: (900, 0, True),
    CONF_REQUEST_RETRY_TIMER: (300, 0, True),
    CONF_MONITORING_DELAY_TIMER: (900, 0, False),
}

#: Temperature gaps, (°C, °F): default, minimum, minimum excluded, maximum.
GAPS: dict[str, tuple[tuple[float, float], tuple[float, float] | None, bool]] = {
    CONF_PHASE_HYSTERESIS: ((1, 2), (0, 0), False),
    CONF_MONITORING_GAP: ((2, 4), (0, 0), True),
    CONF_MIN_GAP: ((1, 2), (1, 2), False),
}
OFFSET_LIMIT = (10, 18)

SECTIONS: dict[str, tuple[str, ...]] = {
    "modes": ENTITY_KEYS,
    "readings": (CONF_TEMPERATURE_SENSOR, *OFFSET_KEYS, *EXTERNAL_KEYS, CONF_PHASE_HYSTERESIS),
    "timers": TIMER_KEYS,
    "monitoring": (CONF_MONITORING_GAP, CONF_MONITORING_DELAY_TIMER),
    "limits": (CONF_MIN_TEMP, CONF_MAX_TEMP, CONF_MIN_GAP),
    "fan_swing": (CONF_SYNC_MODES, CONF_BI_SOURCE_SYNC),
}


def unit_index(unit: str) -> int:
    """0 for °C, 1 for °F."""
    return 1 if unit == UnitOfTemperature.FAHRENHEIT else 0


def defaults(unit: str) -> dict[str, Any]:
    """Default value of each option with one."""
    index = unit_index(unit)
    result: dict[str, Any] = {key: 0.0 for key in OFFSET_KEYS}
    result.update({key: float(value[0]) for key, value in TIMERS.items()})
    result.update({key: float(value[0][index]) for key, value in GAPS.items()})
    result[CONF_SYNC_MODES] = []
    result[CONF_BI_SOURCE_SYNC] = False
    return result


# --- YAML (§3.2) -------------------------------------------------------------------

YAML_ENTRY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        **{vol.Optional(key): cv.entity_domain("climate") for key in ENTITY_KEYS},
        vol.Optional(CONF_TEMPERATURE_SENSOR): cv.entity_domain("sensor"),
        **{vol.Optional(key): vol.Coerce(float) for key in OFFSET_KEYS},
        **{
            vol.Optional(key): cv.entity_domain(["number", "input_number"])
            for key in EXTERNAL_KEYS
        },
        **{vol.Optional(key): vol.Coerce(float) for key in (*GAPS, *TIMERS)},
        vol.Optional(CONF_MIN_TEMP): vol.Coerce(float),
        vol.Optional(CONF_MAX_TEMP): vol.Coerce(float),
        vol.Optional(CONF_SYNC_MODES): vol.All(cv.ensure_list, [vol.In(MODES)]),
        vol.Optional(CONF_BI_SOURCE_SYNC): cv.boolean,
    }
)


# --- UI forms (config flow, options flow) ----------------------------------------------


def _number(unit: str | None, minimum: float, maximum: float, step: float) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            unit_of_measurement=unit,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _field(key: str, values: Mapping[str, Any], default: Any = None) -> vol.Optional:
    """An optional field, prefilled with the current value (it can be cleared)."""
    current = values.get(key, default)
    if current is None:
        return vol.Optional(key)
    return vol.Optional(key, description={"suggested_value": current})


def form_schema(unit: str, values: Mapping[str, Any], with_name: bool) -> vol.Schema:
    """The form of the configuration, by sections."""
    index = unit_index(unit)
    limit = OFFSET_LIMIT[index]
    temp_step = 0.1 if index == 0 else 0.5
    base = defaults(unit)
    climate = selector.EntitySelector(selector.EntitySelectorConfig(domain="climate"))
    external = selector.EntitySelector(
        selector.EntitySelectorConfig(domain=["number", "input_number"])
    )
    sensor = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
    seconds = _number("s", 0, 86400, 1)

    modes = {_field(key, values): climate for key in ENTITY_KEYS}
    readings: dict[Any, Any] = {_field(CONF_TEMPERATURE_SENSOR, values): sensor}
    readings.update(
        {
            _field(key, values, base[key]): _number(unit, -limit, limit, temp_step)
            for key in OFFSET_KEYS
        }
    )
    readings.update({_field(key, values): external for key in EXTERNAL_KEYS})
    readings[_field(CONF_PHASE_HYSTERESIS, values, base[CONF_PHASE_HYSTERESIS])] = _number(
        unit, 0, 2 * limit, temp_step
    )
    timers = {_field(key, values, base[key]): seconds for key in TIMER_KEYS}
    monitoring = {
        _field(CONF_MONITORING_GAP, values, base[CONF_MONITORING_GAP]): _number(
            unit, 0, 2 * limit, temp_step
        ),
        _field(CONF_MONITORING_DELAY_TIMER, values, base[CONF_MONITORING_DELAY_TIMER]): seconds,
    }
    limits = {
        _field(CONF_MIN_TEMP, values): _number(unit, -100, 200, temp_step),
        _field(CONF_MAX_TEMP, values): _number(unit, -100, 200, temp_step),
        _field(CONF_MIN_GAP, values, base[CONF_MIN_GAP]): _number(unit, 0, 2 * limit, temp_step),
    }
    fan_swing = {
        _field(CONF_SYNC_MODES, values, []): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(MODES),
                multiple=True,
                translation_key=CONF_SYNC_MODES,
            )
        ),
        _field(CONF_BI_SOURCE_SYNC, values, False): selector.BooleanSelector(),
    }
    schema: dict[Any, Any] = {}
    if with_name:
        schema[vol.Required(CONF_NAME, default=values.get(CONF_NAME, vol.UNDEFINED))] = (
            selector.TextSelector()
        )
    for name, fields in (
        ("modes", modes),
        ("readings", readings),
        ("timers", timers),
        ("monitoring", monitoring),
        ("limits", limits),
        ("fan_swing", fan_swing),
    ):
        schema[vol.Required(name)] = section(vol.Schema(fields), {"collapsed": name != "modes"})
    return vol.Schema(schema)


def flatten(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """The values of the form, without sections nor empty values."""
    result: dict[str, Any] = {}
    for key, value in user_input.items():
        if key in SECTIONS and isinstance(value, Mapping):
            result.update(value)
        else:
            result[key] = value
    return {k: v for k, v in result.items() if v is not None and v != ""}
