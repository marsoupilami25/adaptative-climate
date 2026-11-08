"""What each mode does with its sources and targets.

Each configured mode gets a profile, built once from the config by
build_profiles. The entity asks the profile of its mode instead of
testing the mode itself. A profile answers:

- source_modes: the source modes it uses.
- source_mode: the HVAC mode sent to the source.
- target_map: which target each target attribute of the source gets,
  as {source attribute: target}.
- shown_target: which target the entity shows in a target attribute.
- target_source: the only source a low/high target goes to, if any.
- features: what the mode adds to the entity, whatever its sources offer.

Profiles:
- ModeProfile: off. The single target goes to the single target of the
  source.
- FanOnlyProfile: fan only. No target: nothing is sent to the source,
  taken from it or shown; the targets are kept for the next mode.
- DryProfile: dry. The single target when its source has one, else no
  target (like fan only).
- AutoProfile: auto. The low/high targets when its source has them (like
  HEAT_COOL with its own source), else the single target (like dry), else
  no target (like fan only).
- SetpointProfile: heat sends the low target (heating setpoint) as the
  single target of its source, cool the high one (cooling setpoint).
- RangeHeatCoolProfile: HEAT_COOL with a source of its own. The source
  gets low/high when it has them, else the single target.
- CombinedHeatCoolProfile: HEAT_COOL without a source of its own. It
  runs the heat or cool source (its phase), sends the phase as the mode,
  the low target to the heat source and the high one to the cool source.
  The entity always shows low/high.

A new kind of mode is a new profile.
"""

from __future__ import annotations

from homeassistant.components.climate import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE

from ..const import MODE_SOURCE_KEYS
from .model import PHASES, SINGLE_TARGETS
from .sources import Sources

_RANGE = ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
_TARGET = ClimateEntityFeature.TARGET_TEMPERATURE


class ModeProfile:
    """A mode with a source of its own and the single target: OFF."""

    # Features the mode adds to the entity, whatever its sources offer.
    features = ClimateEntityFeature(0)

    def __init__(self, mode: HVACMode, sources: Sources) -> None:
        """Initialize the profile of a mode."""
        self.mode = mode
        self._sources = sources

    def source_modes(self) -> tuple[HVACMode, ...]:
        """Return the source modes the mode uses."""
        return (self.mode,)

    def source_mode(self, phase: HVACMode | None) -> HVACMode:
        """Return the mode sent to the source."""
        return self.mode

    def target_map(self, phase: HVACMode | None) -> dict[str, str]:
        """Return which target each target attribute of the source gets."""
        return {ATTR_TEMPERATURE: ATTR_TEMPERATURE}

    def shown_target(self, attr: str, mapping: dict[str, str]) -> str | None:
        """Return the target shown as a target attribute of the entity, if any.

        mapping is the target map of the current mode.
        """
        return ATTR_TEMPERATURE if attr == ATTR_TEMPERATURE else None

    def target_source(self, target: str) -> str | None:
        """Return the only source a low/high target goes to, if any."""
        return None


class FanOnlyProfile(ModeProfile):
    """Fan only: the fan alone, without target.

    The source gets no target, its targets are ignored and the entity shows
    none. The targets are kept for the next mode.
    """

    def target_map(self, phase: HVACMode | None) -> dict[str, str]:
        """Send no target."""
        return {}

    def shown_target(self, attr: str, mapping: dict[str, str]) -> str | None:
        """Show no target."""
        return None


class SourceTargetsProfile(ModeProfile):
    """A mode whose targets are those its source has (dry, auto).

    The low/high targets when the source has them and the mode uses them
    (use_range), else the single target when the source has it, else none.
    The targets are the same as in the other modes: one single target, one
    low and one high.
    """

    use_range = False

    def _targets(self) -> tuple[str, ...]:
        """Return the targets the source gets."""
        features = self._sources.features(self._sources.mode_sources[self.mode])
        if self.use_range and _RANGE in features:
            return (ATTR_TARGET_TEMP_LOW, ATTR_TARGET_TEMP_HIGH)
        if _TARGET in features:
            return (ATTR_TEMPERATURE,)
        return ()

    def target_map(self, phase: HVACMode | None) -> dict[str, str]:
        """Send the targets the source has."""
        return {target: target for target in self._targets()}

    def shown_target(self, attr: str, mapping: dict[str, str]) -> str | None:
        """Show the targets the source gets."""
        return attr if attr in self._targets() else None

    def target_source(self, target: str) -> str | None:
        """Low/high go to the source, when it gets them."""
        if target != ATTR_TEMPERATURE and target in self._targets():
            return self._sources.mode_sources[self.mode]
        return None


