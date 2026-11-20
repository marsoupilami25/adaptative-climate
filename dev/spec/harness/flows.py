"""A user filling the forms of a config flow or an options flow.

The driver knows the names of the options (spec §3.1), not the steps nor the
sections of the forms: it fills each form shown with the options given, as a
user would, and submits it until the flow ends or shows an error.

- A field named after an option given gets its value; `None` clears it.
- A field not given keeps what the form shows (its suggested value), or is
  left empty.
- A value the form itself rejects (type, range of a field) is a refusal too:
  the result is then `{"type": "invalid_data", "errors": {...}}`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResultType, InvalidData, section

#: The result of a form whose values the form itself rejects.
INVALID_DATA = "invalid_data"


def _key_name(key: Any) -> str:
    return str(key.schema) if isinstance(key, vol.Marker) else str(key)


def _shown(key: Any) -> Any:
    """What the form shows in a field: its suggested value, else nothing."""
    description = getattr(key, "description", None) or {}
    return description.get("suggested_value")


def fill_form(schema: vol.Schema, options: Mapping[str, Any]) -> dict[str, Any]:
    """The answer of a user to a form, with the options given."""
    answer: dict[str, Any] = {}
    for key, validator in schema.schema.items():
        name = _key_name(key)
        if isinstance(validator, section):
            answer[name] = fill_form(validator.schema, options)
            continue
        if name in options:
            if options[name] is not None:
                answer[name] = options[name]
            continue
        shown = _shown(key)
        if shown is not None:
            answer[name] = shown
    return answer


def field_names(schema: vol.Schema) -> set[str]:
    """The names of the fields of a form, sections opened."""
    names: set[str] = set()
    for key, validator in schema.schema.items():
        if isinstance(validator, section):
            names |= field_names(validator.schema)
        else:
            names.add(_key_name(key))
    return names


async def drive(flow_manager: Any, result: Mapping[str, Any], options: Mapping[str, Any]) -> Any:
    """Answer each form with the options, until the flow ends or shows an error."""
    seen: set[str] = set()
    answered = False
    while result["type"] == FlowResultType.FORM:
        if answered and result.get("errors"):
            return result
        schema = result["data_schema"]
        seen |= field_names(schema)
        try:
            result = await flow_manager.async_configure(
                result["flow_id"], fill_form(schema, options)
            )
        except InvalidData as err:
            return {"type": INVALID_DATA, "errors": dict(err.schema_errors)}
        answered = True
    missing = set(options) - seen
    assert not missing, f"no field of the forms names {sorted(missing)}"
    return result
