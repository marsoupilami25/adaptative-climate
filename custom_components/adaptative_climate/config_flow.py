"""Config flow for Adaptative Climate."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.climate import ATTR_HVAC_MODES
from homeassistant.const import CONF_NAME, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_MAX_TEMP,
    CONF_MIN_GAP,
    CONF_MIN_TEMP,
    CONF_SYNC_MODES,
    CONF_TEMPERATURE_SENSOR,
    DEFAULT_NAME,
    DOMAIN,
    MIN_GAP,
    MODE_SOURCE_KEYS,
    entry_settings,
)

_LOGGER = logging.getLogger(__name__)

TEMPERATURE_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=0, max=40, step=0.5, mode=NumberSelectorMode.BOX),
)

GAP_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=MIN_GAP, max=10, step=0.5, mode=NumberSelectorMode.BOX),
)

CLIMATE_SELECTOR = EntitySelector(EntitySelectorConfig(domain="climate"))

# One optional source per mode. A mode without a source is not shown.
SOURCES_SCHEMA: dict[vol.Marker, Any] = {
    vol.Optional(key): CLIMATE_SELECTOR for key in MODE_SOURCE_KEYS.values()
}

# Optional room temperature sensor, used by the combined heat_cool mode.
SENSOR_SCHEMA: dict[vol.Marker, Any] = {
    vol.Optional(CONF_TEMPERATURE_SENSOR): EntitySelector(
        EntitySelectorConfig(domain="sensor", device_class="temperature")
    ),
}

# Optional limits, empty by default: the range then follows the sources.
TEMPERATURE_SCHEMA: dict[vol.Marker, Any] = {
    vol.Optional(CONF_MIN_TEMP): TEMPERATURE_SELECTOR,
    vol.Optional(CONF_MAX_TEMP): TEMPERATURE_SELECTOR,
    vol.Optional(CONF_MIN_GAP): GAP_SELECTOR,
}

# Modes sharing their fan and swing settings. A mode without a source is ignored.
SYNC_SCHEMA: dict[vol.Marker, Any] = {
    vol.Optional(CONF_SYNC_MODES): SelectSelector(
        SelectSelectorConfig(
            options=[str(mode) for mode in MODE_SOURCE_KEYS],
            multiple=True,
            mode=SelectSelectorMode.LIST,
            translation_key=CONF_SYNC_MODES,
        )
    ),
}

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
        **SOURCES_SCHEMA,
        **SENSOR_SCHEMA,
        **SYNC_SCHEMA,
        **TEMPERATURE_SCHEMA,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {**SOURCES_SCHEMA, **SENSOR_SCHEMA, **SYNC_SCHEMA, **TEMPERATURE_SCHEMA}
)


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

    @classmethod
    @callback
    def async_supports_options_flow(
        cls, config_entry: config_entries.ConfigEntry
    ) -> bool:
        """Offer options only for UI entries: YAML would overwrite them."""
        return config_entry.source != config_entries.SOURCE_IMPORT

    async def async_step_import(
        self, import_data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Create or update an entry from YAML.

        The name identifies the entry. YAML already checked the sources and
        temperatures; only the self reference needs the entity registry.
        """
        errors = _validate_input(self.hass, import_data)
        if errors:
            _LOGGER.error(
                "Invalid YAML configuration for %s: %s",
                import_data[CONF_NAME],
                ", ".join(errors.values()),
            )
            return self.async_abort(reason="invalid_yaml")

        name = import_data[CONF_NAME]
        entry = await self.async_set_unique_id(name)
        if entry is not None:
            # Also clear options, which would replace the data (see entry_settings).
            # The update listener reloads the entry when it is loaded.
            if entry.data != import_data or entry.options or entry.title != name:
                self.hass.config_entries.async_update_entry(
                    entry, title=name, data=import_data, options={}
                )
            return self.async_abort(reason="already_configured")

        return self.async_create_entry(title=name, data=import_data)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_input(self.hass, user_input)
            if not errors:
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
        """Manage integration options.

        Every setting is saved here, so the options replace the initial data.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_input(self.hass, user_input)
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        # Show what the user just typed after an error, otherwise the
        # current settings.
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, user_input or dict(entry_settings(self.config_entry))
            ),
            errors=errors,
        )


def _validate_input(hass: HomeAssistant, user_input: dict[str, Any]) -> dict[str, str]:
    """Return form errors for user input (empty when valid)."""
    errors: dict[str, str] = {}
    registry = er.async_get(hass)

    configured = 0
    for mode, key in MODE_SOURCE_KEYS.items():
        source = user_input.get(key)
        if not source:
            continue
        configured += 1
        # Using one of our own entities as a source would make calls loop forever.
        registry_entry = registry.async_get(source)
        if registry_entry is not None and registry_entry.platform == DOMAIN:
            errors[key] = "self_reference"
            continue
        # The source must offer the mode it serves. A source that is not
        # loaded yet, unknown (still starting) or unavailable may not list its
        # real modes, so it is accepted.
        state = hass.states.get(source)
        source_modes = (
            state.attributes.get(ATTR_HVAC_MODES)
            if state is not None and state.state not in {STATE_UNAVAILABLE, STATE_UNKNOWN}
            else None
        )
        if source_modes is not None and mode not in source_modes:
            errors[key] = "mode_not_supported"

    if configured == 0:
        errors["base"] = "no_source"

    min_temp = user_input.get(CONF_MIN_TEMP)
    max_temp = user_input.get(CONF_MAX_TEMP)
    if min_temp is not None and max_temp is not None and min_temp >= max_temp:
        errors["base"] = "min_max_invalid"

    return errors
