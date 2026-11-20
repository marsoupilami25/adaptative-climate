"""core/entity/targets: the gap applied again on the values sent (ENT-TGT-8, ENT-FEAT-4).

In the phase `cool` of a bi-source heat_cool, a source with low/high keeps high, the
target of the phase: the low target moves first. It only differs from the general rule
(the high target moves) when a takeover broke the gap of the kept targets, at a later
sending: called directly here.
"""

from __future__ import annotations

from custom_components.adaptative_climate.core.entity import targets
from custom_components.adaptative_climate.core.model.values import HIGH, LOW
from dev.unit.core.kit import Core, climate

HEATER = "climate.heater"
AIRCON = "climate.aircon"
RANGE = 2 | 128 | 256  # target_temp_low / target_temp_high, off, on


def aircon(state: str) -> object:
    return climate(
        state, ["cool"], min_temp=16.0, max_temp=30.0, temperature=None,
        target_temp_low=18.0, target_temp_high=22.0, supported_features=RANGE,
    )


def bi_source() -> Core:
    """A heater (single target) and an aircon with low/high in cool, cool discovered."""
    core = Core(
        {"heat_entity": HEATER, "cool_entity": AIRCON},
        snapshots={HEATER: climate("off", ["heat"], min_temp=18.0, max_temp=30.0),
                   AIRCON: aircon("off")},
    )
    core.start()
    core.change(AIRCON, aircon("cool"))  # cool discovered
    core.change(AIRCON, aircon("off"))
    return core


def test_ent_tgt_8_phase_cool_keeps_high_the_low_target_moves_first() -> None:
    core = bi_source()
    core.entity.stored.targets.update({LOW: 18.0, HIGH: 18.5})  # gap broken by a takeover
    sent = targets.send_values(core.entity, AIRCON, "cool", "cool", True)
    assert sent == {"target_temp_low": 17.5, "target_temp_high": 18.5}


def test_ent_tgt_8_mono_source_cool_the_high_target_moves() -> None:
    core = bi_source()
    core.entity.stored.targets.update({LOW: 18.0, HIGH: 18.5})
    sent = targets.send_values(core.entity, AIRCON, "cool", "cool", False)
    assert sent == {"target_temp_low": 18.0, "target_temp_high": 19.0}
