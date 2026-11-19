"""Import and sync of the YAML entries (spec §3.2, CFG-YAML-1 to CFG-YAML-5)."""

from __future__ import annotations

from collections import Counter
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from ...const import DOMAIN
from ..options.checks import check_config
from ..options.schema import CONF_NAME, YAML_ENTRY_SCHEMA

_LOGGER = logging.getLogger(__package__)

#: Each entry is validated alone: an invalid one is not imported (CFG-YAML-5).
CONFIG_SCHEMA = vol.Schema(
    {vol.Optional(DOMAIN): vol.All(cv.ensure_list, [dict])},
    extra=vol.ALLOW_EXTRA,
)

YAML_ERRORS = "yaml_errors"


def yaml_error(hass: HomeAssistant, entry_id: str) -> str | None:
    """The error of the YAML entry of an imported entry, if invalid: it is not loaded."""
    return hass.data.get(DOMAIN, {}).get(YAML_ERRORS, {}).get(entry_id)


async def async_import_yaml(hass: HomeAssistant, config: ConfigType) -> None:
    """Match the YAML entries to the imported entries by name; create, update, delete.

    An invalid YAML entry is an error (CFG-YAML-5): it is not imported, and
    the error is logged. An imported entry of that name is kept, with its
    stored data, but not loaded: its setup fails with the error.
    """
    errors: dict[str, str] = hass.data.setdefault(DOMAIN, {}).setdefault(YAML_ERRORS, {})
    errors.clear()
    #: Invalid YAML entries, by name ignoring case (CFG-NAME-1).
    invalid: dict[str, str] = {}
    entries: list[dict[str, Any]] = []
    for raw in config.get(DOMAIN) or []:
        try:
            entries.append(dict(YAML_ENTRY_SCHEMA(raw)))
        except vol.Invalid as err:
            _invalid(invalid, raw.get(CONF_NAME), str(err))
    # The name identifies the entry, ignoring case (CFG-NAME-1, CFG-YAML-2)
    counts = Counter(_key(entry[CONF_NAME]) for entry in entries)
    for entry in entries:
        if counts[_key(entry[CONF_NAME])] > 1:
            _invalid(invalid, entry[CONF_NAME], "the name is used several times")
    entries = [entry for entry in entries if counts[_key(entry[CONF_NAME])] == 1]

    imported = {
        _key(entry.data.get(CONF_NAME, "")): entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.source == SOURCE_IMPORT
    }
    #: Names of the valid YAML entries that match an imported entry.
    kept: set[str] = set()
    for data in entries:
        name = data[CONF_NAME]
        existing = imported.get(_key(name))
        if existing is None:
            # Checked by the import flow, as in the UI (CFG-YAML-5)
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN, context={"source": SOURCE_IMPORT}, data=data
                )
            )
            continue
        if dict(existing.data) == data:
            kept.add(_key(name))  # unchanged: a restart, nothing refused (CFG-MODE-5)
            continue
        problems = check_config(hass, data, existing.entry_id)
        if problems:
            _invalid(
                invalid, name, "; ".join(f"{key} {detail}".strip() for key, detail in problems)
            )
            continue
        hass.config_entries.async_update_entry(existing, title=name, data=data)  # ENT-INIT-4
        kept.add(_key(name))
    for key, entry in imported.items():
        if key in kept:
            continue
        if key in invalid:
            # Kept with its stored data; its setup fails with the error (logged by Home Assistant)
            errors[entry.entry_id] = invalid[key]
            continue
        # Removed from the YAML: deleted, with its stored data (END-3)
        _LOGGER.info("Imported entry %s removed from the YAML: deleted", entry.title)
        hass.async_create_task(hass.config_entries.async_remove(entry.entry_id))


def _invalid(invalid: dict[str, str], name: Any, error: str) -> None:
    """An invalid YAML entry is an error: not imported, logged (CFG-YAML-5)."""
    _LOGGER.error("YAML entry %s is invalid, not imported: %s", name, error)
    if isinstance(name, str):
        invalid[_key(name)] = error


def _key(name: str) -> str:
    """A name, ignoring case (CFG-NAME-1)."""
    return str(name).casefold()
