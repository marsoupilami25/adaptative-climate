"""The dashboard card: served and declared to the frontend (ARCHITECTURE §13).

ENT-CARD-1: installing the integration is enough to get the card.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from ...const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# The folder of the build (CARD_ARCHITECTURE §8), served at URL_PATH (ARCH-12)
FOLDER = Path(__file__).resolve().parents[2] / "frontend"
FILE = "adaptative-climate-card.js"
URL_PATH = f"/{DOMAIN}/frontend"


async def async_setup_card(hass: HomeAssistant) -> None:
    """Serve the card file, then declare it to the frontend.

    Called from `async_setup`: once per Home Assistant instance.

    `http` is a dependency: the file is served. It is declared only when
    `frontend` is loaded (ARCH-13). A missing file (not built) is logged, and
    neither served nor declared.
    """
    if not await hass.async_add_executor_job((FOLDER / FILE).is_file):
        _LOGGER.warning("The card file %s is missing: build it (frontend/: npm run build)", FOLDER / FILE)
        return
    # No cache headers: the version in the URL is what changes on an update,
    # and a build during development is seen at the next refresh.
    await hass.http.async_register_static_paths([StaticPathConfig(URL_PATH, str(FOLDER), cache_headers=False)])
    if "frontend" not in hass.config.components:
        return
    integration = await async_get_integration(hass, DOMAIN)
    add_extra_js_url(hass, f"{URL_PATH}/{FILE}?v={integration.version}")
