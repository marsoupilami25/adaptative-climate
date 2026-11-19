"""Options flow (UI): saves the whole configuration at once (CFG-YAML-4)."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlowResult, OptionsFlow

from ..options.checks import check_config
from ..options.schema import CONF_NAME, flatten, form_schema


class AdaptativeClimateOptionsFlow(OptionsFlow):
    """The options replace the whole configuration of the entry; it is then reloaded."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The same form as the config flow, without the name."""
        entry = self.config_entry
        unit = self.hass.config.units.temperature_unit
        errors: dict[str, str] = {}
        placeholders = {"detail": ""}
        values: dict[str, Any] = dict(entry.data)
        if user_input is not None:
            values = flatten(user_input)
            values[CONF_NAME] = entry.data[CONF_NAME]
            problems = check_config(self.hass, values, entry.entry_id)
            if not problems:
                # The update listener reloads the entry (ENT-INIT-4)
                self.hass.config_entries.async_update_entry(entry, data=values)
                return self.async_create_entry(data={})
            errors["base"], placeholders["detail"] = problems[0]
        return self.async_show_form(
            step_id="init",
            data_schema=form_schema(unit, values, with_name=False),
            errors=errors,
            description_placeholders=placeholders,
        )
