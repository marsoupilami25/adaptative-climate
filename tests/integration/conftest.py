"""Shared by the pytest suites of tests/integration (spec, unit)."""

from __future__ import annotations

import pytest

# The `custom_components` package of the repository, imported before Home
# Assistant mounts the testing config of the plugin, whose own
# `custom_components` package would hide it (Home Assistant before 2026.11).
import custom_components  # noqa: F401


def pytest_configure(config: pytest.Config) -> None:
    """The marker that ties a spec test to the rules it checks."""
    config.addinivalue_line(
        "markers",
        "spec(*rules): the rules of documents/SPEC.md the test checks (SRC-STATE-3...)",
    )
