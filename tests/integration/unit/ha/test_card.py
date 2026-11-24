"""ha/frontend/card.py: the branches the spec tests do not reach (ARCHITECTURE §13).

The spec tests load `http` but not `frontend` (its package is not installed):
the declaration to the frontend, and a missing card file, are checked here.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
import pytest

from custom_components.adaptative_climate.ha.frontend import card

MANIFEST = Path(card.__file__).resolve().parents[2] / "manifest.json"


@pytest.fixture
def loaded(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """`http` and `frontend` loaded; returns the URLs declared to the frontend."""
    hass.config.components.update({"http", "frontend"})
    hass.http = SimpleNamespace(async_register_static_paths=AsyncMock())
    declared: list[str] = []
    monkeypatch.setattr(card, "add_extra_js_url", lambda _hass, url: declared.append(url))
    return declared


async def test_declared_to_the_frontend_with_the_version(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    loaded: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The URL carries the version of the integration (ARCH-12)."""
    (tmp_path / card.FILE).write_text("// card\n")
    monkeypatch.setattr(card, "FOLDER", tmp_path)
    await card.async_setup_card(hass)
    version = json.loads(MANIFEST.read_text())["version"]
    assert loaded == [f"/adaptative_climate/frontend/adaptative-climate-card.js?v={version}"]
    (configs,), _ = hass.http.async_register_static_paths.call_args
    assert [(config.url_path, config.path) for config in configs] == [
        ("/adaptative_climate/frontend", str(tmp_path))
    ]


async def test_a_missing_file_is_logged_neither_served_nor_declared(
    hass: HomeAssistant,
    loaded: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Not built (ARCH-13): a warning, and the integration works without the card."""
    monkeypatch.setattr(card, "FOLDER", tmp_path)
    await card.async_setup_card(hass)
    hass.http.async_register_static_paths.assert_not_called()
    assert loaded == []
    assert "The card file" in caplog.text
