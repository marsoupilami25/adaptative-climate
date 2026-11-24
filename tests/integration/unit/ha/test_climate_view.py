"""ha/views/climate_view.py: the temperatures under both names (ENT-HA-1), the action shown.

Home Assistant 2026.11 reads the `native_*` names, 2026.6 the former ones: each
version runs one path; both are read here.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace
from typing import Any

from custom_components.adaptative_climate.ha.views.climate_view import AdaptativeClimateEntity
from tests.integration.unit.core.kit import Core, climate

HEATER = "climate.heater"
AIRCON = "climate.aircon"


def view_entity(core: Core, **changes: Any) -> AdaptativeClimateEntity:
    view = dataclasses.replace(core.entity.view(), **changes)
    entity = SimpleNamespace(view=lambda: view)
    host = SimpleNamespace(model=core.model, entity=entity, views=[])
    return AdaptativeClimateEntity(host)  # type: ignore[arg-type]


def test_ent_ha_1_both_names() -> None:
    core = Core(
        {"heat_entity": HEATER, "cool_entity": AIRCON},
        snapshots={HEATER: climate("off", ["heat"]), AIRCON: climate("off", ["cool"])},
        unit="°C",
    )
    core.start()
    entity = view_entity(core, current_temperature=20.5, temperature=19.0)
    assert entity.temperature_unit == entity.native_temperature_unit == "°C"
    assert entity.current_temperature == entity.native_current_temperature == 20.5
    assert entity.target_temperature == entity.native_target_temperature == 19.0
    entity = view_entity(core, temperature=None, target_temp_low=19.0, target_temp_high=24.0)
    assert entity.target_temperature_low == entity.native_target_temperature_low == 19.0
    assert entity.target_temperature_high == entity.native_target_temperature_high == 24.0


def test_action_unknown_to_home_assistant_is_not_shown() -> None:
    core = Core({"heat_entity": HEATER}, snapshots={HEATER: climate("off", ["heat"])})
    core.start()
    assert view_entity(core, hvac_action="warming_up").hvac_action is None
    assert view_entity(core, hvac_action="heating").hvac_action == "heating"
