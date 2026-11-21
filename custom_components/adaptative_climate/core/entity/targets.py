"""Temperature targets of the AC entity (spec §1.3.5.3).

Kept on the scale of the entity (the reference); the offset is added only
when a target is sent to a source (ENT-TGT-1, ENT-TGT-8).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..model.values import (
    CASE_LOW_HIGH,
    CASE_SINGLE,
    CELSIUS,
    COOL,
    HEAT,
    HEAT_COOL,
    HIGH,
    LOW,
    SINGLE,
    TARGET_TEMP_HIGH,
    TARGET_TEMP_LOW,
    TARGETS,
    TEMPERATURE,
    clamp,
    clean,
    round_to_step,
)

if TYPE_CHECKING:
    from .entity import ACEntity

EPSILON = 1e-6


def single_target(label: str, phase: bool) -> str:
    """The target a source with a single temperature target gets (ENT-FEAT-4).

    T in a mono-source mode; in a phase of the bi-source heat_cool, low in
    `heat` and high in `cool`.
    """
    if not phase:
        return SINGLE
    return LOW if label == HEAT else HIGH


def _fit(value: float, rng: tuple[float, float], step: float) -> float:
    """On the step of the entity, within a range (rounded toward the inside)."""
    low, high = rng
    value = round_to_step(value, step)
    if value < low - EPSILON:
        value = round_to_step(low, step, 1)
    if value > high + EPSILON:
        value = round_to_step(high, step, -1)
    return clean(value)


def _too_close(entity: ACEntity) -> bool:
    """Low and high both kept, closer than min_gap (ENT-TGT-5)."""
    low, high = entity.stored.targets[LOW], entity.stored.targets[HIGH]
    return low is not None and high is not None and high - low < entity.entry.min_gap - EPSILON


def _push_other(entity: ACEntity, kept: str) -> None:
    """The target other than `kept` moves away from it to keep the gap (ENT-TGT-6, ENT-TGT-9).

    Rounded away from `kept`, on the step of the entity; it stops at the end
    of its range, and never moves toward `kept`.
    """
    cam = entity.cam
    step = cam.step()
    targets = entity.stored.targets
    gap = entity.entry.min_gap
    if kept == LOW:
        limit = round_to_step(cam.target_range(HIGH)[1], step, -1)
        targets[HIGH] = max(targets[HIGH], min(round_to_step(targets[LOW] + gap, step, 1), limit))
    else:
        limit = round_to_step(cam.target_range(LOW)[0], step, 1)
        targets[LOW] = min(targets[LOW], max(round_to_step(targets[HIGH] - gap, step, -1), limit))


def _give_way(entity: ACEntity, changed: str) -> None:
    """ENT-TGT-6: the target changed stops at the gap from the other one, within its range."""
    cam = entity.cam
    step = cam.step()
    targets = entity.stored.targets
    gap = entity.entry.min_gap
    if changed == LOW:
        low_min = round_to_step(cam.target_range(LOW)[0], step, 1)
        targets[LOW] = max(round_to_step(targets[HIGH] - gap, step, -1), low_min)
    else:
        high_max = round_to_step(cam.target_range(HIGH)[1], step, -1)
        targets[HIGH] = min(round_to_step(targets[LOW] + gap, step, 1), high_max)


def apply_gap(entity: ACEntity) -> None:
    """Keep low at least min_gap below high, both changed (ENT-TGT-5, ENT-TGT-6).

    High moves up, rounded away from low; at the end of its range, low moves
    down instead; if neither can, low goes to the minimum of its range and
    high to the maximum.
    """
    targets = entity.stored.targets
    low, high = targets[LOW], targets[HIGH]
    gap = entity.entry.min_gap
    if low is None or high is None or high - low >= gap - EPSILON:
        return
    cam = entity.cam
    step = cam.step()
    low_min = cam.target_range(LOW)[0]
    high_max = cam.target_range(HIGH)[1]
    new_high = round_to_step(low + gap, step, 1)
    if new_high <= high_max + EPSILON:
        targets[HIGH] = new_high
        return
    targets[HIGH] = round_to_step(high_max, step, -1)
    new_low = round_to_step(targets[HIGH] - gap, step, -1)
    targets[LOW] = max(new_low, round_to_step(low_min, step, 1))


def bring_in_line(entity: ACEntity) -> None:
    """ENT-TGT-4: rounded to the step, in the range of the target, gap applied again."""
    cam = entity.cam
    step = cam.step()
    targets = entity.stored.targets
    for name in TARGETS:
        if targets[name] is not None:
            targets[name] = _fit(targets[name], cam.target_range(name), step)
    if cam.has_low_high():
        apply_gap(entity)
    entity.save()


def user_set(entity: ACEntity, request: dict[str, Any]) -> bool:
    """ENT-TGT-7: targets set by the user. True when a target was set.

    A single `temperature` sets T, in every state.
    """
    cam = entity.cam
    step = cam.step()
    values: dict[str, float] = {}
    if TEMPERATURE in request:
        values[SINGLE] = request[TEMPERATURE]
    if TARGET_TEMP_LOW in request:
        values[LOW] = request[TARGET_TEMP_LOW]
    if TARGET_TEMP_HIGH in request:
        values[HIGH] = request[TARGET_TEMP_HIGH]
    if not values:
        return False
    targets = entity.stored.targets
    before, _ = shown(entity)
    changed = []
    for name, value in values.items():
        targets[name] = _fit(float(value), cam.target_range(name), step)
        attribute = {LOW: TARGET_TEMP_LOW, HIGH: TARGET_TEMP_HIGH}.get(name)
        if attribute is not None and (
            before[attribute] is None or abs(targets[name] - before[attribute]) > EPSILON
        ):
            changed.append(name)
    if cam.has_low_high() and (LOW in values or HIGH in values) and _too_close(entity):
        if len(changed) == 1:
            # ENT-TGT-6: the target changed is kept, the other one moves; else it gives way
            _push_other(entity, changed[0])
            if _too_close(entity):
                _give_way(entity, changed[0])
        else:
            apply_gap(entity)
    entity.save()
    return True


def takeover(entity: ACEntity, taken: dict[str, float]) -> set[str]:
    """ENT-TGT-9: a target changed on the active source becomes the target of the entity.

    Returns the targets moved for the gap.
    """
    cam = entity.cam
    step = cam.step()
    targets = entity.stored.targets
    for name, value in taken.items():
        targets[name] = round_to_step(value, step)  # kept even outside the ranges
    moved: set[str] = set()
    if cam.has_low_high() and len({LOW, HIGH} & taken.keys()) == 1 and _too_close(entity):
        # The other one moves; the target taken never gives way.
        kept = LOW if LOW in taken else HIGH
        other = HIGH if kept == LOW else LOW
        before = targets[other]
        _push_other(entity, kept)
        if targets[other] != before:
            moved.add(other)
    entity.save()
    return moved


def first_targets(entity: ACEntity) -> None:
    """ENT-TGT-10: the targets not stored are taken from the sources."""
    targets = entity.stored.targets
    if all(targets[name] is not None for name in TARGETS):
        return
    entry = entity.entry
    cam = entity.cam
    step = cam.step()

    def shown(source_id: str | None) -> dict[str, Any]:
        if source_id is None or not entity.source_state(source_id).available:
            return {}
        return entity.sources[source_id].settings

    def first(name: str) -> float | None:
        for source in entry.sources:
            settings = shown(source.entity_id)
            if name in settings:
                return settings[name] - source.offset
        return None

    found: dict[str, float | None] = {}
    if targets[SINGLE] is None:
        value = first(TEMPERATURE)
        if value is None:
            rng = cam.widest_range()
            value = (rng[0] + rng[1]) / 2
        found[SINGLE] = value
    if targets[LOW] is None or targets[HIGH] is None:
        low = first(TARGET_TEMP_LOW)
        high = first(TARGET_TEMP_HIGH)
        if entry.is_bi(HEAT_COOL):
            # The single targets of the phase sources (ENT-FEAT-4).
            for phase in (HEAT, COOL):
                if (low if phase == HEAT else high) is not None:
                    continue
                source_id = entry.phase_source(phase)
                settings = shown(source_id)
                if TEMPERATURE in settings:
                    value = settings[TEMPERATURE] - entry.offset_of(source_id)
                    if phase == HEAT:
                        low = value
                    else:
                        high = value
        single = targets[SINGLE] if targets[SINGLE] is not None else found[SINGLE]
        degree = 1.0 if entry.unit == CELSIUS else 2.0
        found[LOW] = low if low is not None else single - degree
        found[HIGH] = high if high is not None else single + degree
    for name, value in found.items():
        if targets[name] is None and value is not None:
            targets[name] = _fit(value, cam.target_range(name), step)
    if cam.has_low_high():
        apply_gap(entity)
    entity.save()


def send_values(
    entity: ACEntity, source_id: str, mode: str, label: str, phase: bool
) -> dict[str, float]:
    """ENT-TGT-8: the targets sent to a source in a source mode, on its scale."""
    cam = entity.cam
    case = cam.case(source_id, mode)
    if case not in (CASE_SINGLE, CASE_LOW_HIGH):
        return {}
    targets = entity.stored.targets
    low_range, high_range = cam.context_range(source_id, mode, shown=False)  # never a guess (ENT-CAP-5)
    offset = entity.entry.offset_of(source_id)
    step = cam.source_step(source_id, mode)
    raw_min, raw_max = cam.raw_range(source_id, mode)

    def out(value: float, direction: int = 0) -> float:
        result = round_to_step(value + offset, step, direction)
        if result < raw_min - EPSILON:
            result = round_to_step(raw_min, step, 1)
        if result > raw_max + EPSILON:
            result = round_to_step(raw_max, step, -1)
        return clean(result)

    if case == CASE_SINGLE:
        value = targets[single_target(label, phase)]
        if value is None:
            # Safety net (not reached): every target has a value once in OPER (ENT-TGT-10)
            return {}
        return {TEMPERATURE: out(clamp(value, low_range, high_range))}
    low, high = targets[LOW], targets[HIGH]
    if low is None or high is None:
        # Safety net (not reached): every target has a value once in OPER (ENT-TGT-10)
        return {}
    low = clamp(low, low_range, high_range)
    high = clamp(high, low_range, high_range)
    gap = entity.entry.min_gap
    moved = None
    if high - low < gap - EPSILON:
        if high_range - low_range < gap:
            low, high = low_range, high_range
        elif phase and label == COOL:
            # Phase cool of the bi-source heat_cool: high, the target of the phase, is kept
            low, moved = high - gap, LOW
            if low < low_range:
                low, high, moved = low_range, low_range + gap, HIGH
        else:
            high, moved = low + gap, HIGH
            if high > high_range:
                high, low, moved = high_range, high_range - gap, LOW
    return {
        TARGET_TEMP_LOW: out(low, -1 if moved == LOW else 0),
        TARGET_TEMP_HIGH: out(high, 1 if moved == HIGH else 0),
    }


def shown(entity: ACEntity) -> tuple[dict[str, float | None], list[dict[str, Any]]]:
    """ENT-TGT-11, ENT-TGT-12, ENT-TGT-13: targets shown, and target_gaps."""
    cam = entity.cam
    targets = entity.stored.targets
    mode = entity.stm.operating_mode()
    if mode is not None:
        mapping = cam.mode_targets(mode)
        ranges = dict.fromkeys(mapping.values(), cam.mode_range(mode))
    else:
        if cam.has_low_high():
            mapping = {TARGET_TEMP_LOW: LOW, TARGET_TEMP_HIGH: HIGH}
        else:
            mapping = cam.mode_targets(entity.turn_on_mode())
        ranges = {name: cam.target_range(name) for name in mapping.values()}
    values: dict[str, float | None] = dict.fromkeys(
        (TEMPERATURE, TARGET_TEMP_LOW, TARGET_TEMP_HIGH)
    )
    gaps: list[dict[str, Any]] = []
    for attribute, name in mapping.items():
        saved = targets[name]
        if saved is None:
            # Safety net (not reached): every target has a value once in OPER (ENT-TGT-10)
            continue
        value = clean(clamp(saved, *ranges[name]))
        values[attribute] = value
        if abs(value - saved) > EPSILON:
            gaps.append({"attribute": attribute, "saved": saved, "shown": value})
    return values, gaps
