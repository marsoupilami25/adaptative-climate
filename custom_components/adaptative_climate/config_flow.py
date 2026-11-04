"""Config flow for Adaptative Climate."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_TARGET_ENTITY,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DEFAULT_NAME,
    DOMAIN,
)

TEMPERATURE_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=0, max=40, step=0.5, mode=NumberSelectorMode.BOX),
)

TEMPERATURE_SCHEMA: dict[vol.Marker, Any] = {
    vol.Optional(CONF_MIN_TEMP, default=DEFAULT_MIN_TEMP): TEMPERATURE_SELECTOR,
    vol.Optional(CONF_MAX_TEMP, default=DEFAULT_MAX_TEMP): TEMPERATURE_SELECTOR,
}

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Required(CONF_TARGET_ENTITY): EntitySelector(
            EntitySelectorConfig(domain="climate"),
        ),
        **TEMPERATURE_SCHEMA,
    }
)

OPTIONS_SCHEMA = vol.Schema(TEMPERATURE_SCHEMA)


class AdaptativeClimateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an Adaptative Climate config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return AdaptativeClimateOptionsFlow()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_input(self.hass, user_input)
            if not errors:
                await self.async_set_unique_id(user_input[CONF_TARGET_ENTITY])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(CONFIG_SCHEMA, user_input),
            errors=errors,
        )


class AdaptativeClimateOptionsFlow(config_entries.OptionsFlow):
    """Handle Adaptative Climate options."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Manage integration options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_input(self.hass, user_input)
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        # Show what the user just typed after an error, otherwise the
        # current settings (options first, then initial setup values).
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, user_input or current
            ),
            errors=errors,
        )


def _validate_input(hass: HomeAssistant, user_input: dict[str, Any]) -> dict[str, str]:
    """Return form errors for user input (empty when valid)."""
    errors: dict[str, str] = {}

    target = user_input.get(CONF_TARGET_ENTITY)
    if target is not None:
        # Wrapping one of our own entities would make calls loop forever.
        registry_entry = er.async_get(hass).async_get(target)
        if registry_entry is not None and registry_entry.platform == DOMAIN:
            errors[CONF_TARGET_ENTITY] = "self_reference"

    min_temp = user_input.get(CONF_MIN_TEMP, DEFAULT_MIN_TEMP)
    max_temp = user_input.get(CONF_MAX_TEMP, DEFAULT_MAX_TEMP)
    if min_temp >= max_temp:
        errors["base"] = "min_max_invalid"

    return errors
