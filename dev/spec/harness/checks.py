"""What the user sees of a configuration: created, refused, logged."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from homeassistant.data_entry_flow import FlowResultType

from .flows import INVALID_DATA


def created(result: Any) -> bool:
    """The flow created the entry."""
    return result["type"] == FlowResultType.CREATE_ENTRY


def refused(result: Any) -> bool:
    """The form shows an error: the configuration is not applied."""
    return result["type"] in (FlowResultType.FORM, INVALID_DATA) and bool(result.get("errors"))


def error_text(result: Any) -> str:
    """What the form tells about its error (its placeholders), to look for names in it."""
    placeholders = result.get("description_placeholders") or {}
    return " ".join(str(value) for value in placeholders.values())


def logged(caplog: pytest.LogCaptureFixture, level: int, *words: str) -> list[str]:
    """The messages logged at that level or above that contain every word (ignoring case)."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= level
        and all(word.casefold() in record.getMessage().casefold() for word in words)
    ]


def errors_logged(caplog: pytest.LogCaptureFixture, *words: str) -> list[str]:
    """The errors logged that contain every word."""
    return logged(caplog, logging.ERROR, *words)


def warnings_logged(caplog: pytest.LogCaptureFixture, *words: str) -> list[str]:
    """The warnings (or worse) logged that contain every word."""
    return logged(caplog, logging.WARNING, *words)
