"""Test helpers of Home Assistant, from whichever pytest plugin is installed.

The suites run on two versions of Home Assistant (ENT-HA-2):

- from 2026.11, the plugin `pytest-homeassistant` (module `pytest_homeassistant`);
- before, the plugin `pytest-homeassistant-custom-component`
  (module `pytest_homeassistant_custom_component`).

Both give the same helpers under different module names. The tests import
them from here only.
"""

from __future__ import annotations

try:
    from pytest_homeassistant import common
except ImportError:  # Home Assistant before 2026.11
    from pytest_homeassistant_custom_component import common  # type: ignore[no-redef]

MockConfigEntry = common.MockConfigEntry
MockModule = common.MockModule
MockPlatform = common.MockPlatform
async_capture_events = common.async_capture_events
async_fire_time_changed = common.async_fire_time_changed
async_mock_service = common.async_mock_service
async_test_home_assistant = common.async_test_home_assistant
mock_integration = common.mock_integration
mock_platform = common.mock_platform

__all__ = [
    "MockConfigEntry",
    "MockModule",
    "MockPlatform",
    "async_capture_events",
    "async_fire_time_changed",
    "async_mock_service",
    "async_test_home_assistant",
    "mock_integration",
    "mock_platform",
]
