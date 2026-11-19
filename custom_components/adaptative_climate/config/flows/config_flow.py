"""Config flow (UI), and the import of the YAML entries (spec §3, CFG-YAML-5)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import (
    SOURCE_IMPORT,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from ...const import DOMAIN
from ..options.checks import check_config
from ..options.schema import CONF_NAME, flatten, form_schema
from .options_flow import AdaptativeClimateOptionsFlow

_LOGGER = logging.getLogger(__package__)


class AdaptativeClimateConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create an entry from the UI or from the YAML."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The whole configuration in one form, by sections."""
        unit = self.hass.config.units.temperature_unit
        errors: dict[str, str] = {}
        placeholders = {"detail": ""}
        values: dict[str, Any] = {}
        if user_input is not None:
            values = flatten(user_input)
            problems = check_config(self.hass, values, None)
            if not problems:
                return self.async_create_entry(title=values[CONF_NAME], data=values)
            errors["base"], placeholders["detail"] = problems[0]
        return self.async_show_form(
            step_id="user",
            data_schema=form_schema(unit, values, with_name=True),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """An entry of the YAML (CFG-YAML-1): checked as in the UI (CFG-YAML-5)."""
        data = dict(import_data)
        problems = check_config(self.hass, data, None)
        if problems:
            _LOGGER.error(
                "YAML entry %s is invalid, not imported: %s",
                data.get(CONF_NAME),
                "; ".join(f"{key} {detail}".strip() for key, detail in problems),
            )
            return self.async_abort(reason="invalid_yaml")
        return self.async_create_entry(title=data[CONF_NAME], data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """The options flow of an entry created from the UI."""
        return AdaptativeClimateOptionsFlow()

    @classmethod
    @callback
    def async_supports_options_flow(cls, config_entry: ConfigEntry) -> bool:
        """An imported entry has no options in the UI (CFG-YAML-3)."""
        return config_entry.source != SOURCE_IMPORT
