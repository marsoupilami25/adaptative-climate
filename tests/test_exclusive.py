"""Tests for the exclusive sources: one source runs at a time."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.adaptative_climate.coordinator import EXCLUSIVE_RETRY

from .conftest import AC, ENTITY_ID, HEATER, FakeClimate

pytestmark = pytest.mark.usefixtures("init_integration")


async def _set_mode(hass: HomeAssistant, entity_id: str, mode: HVACMode) -> None:
    """Set the mode of an entity, as the user or elsewhere (remote, app)."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: entity_id, ATTR_HVAC_MODE: mode},
        blocking=True,
    )
    await hass.async_block_till_done()


def _mode(hass: HomeAssistant, entity_id: str = ENTITY_ID) -> str:
    return hass.states.get(entity_id).state


def _stuck(hass: HomeAssistant, init_integration: Any) -> dict[str, str]:
    return init_integration.runtime_data.stuck_sources


async def _wait_retry(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Let the retry of the stuck sources run."""
    freezer.tick(EXCLUSIVE_RETRY + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_new_source_turned_on_first(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """The new source is turned on before the previous one is turned off."""
    await _set_mode(hass, ENTITY_ID, HVACMode.HEAT)
    log: list[tuple[str, HVACMode]] = []
    heater.mode_log = ac.mode_log = log

    await _set_mode(hass, ENTITY_ID, HVACMode.COOL)

    assert log == [(AC, HVACMode.COOL), (HEATER, HVACMode.OFF)]
    assert _mode(hass) == HVACMode.COOL
    assert _mode(hass, HEATER) == HVACMode.OFF


async def test_new_source_fails_keeps_previous(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """A source that cannot be turned on leaves the previous mode running."""
    await _set_mode(hass, ENTITY_ID, HVACMode.HEAT)
    ac.failing_modes = {HVACMode.COOL}

    with pytest.raises(HomeAssistantError):
        await _set_mode(hass, ENTITY_ID, HVACMode.COOL)
    await hass.async_block_till_done()

    assert _mode(hass) == HVACMode.HEAT
    assert _mode(hass, HEATER) == HVACMode.HEAT
    assert _mode(hass, AC) == HVACMode.OFF


async def test_already_running_source_wins(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """A mode whose source already runs wins over the source turned on last."""
    # Both run and cannot be turned off; the heater was turned on last.
    heater.failing_modes = ac.failing_modes = {HVACMode.OFF}
    ac._attr_hvac_mode = HVACMode.COOL
    ac.async_write_ha_state()
    heater._attr_hvac_mode = HVACMode.HEAT
    heater.async_write_ha_state()
    await hass.async_block_till_done()
    assert _mode(hass) == HVACMode.HEAT

    await _set_mode(hass, ENTITY_ID, HVACMode.COOL)

    assert _mode(hass) == HVACMode.COOL
    assert hass.states.get(ENTITY_ID).attributes["active_entity_id"] == AC


async def test_stuck_source_tried_again(
    hass: HomeAssistant,
    heater: FakeClimate,
    init_integration: Any,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A source that does not turn off is tried again every minute while it runs."""
    await _set_mode(hass, ENTITY_ID, HVACMode.HEAT)
    heater.failing_modes = {HVACMode.OFF}
    heater.calls.clear()

    # The mode change works: the new source runs.
    await _set_mode(hass, ENTITY_ID, HVACMode.COOL)

    assert _mode(hass) == HVACMode.COOL
    assert _mode(hass, HEATER) == HVACMode.HEAT
    # Tried twice at once, logged once.
    assert heater.calls.count(("set_hvac_mode", {"hvac_mode": HVACMode.OFF})) == 2
    assert _stuck(hass, init_integration) == {HEATER: (AC, f"{HEATER} cannot be reached")}
    assert caplog.text.count(f"{HEATER} (heat) does not turn off while {AC} runs") == 1

    # Still failing: tried again twice, not logged again.
    heater.calls.clear()
    await _wait_retry(hass, freezer)
    assert heater.calls.count(("set_hvac_mode", {"hvac_mode": HVACMode.OFF})) == 2
    assert HEATER in _stuck(hass, init_integration)
    assert caplog.text.count(f"{HEATER} (heat) does not turn off while {AC} runs") == 1

    # It works again.
    heater.failing_modes = set()
    await _wait_retry(hass, freezer)
    assert _mode(hass, HEATER) == HVACMode.OFF
    assert _stuck(hass, init_integration) == {}
    assert f"{HEATER} no longer runs along with another source" in caplog.text

    # No more retries.
    heater.calls.clear()
    await _wait_retry(hass, freezer)
    assert heater.calls == []


async def test_stuck_source_turned_off_elsewhere(
    hass: HomeAssistant,
    heater: FakeClimate,
    init_integration: Any,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A stuck source turned off elsewhere is no longer tried."""
    await _set_mode(hass, ENTITY_ID, HVACMode.HEAT)
    heater.failing_modes = {HVACMode.OFF}
    await _set_mode(hass, ENTITY_ID, HVACMode.COOL)
    assert HEATER in _stuck(hass, init_integration)

    heater._attr_hvac_mode = HVACMode.OFF
    heater.async_write_ha_state()
    await hass.async_block_till_done()

    assert _stuck(hass, init_integration) == {}
    heater.calls.clear()
    await _wait_retry(hass, freezer)
    assert heater.calls == []


async def test_stuck_sources_forgotten_when_off(
    hass: HomeAssistant,
    heater: FakeClimate,
    ac: FakeClimate,
    init_integration: Any,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Once the source turned on last stops, the stuck sources are not tried."""
    await _set_mode(hass, ENTITY_ID, HVACMode.HEAT)
    heater.failing_modes = {HVACMode.OFF}
    await _set_mode(hass, ENTITY_ID, HVACMode.COOL)

    await _set_mode(hass, AC, HVACMode.OFF)
    heater.calls.clear()
    await _wait_retry(hass, freezer)

    assert heater.calls == []
    assert _stuck(hass, init_integration) == {}
    # The heater still runs: the entity follows it.
    assert _mode(hass) == HVACMode.HEAT


async def test_source_turned_on_elsewhere_with_stuck_source(
    hass: HomeAssistant,
    heater: FakeClimate,
    init_integration: Any,
) -> None:
    """A source turned on elsewhere wins even if the other one does not turn off."""
    await _set_mode(hass, ENTITY_ID, HVACMode.HEAT)
    heater.failing_modes = {HVACMode.OFF}

    await _set_mode(hass, AC, HVACMode.COOL)

    assert _mode(hass) == HVACMode.COOL
    assert HEATER in _stuck(hass, init_integration)


async def test_source_back_from_unavailable_after_another_turned_on(
    hass: HomeAssistant, heater: FakeClimate, ac: FakeClimate
) -> None:
    """A source back in its old mode while another one runs is turned off."""
    await _set_mode(hass, ENTITY_ID, HVACMode.HEAT)
    hass.states.async_set(HEATER, "unavailable")
    await hass.async_block_till_done()
    await _set_mode(hass, ENTITY_ID, HVACMode.COOL)

    # Back, still showing heat.
    heater.async_write_ha_state()
    await hass.async_block_till_done()

    assert _mode(hass, HEATER) == HVACMode.OFF
    assert _mode(hass, AC) == HVACMode.COOL
    assert _mode(hass) == HVACMode.COOL


async def test_source_back_from_unavailable_alone_runs(
    hass: HomeAssistant, heater: FakeClimate
) -> None:
    """A source back in its mode with nothing else running stays on."""
    await _set_mode(hass, ENTITY_ID, HVACMode.HEAT)
    hass.states.async_set(HEATER, "unavailable")
    await hass.async_block_till_done()

    heater.async_write_ha_state()
    await hass.async_block_till_done()

    assert _mode(hass, HEATER) == HVACMode.HEAT
    assert _mode(hass) == HVACMode.HEAT
