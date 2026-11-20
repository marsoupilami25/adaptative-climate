"""The bench itself: the spec tests see the integration through Home Assistant only."""

from __future__ import annotations

import ast
from pathlib import Path

from dev.spec.harness import Bench, yaml_entry

SPEC_TESTS = Path(__file__).parent


def test_no_import_of_the_integration() -> None:
    """No module of dev/spec imports the integration: black box only."""
    offenders = []
    for path in SPEC_TESTS.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            offenders += [
                f"{path.name}: {name}" for name in names if name.startswith("custom_components")
            ]
    assert offenders == []


async def test_bench_runs_the_integration_across_a_restart(bench: Bench) -> None:
    """A device, an entry from the YAML, a mode asked, a restart."""
    heater = bench.device("climate.heater", ["heat"])
    await bench.start([yaml_entry("Living room", heat_entity="climate.heater")])
    ac = bench.ac("Living room")
    assert ac.exists
    assert ac.state == "off"
    assert ac.monitoring_sources.state == "off"
    assert ac.monitoring_temperatures.state == "off"

    await ac.set_hvac_mode("heat")
    assert heater.modes_asked() == ["heat"]
    assert heater.hvac_mode == "heat"
    assert ac.state == "heat"

    await bench.restart()
    ac = bench.ac("Living room")
    assert ac.state == "heat"
    assert len(bench.entries()) == 1
