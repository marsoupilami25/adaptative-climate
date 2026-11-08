"""Unit tests of the engine parts that do not need a running entity."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.climate import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.adaptative_climate.engine.phase import CombinedPhase, wanted_phase
from custom_components.adaptative_climate.engine.profiles import (
    AutoProfile,
    CombinedHeatCoolProfile,
    DryProfile,
    FanOnlyProfile,
    ModeProfile,
    RangeHeatCoolProfile,
    SetpointProfile,
    build_profiles,
)
from custom_components.adaptative_climate.engine.targets import TargetStore
from custom_components.adaptative_climate.engine.timer import Timer
from custom_components.adaptative_climate.engine.util import (
    changed,
    is_number,
    match_option,
    same_temperature,
    same_value,
)

LOW = ATTR_TARGET_TEMP_LOW
HIGH = ATTR_TARGET_TEMP_HIGH
TEMP = ATTR_TEMPERATURE
RANGE = ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
TARGET = ClimateEntityFeature.TARGET_TEMPERATURE


# util


def test_is_number() -> None:
    """Booleans are not numbers."""
    assert is_number(1)
    assert is_number(1.5)
    assert not is_number(True)
    assert not is_number("1")
    assert not is_number(None)


def test_same_temperature() -> None:
    """Float noise is ignored; non numbers never match."""
    assert same_temperature(0.1 + 0.2, 0.3)
    assert not same_temperature(20, 20.5)
    assert not same_temperature(None, None)
    assert not changed(0.1 + 0.2, 0.3)
    assert changed(None, 20)
    assert not changed(None, None)


def test_same_value_and_match_option() -> None:
    """Setting values are compared ignoring case, and spelled as the source does."""
    assert same_value("Auto", "auto")
    assert not same_value("auto", None)
    assert match_option(["Low", "High", 3], "high") == "High"
    assert match_option(["Low"], "medium") is None


# wanted_phase


@pytest.mark.parametrize(
    ("current", "temperature", "expected"),
    [
        # Below low: heat; above high: cool.
        (None, 18, HVACMode.HEAT),
        (HVACMode.COOL, 18, HVACMode.HEAT),
        (None, 27, HVACMode.COOL),
        (HVACMode.HEAT, 27, HVACMode.COOL),
        # In between: the current phase is kept.
        (HVACMode.HEAT, 24, HVACMode.HEAT),
        (HVACMode.COOL, 21, HVACMode.COOL),
        # Entering in between: the closest target, heat on a tie.
        (None, 21, HVACMode.HEAT),
        (None, 24, HVACMode.COOL),
        (None, 22.5, HVACMode.HEAT),
    ],
)
def test_wanted_phase(
    current: HVACMode | None, temperature: float, expected: HVACMode
) -> None:
    """The phase follows the room temperature around the low/high targets."""
    assert wanted_phase(current, [temperature], 20, 25, HVACMode.OFF) is expected


@pytest.mark.parametrize(
    ("current", "temperatures", "expected"),
    [
        # Both sources agree: the phase follows them.
        (HVACMode.HEAT, [26, 27], HVACMode.COOL),
        (HVACMode.COOL, [18, 19], HVACMode.HEAT),
        # They contradict each other: the current phase is kept.
        (HVACMode.HEAT, [26, 18], HVACMode.HEAT),
        (HVACMode.COOL, [26, 18], HVACMode.COOL),
        # One is past a target, the other in between: kept too.
        (HVACMode.HEAT, [26, 23], HVACMode.HEAT),
        (HVACMode.COOL, [22, 19], HVACMode.COOL),
        # Entering: the closest target to their mean.
        (None, [26, 18], HVACMode.HEAT),
        (None, [27, 21], HVACMode.COOL),
        (None, [26, 27], HVACMode.COOL),
    ],
)
def test_wanted_phase_several_temperatures(
    current: HVACMode | None, temperatures: list[float], expected: HVACMode
) -> None:
    """With several readings, the phase switches only when they all agree."""
    assert wanted_phase(current, temperatures, 20, 25, HVACMode.OFF) is expected


def test_wanted_phase_inverted_targets() -> None:
    """Low above high: between them, the current phase is kept."""
    assert wanted_phase(HVACMode.HEAT, [24], 25, 23, HVACMode.OFF) is HVACMode.HEAT
    assert wanted_phase(HVACMode.COOL, [24], 25, 23, HVACMode.OFF) is HVACMode.COOL


def test_wanted_phase_without_temperature() -> None:
    """Without temperature: the current phase, else the running source, else heat."""
    assert wanted_phase(HVACMode.COOL, [], 20, 25, HVACMode.HEAT) is HVACMode.COOL
    assert wanted_phase(None, [], 20, 25, HVACMode.COOL) is HVACMode.COOL
    assert wanted_phase(None, [], 20, 25, HVACMode.AUTO) is HVACMode.HEAT
    assert wanted_phase(None, [22], None, 25, HVACMode.OFF) is HVACMode.HEAT


# TargetStore


def _store(**values: float | None) -> TargetStore:
    store = TargetStore()
    for target, value in values.items():
        store[target] = value
    return store


def _keep(target: str, value: float) -> float:
    return value


def _clamp(low: float, high: float) -> Any:
    def keep(target: str, value: float) -> float:
        return min(max(value, low), high)

    return keep


def test_gap_moves_the_other_target() -> None:
    """The target just set stays, the other one moves."""
    store = _store(target_temp_low=24.0, target_temp_high=24.5)
    store.apply_gap([LOW], 2.0, _keep)
    assert (store[LOW], store[HIGH]) == (24.0, 26.0)

    store = _store(target_temp_low=24.0, target_temp_high=24.5)
    store.apply_gap([HIGH], 2.0, _keep)
    assert (store[LOW], store[HIGH]) == (22.5, 24.5)


def test_gap_both_set_moves_high() -> None:
    """Both targets set: the high one moves."""
    store = _store(target_temp_low=24.0, target_temp_high=24.5)
    store.apply_gap([LOW, HIGH], 1.0, _keep)
    assert (store[LOW], store[HIGH]) == (24.0, 25.0)


def test_gap_gives_way() -> None:
    """The other target cannot follow: the target just set moves back."""
    store = _store(target_temp_low=29.5, target_temp_high=30.0)
    store.apply_gap([LOW], 1.0, _clamp(10, 30))
    assert (store[LOW], store[HIGH]) == (29.0, 30.0)


def test_gap_kept_from_source() -> None:
    """A change made on a source does not give way, even if the gap is lost."""
    store = _store(target_temp_low=29.5, target_temp_high=30.0)
    store.apply_gap([LOW], 1.0, _clamp(10, 30), give_way=False)
    assert (store[LOW], store[HIGH]) == (29.5, 30.0)


def test_gap_untouched() -> None:
    """Nothing moves when the gap holds, or only the single target changed."""
    store = _store(target_temp_low=20.0, target_temp_high=21.0)
    store.apply_gap([LOW], 1.0, _clamp(0, 0))
    assert (store[LOW], store[HIGH]) == (20.0, 21.0)

    store = _store(target_temp_low=20.0, target_temp_high=20.0)
    store.apply_gap([TEMP], 1.0, _keep)
    assert (store[LOW], store[HIGH]) == (20.0, 20.0)

    store = _store(target_temp_low=20.0)
    assert store.gap_respected(5)
    store.apply_gap([LOW], 1.0, _keep)
    assert store[HIGH] is None


def test_store_restore() -> None:
    """Saved targets are read back; bad values are dropped."""
    store = TargetStore()
    store.restore(
        {
            "target_temperature": 21,
            "target_temperature_low": "x",
            "target_temperature_high": True,
        }
    )
    assert (store[TEMP], store[LOW], store[HIGH]) == (21.0, None, None)
    assert not store.has_range()
    assert store.as_dict() == {
        "target_temperature": 21.0,
        "target_temperature_low": None,
        "target_temperature_high": None,
    }


# Profiles


def _sources(features: int = 0, **modes: str) -> Any:
    """Return fake sources: the modes given, each with the same features."""
    return SimpleNamespace(
        mode_sources={HVACMode(mode): entity_id for mode, entity_id in modes.items()},
        features=lambda entity_id: ClimateEntityFeature(features if entity_id else 0),
    )


def test_build_profiles() -> None:
    """Each configured mode gets its profile, in display order."""
    sources = _sources(
        heat="climate.h",
        cool="climate.c",
        auto="climate.a",
        dry="climate.d",
        fan_only="climate.f",
    )
    profiles = build_profiles(sources, combined=True)
    assert list(profiles) == [
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.HEAT_COOL,
        HVACMode.AUTO,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
    ]
    assert type(profiles[HVACMode.AUTO]) is AutoProfile
    assert type(profiles[HVACMode.HEAT]) is SetpointProfile
    assert type(profiles[HVACMode.HEAT_COOL]) is CombinedHeatCoolProfile
    assert type(profiles[HVACMode.DRY]) is DryProfile
    assert type(profiles[HVACMode.FAN_ONLY]) is FanOnlyProfile

    assert HVACMode.HEAT_COOL not in build_profiles(sources, combined=False)

    sources = _sources(heat_cool="climate.hc")
    assert type(build_profiles(sources, combined=False)[HVACMode.HEAT_COOL]) is (
        RangeHeatCoolProfile
    )


def test_single_target_profile() -> None:
    """Off uses the single target."""
    profile = ModeProfile(HVACMode.OFF, _sources())
    mapping = profile.target_map(None)
    assert mapping == {TEMP: TEMP}
    assert profile.source_modes() == (HVACMode.OFF,)
    assert profile.source_mode(HVACMode.HEAT) is HVACMode.OFF
    assert profile.shown_target(TEMP, mapping) == TEMP
    assert profile.shown_target(LOW, mapping) is None
    assert profile.target_source(LOW) is None
    assert profile.features == ClimateEntityFeature(0)


def test_fan_only_profile() -> None:
    """Fan only sends and shows no target."""
    profile = FanOnlyProfile(HVACMode.FAN_ONLY, _sources(RANGE, fan_only="climate.f"))
    mapping = profile.target_map(None)
    assert mapping == {}
    assert profile.source_mode(None) is HVACMode.FAN_ONLY
    for attr in (TEMP, LOW, HIGH):
        assert profile.shown_target(attr, mapping) is None
    assert profile.target_source(LOW) is None


def test_dry_profile() -> None:
    """Dry uses the single target when its source has one, else none."""
    profile = DryProfile(HVACMode.DRY, _sources(TARGET, dry="climate.d"))
    mapping = profile.target_map(None)
    assert mapping == {TEMP: TEMP}
    assert profile.shown_target(TEMP, mapping) == TEMP
    assert profile.shown_target(LOW, mapping) is None

    profile = DryProfile(HVACMode.DRY, _sources(RANGE, dry="climate.d"))
    mapping = profile.target_map(None)
    assert mapping == {}
    for attr in (TEMP, LOW, HIGH):
        # Even with the mapping of another mode (off shows the next mode).
        assert profile.shown_target(attr, {TEMP: TEMP}) is None


def test_auto_profile() -> None:
    """Auto uses low/high when its source has them, else the single target, else none."""
    profile = AutoProfile(HVACMode.AUTO, _sources(TARGET | RANGE, auto="climate.a"))
    mapping = profile.target_map(None)
    assert mapping == {LOW: LOW, HIGH: HIGH}
    assert profile.shown_target(TEMP, mapping) is None
    assert profile.shown_target(LOW, mapping) == LOW
    assert profile.shown_target(HIGH, mapping) == HIGH
    assert profile.target_source(LOW) == "climate.a"
    assert profile.target_source(TEMP) is None

    profile = AutoProfile(HVACMode.AUTO, _sources(TARGET, auto="climate.a"))
    mapping = profile.target_map(None)
    assert mapping == {TEMP: TEMP}
    assert profile.shown_target(TEMP, mapping) == TEMP
    assert profile.shown_target(LOW, mapping) is None
    assert profile.target_source(LOW) is None

    profile = AutoProfile(HVACMode.AUTO, _sources(0, auto="climate.a"))
    mapping = profile.target_map(None)
    assert mapping == {}
    for attr in (TEMP, LOW, HIGH):
        assert profile.shown_target(attr, {TEMP: TEMP}) is None


@pytest.mark.parametrize(("mode", "target"), [(HVACMode.HEAT, LOW), (HVACMode.COOL, HIGH)])
def test_setpoint_profile(mode: HVACMode, target: str) -> None:
    """Heat sends the low target as the single one, cool the high one."""
    profile = SetpointProfile(mode, _sources(**{str(mode): "climate.x"}))
    mapping = profile.target_map(None)
    assert mapping == {TEMP: target}
    assert profile.shown_target(TEMP, mapping) == target
    assert profile.shown_target(LOW, mapping) is None


def test_range_heat_cool_profile() -> None:
    """A heat_cool source gets low/high when it has them, else the single target."""
    profile = RangeHeatCoolProfile(HVACMode.HEAT_COOL, _sources(RANGE, heat_cool="climate.hc"))
    mapping = profile.target_map(None)
    assert mapping == {LOW: LOW, HIGH: HIGH}
    assert profile.shown_target(TEMP, mapping) is None
    assert profile.shown_target(LOW, mapping) == LOW
    assert profile.target_source(HIGH) == "climate.hc"

    profile = RangeHeatCoolProfile(HVACMode.HEAT_COOL, _sources(0, heat_cool="climate.hc"))
    mapping = profile.target_map(None)
    assert mapping == {TEMP: TEMP}
    assert profile.shown_target(TEMP, mapping) == TEMP
    assert profile.shown_target(HIGH, mapping) is None
    assert profile.target_source(HIGH) is None


def test_combined_heat_cool_profile() -> None:
    """The combined HEAT_COOL runs its phase, low to heat and high to cool."""
    sources = _sources(heat="climate.h", cool="climate.c")
    profile = CombinedHeatCoolProfile(HVACMode.HEAT_COOL, sources)
    assert profile.features == RANGE
    assert profile.source_modes() == (HVACMode.HEAT, HVACMode.COOL)
    assert profile.source_mode(HVACMode.COOL) is HVACMode.COOL
    assert profile.source_mode(None) is HVACMode.HEAT_COOL
    assert profile.target_map(HVACMode.HEAT) == {TEMP: LOW}
    assert profile.target_map(HVACMode.COOL) == {TEMP: HIGH}
    assert profile.target_map(None) == {TEMP: TEMP}
    mapping = profile.target_map(HVACMode.HEAT)
    assert profile.shown_target(TEMP, mapping) is None
    assert profile.shown_target(HIGH, mapping) == HIGH
    assert profile.shown_target(TEMP, {TEMP: TEMP}) == TEMP
    assert profile.target_source(LOW) == "climate.h"
    assert profile.target_source(HIGH) == "climate.c"


# Timer and CombinedPhase


async def test_timer(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """The action runs once after the delay, unless cancelled; start replaces."""
    fired: list[bool] = []

    def action() -> None:
        fired.append(timer.active)

    timer = Timer(hass)
    timer.start(timedelta(seconds=5), action)
    timer.start(timedelta(seconds=10), action)
    assert timer.active
    freezer.tick(6)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert fired == []
    freezer.tick(5)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    # Not active anymore while the action runs.
    assert fired == [False]

    timer.start(timedelta(seconds=5), action)
    timer.cancel()
    timer.cancel()
    freezer.tick(10)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert fired == [False]


async def test_phase_follows_source(hass: HomeAssistant) -> None:
    """The phase ends when its source leaves it, unless waiting or switching."""
    phase = CombinedPhase(hass, True, lambda: None)
    assert not phase.can_switch(False)

    phase.start(HVACMode.HEAT)
    assert phase.waiting
    assert not phase.can_switch(False)
    phase.update(HVACMode.OFF, lambda: True, switching=False)
    assert phase.phase is HVACMode.HEAT

    # The source shows the phase: the wait ends.
    phase.update(HVACMode.HEAT, lambda: True, switching=False)
    assert not phase.waiting
    assert phase.can_switch(False)
    assert not phase.can_switch(True)

    phase.update(HVACMode.OFF, lambda: True, switching=True)
    assert phase.phase is HVACMode.HEAT
    phase.update(HVACMode.AUTO, lambda: True, switching=False)
    assert phase.phase is None
    assert phase.as_dict() == {"heat_cool": False}


async def test_phase_held(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """A new phase is held for the minimum duration, unless forced."""
    fired: list[bool] = []
    phase = CombinedPhase(hass, True, lambda: fired.append(True), timedelta(minutes=10))
    phase.start(HVACMode.HEAT)
    phase.update(HVACMode.HEAT, lambda: True, switching=False)
    assert phase.holding
    assert not phase.can_switch(False)
    assert phase.can_switch(False, forced=True)

    freezer.tick(timedelta(minutes=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not phase.holding
    assert phase.can_switch(False)
    assert fired

    # Leaving the combined mode ends the hold.
    phase.start(HVACMode.COOL)
    phase.leave()
    assert not phase.holding

    # No minimum duration: not held.
    phase = CombinedPhase(hass, True, lambda: None)
    phase.start(HVACMode.HEAT)
    assert not phase.holding
    phase.leave()


async def test_phase_restore(hass: HomeAssistant) -> None:
    """After a restart, the phase comes back once its source runs."""
    phase = CombinedPhase(hass, True, lambda: None)
    phase.restore({"heat_cool": True})
    assert phase.as_dict() == {"heat_cool": True}
    phase.update(HVACMode.OFF, lambda: False, switching=False)
    assert phase.as_dict() == {"heat_cool": True}
    phase.update(HVACMode.COOL, lambda: False, switching=False)
    assert phase.phase is HVACMode.COOL

    # Sources usable and none runs: it was turned off.
    phase = CombinedPhase(hass, True, lambda: None)
    phase.restore({"heat_cool": True})
    phase.update(HVACMode.OFF, lambda: True, switching=False)
    assert phase.as_dict() == {"heat_cool": False}

    # Not combined: nothing to restore.
    phase = CombinedPhase(hass, False, lambda: None)
    phase.restore({"heat_cool": True})
    assert phase.as_dict() == {"heat_cool": False}

    phase.leave()
    assert phase.phase is None
