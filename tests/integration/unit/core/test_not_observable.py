"""The rules the spec tests cannot observe (tests/integration/spec/not_observable.md), checked on the core.

SRC-DATA-5, ENT-DATA-2 (invalid stored data), ENT-INIT-2, ENT-INIT-5, EVT-2, EVT-3.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from custom_components.adaptative_climate.core.model import events as events_module
from custom_components.adaptative_climate.core.model.events import (
    HA_START,
    S_SETTINGS,
    T_TEMPERATURE,
    U_SET_MODE,
    U_SET_SETTINGS,
    Event,
)
from custom_components.adaptative_climate.core.model.values import Snapshot
from tests.integration.unit.core.kit import Core, climate

HEATER = "climate.heater"
AIRCON = "climate.aircon"
FAN = 1 | 8 | 128 | 256  # target, fan, off, on
CONFIG = {"heat_entity": HEATER, "cool_entity": AIRCON}
AWAY = Snapshot("unavailable", {})


def heater(state: str = "off", **attributes: Any) -> Snapshot:
    values = {
        "min_temp": 10.0,
        "max_temp": 30.0,
        "fan_modes": ["low", "high"],
        "fan_mode": "low",
        "supported_features": FAN,
        **attributes,
    }
    return climate(state, ["heat"], **values)


def stored_after_heating() -> dict[str, Any]:
    """The stored data after heat at 22 °C, fan high."""
    core = Core(CONFIG, snapshots={HEATER: heater(), AIRCON: climate("off", ["cool"])})
    core.start()
    core.user(U_SET_MODE, "heat")
    core.change(HEATER, heater("heat"))
    core.user(U_SET_SETTINGS, {"temperature": 22.0, "fan_mode": "high"})
    core.advance(20)
    return copy.deepcopy(core.store.parts)


def restart(stored: dict[str, Any], heater_now: Snapshot | None = AWAY) -> Core:
    """A new start on that stored data; the heater away (nothing read from it)."""
    core = Core(
        CONFIG, stored=stored, snapshots={HEATER: heater_now, AIRCON: climate("off", ["cool"])}
    )
    core.start()
    return core


def test_stored_data_restored() -> None:
    """The reference for the tests below: everything valid."""
    view = restart(stored_after_heating()).entity.view()
    assert view.hvac_mode is None  # WAITING(heat)
    assert (view.min_temp, view.max_temp) == (10.0, 30.0)
    assert view.temperature == 22.0
    assert view.values["fan_mode"] == "high"


# --- SRC-DATA-5 -------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["abc", None, [1], {"x": 1}])
def test_src_data_5_invalid_capability_dropped_others_kept(bad: Any) -> None:
    stored = stored_after_heating()
    stored[f"source:{HEATER}"]["modes"]["heat"]["max_temp"] = bad
    view = restart(stored).entity.view()
    assert (view.min_temp, view.max_temp) == (10.0, 35.0)  # the default for the max only
    assert view.options["fan_mode"] == ["low", "high"]


def test_src_data_5_invalid_state_handled_as_missing() -> None:
    """No valid stored state: OFF, whose entry turns the running device off."""
    stored = stored_after_heating()
    stored[f"source:{HEATER}"]["state"] = "boost"
    stored["entity"]["mode"] = "off"
    core = restart(stored, heater_now=heater("heat"))
    assert core.entities[HEATER].modes_asked() == ["off"]


def test_src_data_5_invalid_hvac_modes_read_again() -> None:
    stored = stored_after_heating()
    stored[f"source:{HEATER}"]["hvac_modes"] = "heat"
    core = restart(stored, heater_now=heater("heat"))
    assert core.sources[HEATER].state.available


def test_src_data_5_invalid_part_dropped() -> None:
    stored = stored_after_heating()
    stored[f"source:{HEATER}"] = ["not", "a", "part"]
    core = restart(stored, heater_now=heater("off"))
    assert core.sources[HEATER].state.available  # read again from the source entity


# --- ENT-DATA-2 ------------------------------------------------------------------------------


def test_ent_data_2_invalid_target_taken_from_the_sources() -> None:
    stored = stored_after_heating()
    stored["entity"]["targets"]["T"] = "warm"
    view = restart(stored, heater_now=heater("heat", temperature=19.0)).entity.view()
    assert view.temperature == 19.0  # T taken again from the heater (ENT-TGT-10)


def test_ent_data_2_invalid_fan_value_dropped() -> None:
    """The memory of heat is empty: nothing shown until the source reports a value.
    The source keeps its own stored setting (independent, ENT-DATA-2) and sends it."""
    stored = stored_after_heating()
    stored["entity"]["memory"]["heat"]["fan_mode"] = 3
    core = restart(stored, heater_now=heater("heat", fan_mode="low"))
    view = core.entity.view()
    assert view.hvac_mode == "heat"
    assert view.values["fan_mode"] is None
    assert view.attributes["saved_settings"] == {}
    assert ("set_fan_mode", {"fan_mode": "high"}) in core.entities[HEATER].calls


def test_ent_data_2_invalid_mode_is_off() -> None:
    stored = stored_after_heating()
    stored["entity"]["mode"] = 42
    core = restart(stored, heater_now=heater("heat"))
    view = core.entity.view()
    assert view.hvac_mode == "off"
    assert view.attributes["saved_targets"]["single"] == 22.0  # the other data restored
    assert view.attributes["saved_settings"] == {"heat": {"fan_mode": "high"}}


def test_ent_data_2_loss_on_one_side_changes_nothing_on_the_other() -> None:
    stored = stored_after_heating()
    del stored["entity"]
    core = restart(stored)
    assert core.entity.view().hvac_mode == "off"  # no stored mode
    data = core.sources[HEATER].capabilities
    assert data.hvac_modes == ["off", "heat"]
    caps = data.caps("heat")
    assert caps is not None and (caps.min_temp, caps.max_temp) == (10.0, 30.0)


# --- ENT-INIT-2 ------------------------------------------------------------------------------


def test_ent_init_2_stored_mode_whose_source_is_undiscovered() -> None:
    """The stored data of the heater lost, the heater away: heat cannot resume, OFF."""
    stored = stored_after_heating()
    del stored[f"source:{HEATER}"]
    core = restart(stored)
    assert core.sources[HEATER].state.undiscovered
    assert core.entity.view().hvac_mode == "off"


# --- ENT-INIT-5 ------------------------------------------------------------------------------


def test_ent_init_5_in_init_only_the_first_states_change_the_state() -> None:
    """Events in INIT: a setting from a source is ignored; the external sensor is written."""
    core = Core(
        {**CONFIG, "temperature_sensor": "sensor.room", "heat_external_sensor": "number.trv"},
        snapshots={HEATER: heater(), AIRCON: climate("off", ["cool"])},
        sensor=21.0,
    )
    entity = core.entity.actor_id
    core.stimulus(
        (entity, Event(HA_START, "HA")),
        (entity, Event(T_TEMPERATURE, "T", 23.0)),
        (entity, Event(S_SETTINGS, HEATER, {"temperature": 30.0})),
        *[(source_id, Event(HA_START, "HA")) for source_id in core.sources],
        (core.monitoring.actor_id, Event(HA_START, "HA")),
    )
    assert core.externals["number.trv"].written == [21.0, 23.0]
    view = core.entity.view()
    assert view.hvac_mode == "off"
    assert 30.0 not in view.attributes["saved_targets"].values()


# --- EVT-2, EVT-3 -------------------------------------------------------------------------------


def test_evt_2_only_events_of_the_spec_are_exchanged() -> None:
    """Every event delivered or posted in a full scenario is one the spec names."""
    declared = {
        value for name, value in vars(events_module).items()
        if name.isupper() and isinstance(value, str)
    }
    seen: set[str] = set()
    core = Core(CONFIG, snapshots={HEATER: heater(), AIRCON: climate("off", ["cool"])})
    original_send = core.runtime.send

    def send(target: str, event: Event) -> None:
        seen.add(event.kind)
        original_send(target, event)

    core.runtime.send = send  # type: ignore[method-assign]
    for actor in (core.entity, *core.sources.values(), core.monitoring):
        original_post = actor.post

        def post(event: Event, _post: Any = original_post) -> None:
            seen.add(event.kind)
            _post(event)

        actor.post = post  # type: ignore[method-assign]
    core.start()
    core.user(U_SET_MODE, "heat")
    core.change(HEATER, heater("heat"))
    core.user(U_SET_SETTINGS, {"temperature": 22.0})
    core.change(AIRCON, climate("cool", ["cool"]))
    core.advance(100)
    assert seen <= declared, seen - declared
    assert len(seen) > 10


def test_evt_3_reading_a_data_item_triggers_nothing() -> None:
    core = Core(CONFIG, snapshots={HEATER: heater(), AIRCON: climate("off", ["cool"])})
    core.start()
    source = core.sources[HEATER]
    saved = list(core.store.saved)
    before = repr(core.entity.view())
    for _ in range(3):
        _ = (source.state, source.capabilities, source.temperature, source.action)
        _ = source.settings
        core.entity.view()
    assert core.store.saved == saved
    assert repr(core.entity.view()) == before
    assert core.entities[HEATER].calls == []
