"""Fixtures of the spec tests, and the collection of the rules they check."""

from __future__ import annotations

from collections.abc import AsyncGenerator
import json
from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest

from tests.integration.spec.harness import Bench


@pytest.fixture
async def bench(
    hass_storage: dict[str, Any], freezer: FrozenDateTimeFactory
) -> AsyncGenerator[Bench]:
    """The test bench; Home Assistant starts with `await bench.start(yaml)`."""
    test_bench = Bench(hass_storage, freezer)
    yield test_bench
    await test_bench.close()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--spec-rules",
        metavar="PATH",
        help="write the rules each spec test checks to PATH (JSON), for rule_coverage.py",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    path = config.getoption("--spec-rules")
    if not path:
        return
    rules = {
        item.nodeid: sorted({rule for mark in item.iter_markers("spec") for rule in mark.args})
        for item in items
    }
    with open(path, "w", encoding="utf-8") as file:
        json.dump(rules, file, indent=1)
