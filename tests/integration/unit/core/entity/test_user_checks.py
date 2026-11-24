"""core/entity: the checks of a user request that Home Assistant makes before (ENT-STATE-4,
ENT-TGT-7, ENT-FAN-4, ENT-NOSRC-3). "The entity checks the same": called directly here.
"""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.adaptative_climate.core.entity.entity import (
    FEATURE_NOT_SUPPORTED,
    INVALID_OPTION,
    LOW_ABOVE_HIGH,
    SETTING_NOT_AVAILABLE,
    TEMPERATURE_OUT_OF_RANGE,
)
from custom_components.adaptative_climate.core.model.events import U_SET_MODE, U_SET_SETTINGS
from custom_components.adaptative_climate.core.model.values import Snapshot
from tests.integration.unit.core.kit import Core, climate

HEATER = "climate.heater"
AIRCON = "climate.aircon"
FAN = 1 | 8 | 128 | 256


def heating(**config: Any) -> Core:
    """The heater (fan low/high) in heat; the aircon off."""
    core = Core(
        {"heat_entity": HEATER, **config},
        snapshots={HEATER: climate("off", ["heat"], fan_modes=["low", "high"], fan_mode="low",
                                   supported_features=FAN)},
    )
    core.start()
    core.user(U_SET_MODE, "heat")
    core.change(HEATER, climate("heat", ["heat"], fan_modes=["low", "high"], fan_mode="low",
                                supported_features=FAN))
    return core


def test_ent_nosrc_3_user_request_while_unavailable_is_ignored() -> None:
    core = Core({"heat_entity": HEATER}, snapshots={HEATER: Snapshot("unavailable", {})})
    core.start()
    core.user(U_SET_MODE, "heat")
    core.user(U_SET_SETTINGS, {"temperature": 22.0})
    assert core.entity.refusal is None
    assert core.entities[HEATER].calls == []
    assert not core.entity.view().available


def test_ent_state_4_mode_not_configured_is_refused() -> None:
    core = heating()
    core.user(U_SET_MODE, "dry")
    assert core.entity.refusal is not None
    assert core.entity.view().hvac_mode == "heat"


@pytest.mark.parametrize(
    ("request_", "refusal"),
    [
        pytest.param({"target_temp_low": 19.0, "target_temp_high": 24.0}, FEATURE_NOT_SUPPORTED,
                     id="low/high without the feature"),
        pytest.param({"temperature": 50.0}, TEMPERATURE_OUT_OF_RANGE, id="out of range"),
        pytest.param({"temperature": "warm"}, TEMPERATURE_OUT_OF_RANGE, id="not a number"),
        pytest.param({"fan_mode": "turbo"}, INVALID_OPTION, id="option not shown"),
        pytest.param({"swing_mode": "on"}, SETTING_NOT_AVAILABLE, id="setting not discovered"),
    ],
)
def test_ent_tgt_7_ent_fan_4_settings_checked(request_: dict[str, Any], refusal: str) -> None:
    core = heating()
    before = core.entity.view()
    core.user(U_SET_SETTINGS, request_)
    assert core.entity.refusal == refusal
    assert core.entity.view() == before
    assert all(service == "set_hvac_mode" for service, _ in core.entities[HEATER].calls)


def test_ent_tgt_7_temperature_without_the_feature() -> None:
    core = Core(
        {"heat_entity": HEATER},
        snapshots={HEATER: climate("off", ["heat"], supported_features=128 | 256)},
    )
    core.start()  # heat not discovered, its source shows no target: none shown (ENT-CAP-4)
    core.user(U_SET_SETTINGS, {"temperature": 22.0})
    assert core.entity.refusal == FEATURE_NOT_SUPPORTED


def test_ent_tgt_7_low_above_high() -> None:
    core = Core(
        {"heat_entity": HEATER, "cool_entity": AIRCON},
        snapshots={HEATER: climate("off", ["heat"]), AIRCON: climate("off", ["cool"])},
    )
    core.start()
    core.user(U_SET_SETTINGS, {"target_temp_low": 25.0, "target_temp_high": 20.0})
    assert core.entity.refusal == LOW_ABOVE_HIGH