class DryProfile(SourceTargetsProfile):
    """Dry: the single target when its source has one, else no target."""


class AutoProfile(SourceTargetsProfile):
    """Auto: low/high when its source has them, else the single target, else none."""

    use_range = True


class SetpointProfile(ModeProfile):
    """Heat or cool: the single target of the source is the low or high target.

    Heat sends the low target (heating setpoint), cool the high one (cooling
    setpoint), like the phases of the combined HEAT_COOL.
    """

    def __init__(self, mode: HVACMode, sources: Sources) -> None:
        """Initialize the profile of heat or cool."""
        super().__init__(mode, sources)
        self.target = SINGLE_TARGETS[mode]

    def target_map(self, phase: HVACMode | None) -> dict[str, str]:
        """Send the setpoint as the single target."""
        return {ATTR_TEMPERATURE: self.target}

    def shown_target(self, attr: str, mapping: dict[str, str]) -> str | None:
        """Show the setpoint as the single target, no low/high."""
        return self.target if attr == ATTR_TEMPERATURE else None


class RangeHeatCoolProfile(ModeProfile):
    """HEAT_COOL with a source of its own.

    The source gets the low/high targets when it has them, else the single
    target.
    """

    def _has_range(self) -> bool:
        """Return True when the source has low/high targets."""
        return _RANGE in self._sources.features(self._sources.mode_sources[self.mode])

    def target_map(self, phase: HVACMode | None) -> dict[str, str]:
        """Send low/high when the source has them, else the single target."""
        if self._has_range():
            return {
                ATTR_TARGET_TEMP_LOW: ATTR_TARGET_TEMP_LOW,
                ATTR_TARGET_TEMP_HIGH: ATTR_TARGET_TEMP_HIGH,
            }
        return super().target_map(phase)

    def shown_target(self, attr: str, mapping: dict[str, str]) -> str | None:
        """Show the targets the source gets."""
        return attr if attr in mapping.values() else None

    def target_source(self, target: str) -> str | None:
        """Both low/high targets go to the source, when it has them."""
        return self._sources.mode_sources[self.mode] if self._has_range() else None


class CombinedHeatCoolProfile(ModeProfile):
    """HEAT_COOL without a source of its own: it runs the heat or cool source.

    The source it runs is its phase (see CombinedPhase). The low target goes
    to the heat source and the high one to the cool source, as their single
    target.
    """

    features = _RANGE

    def source_modes(self) -> tuple[HVACMode, ...]:
        """Use the heat and cool sources."""
        return PHASES

    def source_mode(self, phase: HVACMode | None) -> HVACMode:
        """Send the phase to its source."""
        return phase if phase is not None else self.mode

    def target_map(self, phase: HVACMode | None) -> dict[str, str]:
        """Send the setpoint of the phase as the single target."""
        if phase in SINGLE_TARGETS:
            return {ATTR_TEMPERATURE: SINGLE_TARGETS[phase]}
        return super().target_map(phase)

    def shown_target(self, attr: str, mapping: dict[str, str]) -> str | None:
        """Always show the low/high targets, no single target."""
        if attr == ATTR_TEMPERATURE:
            return attr if attr in mapping.values() else None
        return attr

    def target_source(self, target: str) -> str | None:
        """The low target goes to the heat source, the high one to the cool source."""
        phase = HVACMode.HEAT if target == ATTR_TARGET_TEMP_LOW else HVACMode.COOL
        return self._sources.mode_sources[phase]


def build_profiles(sources: Sources, combined: bool) -> dict[HVACMode, ModeProfile]:
    """Return the profile of each mode the entity offers, in display order."""
    profiles: dict[HVACMode, ModeProfile] = {}
    for mode in MODE_SOURCE_KEYS:
        profile: type[ModeProfile]
        if mode in sources.mode_sources:
            if mode is HVACMode.HEAT_COOL:
                profile = RangeHeatCoolProfile
            elif mode in SINGLE_TARGETS:
                profile = SetpointProfile
            elif mode is HVACMode.FAN_ONLY:
                profile = FanOnlyProfile
            elif mode is HVACMode.DRY:
                profile = DryProfile
            elif mode is HVACMode.AUTO:
                profile = AutoProfile
            else:
                profile = ModeProfile
        elif mode is HVACMode.HEAT_COOL and combined:
            profile = CombinedHeatCoolProfile
        else:
            continue
        profiles[mode] = profile(mode, sources)
    return profiles
