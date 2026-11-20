"""Notify port: logs and the event adaptative_climate_problem (MON-LIFE-2, MON-LIFE-3)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__package__.rsplit(".", 2)[0])

PROBLEM_EVENT = "adaptative_climate_problem"
LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


class NotifyAdapter:
    """Logs of an entry, prefixed by its name."""

    def __init__(self, hass: HomeAssistant, name: str) -> None:
        self._hass = hass
        self._name = name

    def log(self, level: str, message: str) -> str:
        """Log at a level, prefixed by the name of the entry; returns the text logged."""
        text = f"{self._name}: {message}"
        _LOGGER.log(LEVELS.get(level, logging.INFO), "%s", text)
        return text

    def fire_problem(self, data: dict[str, Any]) -> None:
        """Fire adaptative_climate_problem."""
        self._hass.bus.async_fire(PROBLEM_EVENT, data)
