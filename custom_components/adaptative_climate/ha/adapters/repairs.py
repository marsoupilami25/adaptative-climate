"""Repairs port: issues of Home Assistant (ENT-HVAC-5, ENT-FAN-7, ENT-FAN-8)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from ...const import DOMAIN


class RepairsAdapter:
    """Raises and clears the issues of an entry."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._raised: set[str] = set()

    def raise_issue(self, issue_id: str, key: str, placeholders: dict[str, str]) -> None:
        """Raise (or update) an issue."""
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=key,
            translation_placeholders=placeholders,
        )
        self._raised.add(issue_id)

    def clear_issue(self, issue_id: str) -> None:
        """Remove an issue."""
        ir.async_delete_issue(self._hass, DOMAIN, issue_id)
        self._raised.discard(issue_id)

    def clear_all(self) -> None:
        """Every issue of the entry removed (END-1)."""
        # Safety net (not reached): the entity has removed its issues at HA=>AC_unload
        for issue_id in list(self._raised):
            self.clear_issue(issue_id)
