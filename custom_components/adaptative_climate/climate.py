"""Climate platform for Adaptative Climate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import math
from typing import Any

from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_SWING_HORIZONTAL_MODE,
    ATTR_SWING_HORIZONTAL_MODES,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TARGET_TEMP_STEP,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_SWING_HORIZONTAL_MODE,
    SERVICE_SET_SWING_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate.const import DEFAULT_MAX_TEMP, DEFAULT_MIN_TEMP
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    ATTR_TEMPERATURE,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.restore_state import RestoredExtraData, RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from homeassistant.util.unit_conversion import TemperatureConverter

from .const import (
    CONF_MAX_TEMP,
    CONF_MIN_GAP,
    CONF_MIN_TEMP,
    DOMAIN,
    MODE_SOURCE_KEYS,
    entry_settings,
)
from .coordinator import AdaptativeClimateConfigEntry, AdaptativeClimateCoordinator

_LOGGER = logging.getLogger(__name__)

# Features this entity implements. Other features of the sources
# (presets, humidity...) are dropped: exposing them without implementing
# them makes Home Assistant fail when the entity is added.
SOURCE_FEATURES = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
)

# Targets kept by the entity, named like the source attributes. The low target
# is the heating setpoint and the high target the cooling setpoint: the single
# target of heat is the low one, the one of cool the high one, and HEAT_COOL
# shows both. The single target only serves the other modes (auto, dry...).
TARGETS = (ATTR_TEMPERATURE, ATTR_TARGET_TEMP_LOW, ATTR_TARGET_TEMP_HIGH)

# Target behind the single target, in the modes that have a setpoint.
SINGLE_TARGETS = {
    HVACMode.HEAT: ATTR_TARGET_TEMP_LOW,
    HVACMode.COOL: ATTR_TARGET_TEMP_HIGH,
}

# Feature a source needs to get a target attribute.
TARGET_FEATURES = {
    ATTR_TEMPERATURE: ClimateEntityFeature.TARGET_TEMPERATURE,
    ATTR_TARGET_TEMP_LOW: ClimateEntityFeature.TARGET_TEMPERATURE_RANGE,
    ATTR_TARGET_TEMP_HIGH: ClimateEntityFeature.TARGET_TEMPERATURE_RANGE,
}

# Name of each target in the saved data.
SAVED_TARGETS = {
    ATTR_TEMPERATURE: "target_temperature",
    ATTR_TARGET_TEMP_LOW: "target_temperature_low",
    ATTR_TARGET_TEMP_HIGH: "target_temperature_high",
}

# Modes the combined HEAT_COOL switches between.
PHASES = (HVACMode.HEAT, HVACMode.COOL)


@dataclass(frozen=True)
class Setting:
    """A fan or swing setting, taken from the source of the current mode."""

    feature: ClimateEntityFeature
    # Attribute holding the value, also the field of the service call.
    attr: str
    # Attribute listing the options.
    options_attr: str
    service: str


# Settings taken from the source of the current mode only: a heater has no
# fan, an AC has one. Each mode remembers them (see _observe_settings).
SETTINGS: tuple[Setting, ...] = (
    Setting(
        ClimateEntityFeature.FAN_MODE,
        ATTR_FAN_MODE,
        ATTR_FAN_MODES,
        SERVICE_SET_FAN_MODE,
    ),
    Setting(
        ClimateEntityFeature.SWING_MODE,
        ATTR_SWING_MODE,
        ATTR_SWING_MODES,
        SERVICE_SET_SWING_MODE,
    ),
    Setting(
        ClimateEntityFeature.SWING_HORIZONTAL_MODE,
        ATTR_SWING_HORIZONTAL_MODE,
        ATTR_SWING_HORIZONTAL_MODES,
        SERVICE_SET_SWING_HORIZONTAL_MODE,
    ),
)

# Memory key shared by the synchronized modes. Other modes use their own name.
SYNC_KEY = "sync"

# After a source enters a mode, it may report its own target for that mode
# late, in a later update: until the source shows the target sent to it, or
# during this time at most, the targets it shows are ignored. Integrations
# polling the device usually refresh right after a command, then at most
# every 10 s (Home Assistant debounce of refresh requests).
SETTLE_TIME = timedelta(seconds=12)

# Remembered settings: memory key -> setting attribute -> value.
type SettingsMemory = dict[str, dict[str, str]]

# What the targets are sent for: the mode, and the phase of the combined
# HEAT_COOL (None otherwise).
type TargetKey = tuple[HVACMode, HVACMode | None]

async def async_setup_entry(
    hass: HomeAssistant,
    entry: AdaptativeClimateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Adaptative Climate entities from a config entry."""
    async_add_entities([AdaptativeClimateEntity(entry.runtime_data)])


def _match_option(options: list[Any], value: str) -> str | None:
    """Return the option equal to value, ignoring case, as the source spells it."""
    wanted = value.lower()
    return next(
        (option for option in options if isinstance(option, str) and option.lower() == wanted),
        None,
    )


def _same_value(a: Any, b: Any) -> bool:
    """Return True when two setting values are equal, ignoring case."""
    if isinstance(a, str) and isinstance(b, str):
        return a.lower() == b.lower()
    return a == b


def _parse_targets(data: dict[str, Any]) -> dict[str, float | None]:
    """Read the targets saved before a restart, dropping bad values."""
    targets: dict[str, float | None] = {}
    for target, name in SAVED_TARGETS.items():
        value = data.get(name)
        valid = isinstance(value, (int, float)) and not isinstance(value, bool)
        targets[target] = float(value) if valid else None
    return targets


def _same_temperature(a: Any, b: Any) -> bool:
    """Return True when two temperatures are equal, ignoring float noise."""
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return False
    return math.isclose(a, b, abs_tol=1e-6)


def _changed(a: Any, b: Any) -> bool:
    """Return True when a target reading changed."""
    return a != b and not _same_temperature(a, b)


def _is_number(value: Any) -> bool:
    """Return True for a number (not a boolean)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_memory(data: dict[str, Any]) -> SettingsMemory:
    """Read the remembered settings saved before a restart, dropping bad values."""
    raw = data.get("memory")
    if not isinstance(raw, dict):
        return {}
    attrs = {setting.attr for setting in SETTINGS}
    return {
        key: {
            attr: value
            for attr, value in values.items()
            if attr in attrs and isinstance(value, str)
        }
        for key, values in raw.items()
        if isinstance(values, dict)
    }


class AdaptativeClimateEntity(
    CoordinatorEntity[AdaptativeClimateCoordinator],
    ClimateEntity,
    RestoreEntity,
):
    """Climate entity driving one source climate entity per mode.

    The current mode is read from the sources: the entity is in a mode when
    the source of that mode is in the HVAC mode of the same name. Otherwise
    it is off.

    Without a heat_cool source, HEAT_COOL uses the heat and cool sources: it
    runs one of them (its phase), chosen from the room temperature and the
    low/high targets. That mode cannot be read from the sources, so the
    entity keeps it (see _update_phase).

    Each mode remembers its fan and swing settings and sends them back to its
    source when the entity switches to it. The synchronized modes share one
    memory, which only keeps values that all their sources accept.

    The targets belong to this entity, not to the sources: they are sent to
    the source of each mode the entity enters, rounded to the step of that
    source and kept in its range (see _observe_targets). It keeps two
    setpoints, heating (low) and cooling (high), and exposes them as the
    single target of heat and cool, and as low/high in HEAT_COOL. The low
    setpoint stays at least the configured gap below the high one.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: AdaptativeClimateCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._entry = coordinator.config_entry
        self._mode_sources = coordinator.mode_sources
        self._combined = coordinator.combined_heat_cool
        self._attr_unique_id = self._entry.entry_id
        self._attr_name = self._entry.title
        # Mode restored by turn_on. Kept in memory only.
        self._last_on_mode: HVACMode | None = None
        # Fan and swing settings of each mode, kept across restarts.
        self._memory: SettingsMemory = {}
        # Target key and readings of the active source at the last update,
        # to tell a mode change from a change within the mode.
        self._observed: tuple[TargetKey, dict[str, Any]] | None = None
        # Mode being switched to by this entity, while it is in progress.
        self._switching_to: HVACMode | None = None
        # Targets wanted by the user, kept across restarts. The sources
        # receive them rounded and in their range, but they stay as they are.
        self._targets: dict[str, float | None] = dict.fromkeys(TARGETS)
        # Settle time after entering a mode (see SETTLE_TIME): cancels its
        # timer, None outside of it.
        self._settle_cancel: CALLBACK_TYPE | None = None
        # A target was sent to the source during the settle time, so the
        # source showing it confirms the mode.
        self._settle_sent = False
        # The source showed another target during the settle time.
        self._settle_received = False
        # Combined HEAT_COOL: the mode its source runs in (heat or cool),
        # None outside of it.
        self._phase: HVACMode | None = None
        # After this entity switches the phase, the sources may still show
        # the previous one for a while: cancels the timer of that wait.
        self._phase_wait_cancel: CALLBACK_TYPE | None = None
        # The combined HEAT_COOL was on before a restart: it is restored once
        # the heat and cool sources are usable (see _update_phase).
        self._restore_phase = False
        # The next state write is sent even when nothing changed (see
        # async_set_temperature).
        self._force_write = False

    async def async_added_to_hass(self) -> None:
        """Restore the remembered settings, the targets and the combined mode."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_extra_data()) is not None:
            data = last.as_dict()
            self._memory = _parse_memory(data)
            self._targets = _parse_targets(data)
            self._restore_phase = self._combined and data.get("heat_cool") is True
        self._update_phase()
        self._observe_sources()

    async def async_will_remove_from_hass(self) -> None:
        """Stop the timers."""
        self._end_settle()
        self._end_phase_wait()
        await super().async_will_remove_from_hass()

    @property
    def extra_restore_state_data(self) -> RestoredExtraData:
        """Save the remembered settings of the configured modes and the targets."""
        sync = self.coordinator.sync_modes
        keys = {str(mode) for mode in self._mode_sources if mode not in sync}
        if sync:
            keys.add(SYNC_KEY)
        return RestoredExtraData(
            {
                "memory": {
                    key: values
                    for key, values in self._memory.items()
                    if key in keys and values
                },
                **{
                    name: self._targets[target]
                    for target, name in SAVED_TARGETS.items()
                },
                "heat_cool": self._phase is not None or self._restore_phase,
            }
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Follow the sources, then update state."""
        self._update_phase()
        mode = self._current_mode()
        if mode is not HVACMode.OFF:
            self._last_on_mode = mode
        self._observe_sources()
        self._check_phase()
        super()._handle_coordinator_update()

    # Remembered settings

    def _memory_key(self, mode: HVACMode) -> str:
        """Return the memory key of a mode: shared by the synchronized modes."""
        return SYNC_KEY if mode in self.coordinator.sync_modes else str(mode)

    def _setting_options(self, entity_id: str | None, setting: Setting) -> list[Any]:
        """Return the options a source offers for a setting (empty when none)."""
        if setting.feature not in self._source_features(entity_id):
            return []
        return self._attr_from(entity_id, setting.options_attr) or []

    def _common_options(self, setting: Setting) -> set[str]:
        """Return the options, in lower case, shared by the synchronized sources.

        Only the usable sources that offer the setting count: a radiator
        without a fan does not empty the fan options of the others.
        """
        common: set[str] | None = None
        entity_ids = {self._mode_sources[mode] for mode in self.coordinator.sync_modes}
        for entity_id in entity_ids:
            options = self._setting_options(entity_id, setting)
            if not options:
                continue
            lowered = {option.lower() for option in options if isinstance(option, str)}
            common = lowered if common is None else common & lowered
        return common or set()

    def _can_remember(self, mode: HVACMode, setting: Setting, value: Any) -> bool:
        """Return True when a value can be remembered for a mode.

        A synchronized mode only keeps values that all synchronized sources
        accept, so the shared value can always be sent back to them.
        """
        if not isinstance(value, str):
            return False
        if mode not in self.coordinator.sync_modes:
            return True
        return value.lower() in self._common_options(setting)

    @callback
    def _observe_sources(self) -> None:
        """Follow the active source: its settings and its targets.

        Nothing is taken from the sources while the entity is off.
        """
        self._init_targets()

        mode = self._current_mode()
        if mode is HVACMode.OFF:
            self._observed = None
            self._end_settle()
            return

        source_mode = self._source_mode(mode)
        if self._running_mode() != source_mode:
            # Combined HEAT_COOL: the source does not show the phase yet.
            self._observed = None
            self._end_settle()
            return

        source = self._mode_sources[source_mode]
        key = self._target_key()
        values = {setting.attr: self._attr_from(source, setting.attr) for setting in SETTINGS}
        for target in TARGETS:
            values[target] = self._attr_from(source, target)
        previous = self._observed
        self._observed = (key, values)
        # While switching, the source may still show the previous mode.
        if self._switching_to is not None and mode != self._switching_to:
            return

        before = None if previous is None or previous[0] != key else previous[1]
        self._observe_settings(source_mode, values, before)
        self._observe_targets(key, source, values, before)

    @callback
    def _observe_settings(
        self, mode: HVACMode, values: dict[str, Any], before: dict[str, Any] | None
    ) -> None:
        """Remember the settings of the active source.

        Entering a mode (before is None) only fills a memory that is still
        empty: the source may still show its own settings before they are
        sent back. Within a mode, every setting change is remembered,
        wherever it comes from.
        """
        memory = self._memory.setdefault(self._memory_key(mode), {})
        for setting in SETTINGS:
            value = values[setting.attr]
            if before is None:
                if setting.attr in memory:
                    continue
            elif value == before[setting.attr]:
                continue
            # The same value in another case (sent back to a source) is kept as is.
            if self._can_remember(mode, setting, value) and not _same_value(
                memory.get(setting.attr), value
            ):
                memory[setting.attr] = value

    @callback
    def _observe_targets(
        self,
        key: TargetKey,
        source: str,
        values: dict[str, Any],
        before: dict[str, Any] | None,
    ) -> None:
        """Send the targets to a source entering its mode, or take a change made on it.

        Entering a mode (by this entity or elsewhere) starts the settle time
        and sends the targets once the source shows the mode. During the
        settle time, the targets of the source are ignored: it may report
        its own targets for the mode, late. The source showing the targets
        sent to it ends the settle time. Otherwise, at its end, the targets
        are sent again if the source showed others in the meantime. If it
        showed nothing, nothing is sent.

        Outside the settle time, a target changed on the source becomes the
        target of this entity, unless it is the value sent to it (rounded
        and in its range).
        """
        if before is None:
            self._start_settle(key)
            self._schedule_send_targets(key)
            return
        mapping = self._target_map()
        changed = [attr for attr in mapping if _changed(values[attr], before[attr])]
        if self._settle_cancel is not None:
            if self._settle_sent and all(
                _same_temperature(values[attr], self._applied(target, source))
                for attr, target in mapping.items()
            ):
                self._end_settle()
            elif changed:
                self._settle_received = True
            return
        for attr in changed:
            value = values[attr]
            target = mapping[attr]
            if not _is_number(value) or _same_temperature(
                value, self._applied(target, source)
            ):
                continue
            # The user took over from the source: it is kept as is, even
            # outside the range or the limits of this entity.
            self._targets[target] = float(value)

    @callback
    def _start_settle(self, key: TargetKey) -> None:
        """Start the settle time of a mode just entered."""
        self._end_settle()

        @callback
        def _settled(_now: datetime) -> None:
            self._settle_cancel = None
            received = self._settle_received
            self._end_settle()
            if received:
                self._schedule_send_targets(key)
            self.async_write_ha_state()

        self._settle_cancel = async_call_later(self.hass, SETTLE_TIME, _settled)

    @callback
    def _end_settle(self) -> None:
        """End the settle time, if any."""
        if self._settle_cancel is not None:
            self._settle_cancel()
            self._settle_cancel = None
        self._settle_sent = False
        self._settle_received = False

    @callback
    def _schedule_send_targets(self, key: TargetKey) -> None:
        """Send the targets to the active source, without waiting."""
        self._entry.async_create_task(
            self.hass,
            self._async_send_targets(key),
            f"{DOMAIN} temperature {self._active_source}",
        )

    @callback
    def _init_targets(self) -> None:
        """Set the first targets, once a source is usable.

        The single target comes from a source, else the middle of the range.
        The low target (heating setpoint) comes from the heat source, the high
        one from the cool source. A heat_cool source with low/high targets
        comes first; without any source, they are 1 degree around the single
        target.
        """
        if self._display_source is None:
            return
        active = self._active_source
        entity_ids = [active] if active else self.coordinator.source_entity_ids
        if self._targets[ATTR_TEMPERATURE] is None:
            low, high = self._temperature_range()
            self._targets[ATTR_TEMPERATURE] = next(
                (
                    float(value)
                    for entity_id in entity_ids
                    if _is_number(value := self._attr_from(entity_id, ATTR_TEMPERATURE))
                ),
                (low + high) / 2,
            )
        if (
            self._targets[ATTR_TARGET_TEMP_LOW] is not None
            and self._targets[ATTR_TARGET_TEMP_HIGH] is not None
        ):
            return
        heat_cool = self._mode_sources.get(HVACMode.HEAT_COOL)
        own = self._source_pair([heat_cool] if heat_cool else [])
        other = self._source_pair(self.coordinator.source_entity_ids)
        single = self._targets[ATTR_TEMPERATURE]
        for index, (target, mode, fallback) in enumerate(
            (
                (ATTR_TARGET_TEMP_LOW, HVACMode.HEAT, single - 1),
                (ATTR_TARGET_TEMP_HIGH, HVACMode.COOL, single + 1),
            )
        ):
            if self._targets[target] is not None:
                continue
            value = self._attr_from(self._mode_sources.get(mode), ATTR_TEMPERATURE)
            if own is not None:
                value = own[index]
            elif not _is_number(value):
                value = other[index] if other is not None else fallback
            self._targets[target] = float(value)

    def _source_pair(self, entity_ids: list[str]) -> tuple[float, float] | None:
        """Return the low/high targets of the first source that has both."""
        for entity_id in entity_ids:
            low = self._attr_from(entity_id, ATTR_TARGET_TEMP_LOW)
            high = self._attr_from(entity_id, ATTR_TARGET_TEMP_HIGH)
            if _is_number(low) and _is_number(high) and low <= high:
                return float(low), float(high)
        return None

    def _applied(self, target: str, entity_id: str | None) -> float | None:
        """Return a target as a source gets it (see _fit)."""
        value = self._targets[target]
        return None if value is None else self._fit(value, entity_id)

    def _fit(self, value: float, entity_id: str | None) -> float:
        """Return a value as a source gets it: rounded to its step, in its range.

        Without a source (entity off), the value is only kept in the range
        of the entity.
        """
        if entity_id is None:
            low, high = self._temperature_range()
        else:
            low, high = self._limited_range([entity_id])
            step = self._attr_from(entity_id, ATTR_TARGET_TEMP_STEP)
            if isinstance(step, (int, float)) and step > 0:
                value = round(math.floor(value / step + 0.5) * step, 6)
        return min(max(value, low), high)

    def _target_source(self, target: str) -> str | None:
        """Return the only source a low/high target goes to, if any.

        The combined HEAT_COOL sends the low target to the heat source and
        the high one to the cool source; a heat_cool source with low/high
        targets gets both. The single target goes to several sources: None.
        """
        if target == ATTR_TEMPERATURE:
            return None
        if self._combined:
            phase = HVACMode.HEAT if target == ATTR_TARGET_TEMP_LOW else HVACMode.COOL
            return self._mode_sources[phase]
        source = self._mode_sources.get(HVACMode.HEAT_COOL)
        if ClimateEntityFeature.TARGET_TEMPERATURE_RANGE in self._source_features(source):
            return source
        return None

    def _target_key(self) -> TargetKey:
        """Return what the targets are sent for: the mode and the combined phase."""
        mode = self._current_mode()
        return (mode, self._phase if mode is HVACMode.HEAT_COOL else None)

    def _target_map(self) -> dict[str, str]:
        """Return which target each target attribute of the active source gets.

        Heat sends the low target (heating setpoint) and cool the high one
        (cooling setpoint) as the single target of their source, like the
        phases of the combined HEAT_COOL. A heat_cool source gets the
        low/high targets when it has them. The other modes get the single
        target.
        """
        mode = self._current_mode()
        if mode in SINGLE_TARGETS:
            return {ATTR_TEMPERATURE: SINGLE_TARGETS[mode]}
        if mode is HVACMode.HEAT_COOL:
            if self._phase is HVACMode.HEAT:
                return {ATTR_TEMPERATURE: ATTR_TARGET_TEMP_LOW}
            if self._phase is HVACMode.COOL:
                return {ATTR_TEMPERATURE: ATTR_TARGET_TEMP_HIGH}
            features = self._source_features(self._active_source)
            if ClimateEntityFeature.TARGET_TEMPERATURE_RANGE in features:
                return {
                    ATTR_TARGET_TEMP_LOW: ATTR_TARGET_TEMP_LOW,
                    ATTR_TARGET_TEMP_HIGH: ATTR_TARGET_TEMP_HIGH,
                }
        return {ATTR_TEMPERATURE: ATTR_TEMPERATURE}

    async def _async_send_targets(self, key: TargetKey) -> None:
        """Send the targets to the active source, if its mode is still on.

        A source without these targets (fan only) gets nothing, and they are
        kept for the next mode. A source error is logged without failing.
        """
        if (
            key[0] is HVACMode.OFF
            or self._target_key() != key
            or self._running_mode() != self._source_mode(key[0])
        ):
            return
        entity_id = self._active_source
        mapping = self._target_map()
        features = self._source_features(entity_id)
        data: dict[str, float] = {}
        for attr, target in mapping.items():
            applied = self._applied(target, entity_id)
            if TARGET_FEATURES[attr] in features and applied is not None:
                data[attr] = applied
        # Low and high targets go together.
        if len(data) < len(mapping) or all(
            _same_temperature(self._attr_from(entity_id, attr), value)
            for attr, value in data.items()
        ):
            return
        # Set first: the source may show the targets before the call returns.
        if self._settle_cancel is not None:
            self._settle_sent = True
        try:
            await self.hass.services.async_call(
                CLIMATE_DOMAIN,
                "set_temperature",
                {**data, ATTR_ENTITY_ID: entity_id},
                blocking=True,
            )
        except HomeAssistantError as err:
            _LOGGER.warning(
                "Could not set %s on %s: %s",
                ", ".join(f"{attr} {value}" for attr, value in data.items()),
                entity_id,
                err,
            )

    # Combined HEAT_COOL

    def _room_temperature(self) -> float | None:
        """Return the room temperature: the sensor, else the display source."""
        sensor = self.coordinator.temperature_sensor
        state = (self.coordinator.data or {}).get(sensor) if sensor else None
        if state is not None:
            try:
                value = float(state.state)
            except ValueError:
                pass
            else:
                if math.isfinite(value):
                    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
                    wanted = self.hass.config.units.temperature_unit
                    if unit in TemperatureConverter.VALID_UNITS and unit != wanted:
                        value = TemperatureConverter.convert(value, unit, wanted)
                    return value
        value = self._attr_from_display(ATTR_CURRENT_TEMPERATURE)
        return float(value) if _is_number(value) else None

    def _wanted_phase(self, current: HVACMode | None) -> HVACMode:
        """Return the phase the combined HEAT_COOL should run in.

        Below the low target: heat. Above the high target: cool. In between,
        the current phase is kept; when entering (current is None), the phase
        of the closest target. Without room temperature, the current phase,
        else the heat or cool source already running, else heat.
        """
        temperature = self._room_temperature()
        low = self._targets[ATTR_TARGET_TEMP_LOW]
        high = self._targets[ATTR_TARGET_TEMP_HIGH]
        if temperature is not None and low is not None and high is not None:
            if temperature < low:
                return HVACMode.HEAT
            if temperature > high:
                return HVACMode.COOL
            if current is None:
                return HVACMode.HEAT if temperature - low <= high - temperature else HVACMode.COOL
        if current is not None:
            return current
        running = self._running_mode()
        return running if running in PHASES else HVACMode.HEAT

    @callback
    def _update_phase(self) -> None:
        """Leave the combined HEAT_COOL when its source left the phase elsewhere.

        The source has the upper hand: another mode or off set on it ends
        the combined mode. While the sources may still show the previous
        phase (see _start_phase), this is not judged.

        After a restart, the combined mode comes back with the phase its
        source runs in, once the sources are usable.
        """
        if self._restore_phase:
            running = self._running_mode()
            if running in PHASES:
                self._phase = running
                self._restore_phase = False
            elif self._mode_usable(HVACMode.HEAT_COOL):
                # Both sources are usable and none runs: it was turned off.
                self._restore_phase = False
        if self._phase is None:
            return
        if self._running_mode() == self._phase:
            self._end_phase_wait()
            return
        if self._phase_wait_cancel is not None or self._switching_to is not None:
            return
        self._phase = None

    @callback
    def _check_phase(self) -> None:
        """Switch the combined HEAT_COOL to the phase the temperature asks for."""
        if (
            self._phase is None
            or self._phase_wait_cancel is not None
            or self._switching_to is not None
        ):
            return
        phase = self._wanted_phase(self._phase)
        if phase != self._phase:
            self._start_phase(phase)
            self._entry.async_create_task(
                self.hass,
                self._async_switch_phase(phase),
                f"{DOMAIN} phase {phase}",
            )

    @callback
    def _start_phase(self, phase: HVACMode) -> None:
        """Set the phase and wait for the sources to show it."""
        self._phase = phase
        self._end_phase_wait()

        @callback
        def _waited(_now: datetime) -> None:
            self._phase_wait_cancel = None
            self._update_phase()
            self._observe_sources()
            self._check_phase()
            self.async_write_ha_state()

        self._phase_wait_cancel = async_call_later(self.hass, SETTLE_TIME, _waited)

    @callback
    def _end_phase_wait(self) -> None:
        """Stop waiting for the sources to show the phase."""
        if self._phase_wait_cancel is not None:
            self._phase_wait_cancel()
            self._phase_wait_cancel = None

    @callback
    def _leave_phase(self) -> None:
        """Leave the combined HEAT_COOL."""
        self._phase = None
        self._end_phase_wait()

    async def _async_switch_phase(self, phase: HVACMode) -> None:
        """Run the source of a new phase, if the phase did not change since."""
        if self._phase != phase:
            return
        try:
            await self._async_activate(phase, HVACMode.HEAT_COOL)
        except HomeAssistantError as err:
            _LOGGER.warning("Could not switch %s to %s: %s", self.entity_id, phase, err)
        self._observe_sources()
        self.async_write_ha_state()

    async def _async_send_settings(self, mode: HVACMode, entity_id: str) -> None:
        """Send the remembered settings of a mode to its source.

        A value the source does not offer, or already has, is not sent. A
        shared value that is no longer common (the sources changed) is
        replaced by the current value of the source, when it can be
        remembered. A source error is logged without failing the mode change.
        """
        memory = self._memory.get(self._memory_key(mode), {})
        for setting in SETTINGS:
            value = memory.get(setting.attr)
            if value is None:
                continue
            if mode in self.coordinator.sync_modes and (
                value.lower() not in self._common_options(setting)
            ):
                del memory[setting.attr]
                current = self._attr_from(entity_id, setting.attr)
                if self._can_remember(mode, setting, current):
                    memory[setting.attr] = current
                continue
            option = _match_option(self._setting_options(entity_id, setting), value)
            if option is None or _same_value(
                self._attr_from(entity_id, setting.attr), option
            ):
                continue
            try:
                await self.hass.services.async_call(
                    CLIMATE_DOMAIN,
                    setting.service,
                    {setting.attr: option, ATTR_ENTITY_ID: entity_id},
                    blocking=True,
                )
            except HomeAssistantError as err:
                _LOGGER.warning(
                    "Could not restore %s %s on %s: %s",
                    setting.attr,
                    option,
                    entity_id,
                    err,
                )

    # Source helpers

    def _state(self, entity_id: str | None) -> State | None:
        """Return the state of a source entity, if it is usable."""
        if entity_id is None or not self.coordinator.data:
            return None
        state = self.coordinator.data.get(entity_id)
        if state is None or state.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
            return None
        return state

    def _running_mode(self) -> HVACMode:
        """Return the mode whose source runs in that mode, else OFF.

        When several do, the source turned on last wins (it is about to turn
        the others off), then the first mode in order.
        """
        running = [
            (mode, entity_id)
            for mode, entity_id in self._mode_sources.items()
            if (state := self._state(entity_id)) is not None and state.state == mode
        ]
        for mode, entity_id in running:
            if entity_id == self.coordinator.last_on_source:
                return mode
        return running[0][0] if running else HVACMode.OFF

    def _current_mode(self) -> HVACMode:
        """Return the mode of this entity.

        The mode the sources run in, or the combined HEAT_COOL when its source
        runs in its phase. While the sources may still show the previous
        phase, or off, it stays HEAT_COOL.
        """
        running = self._running_mode()
        if self._phase is not None and (
            running == self._phase
            or (
                (self._phase_wait_cancel is not None or self._switching_to is not None)
                and running in {HVACMode.OFF, *PHASES}
            )
        ):
            return HVACMode.HEAT_COOL
        return running

    def _source_mode(self, mode: HVACMode) -> HVACMode:
        """Return the mode sent to the source: the phase for the combined HEAT_COOL."""
        if mode is HVACMode.HEAT_COOL and self._phase is not None:
            return self._phase
        return mode

    @property
    def _active_source(self) -> str | None:
        """Return the source of the current mode (None when off)."""
        return self._mode_sources.get(self._source_mode(self._current_mode()))

    @property
    def _display_source(self) -> str | None:
        """Return the source used for readings: the active one, else the first usable one."""
        active = self._active_source
        if active is not None:
            return active
        for entity_id in self.coordinator.source_entity_ids:
            if self._state(entity_id) is not None:
                return entity_id
        return None

    def _attr_from(self, entity_id: str | None, attr: str) -> Any:
        """Read an attribute from a source entity."""
        state = self._state(entity_id)
        return None if state is None else state.attributes.get(attr)

    def _attr_from_display(self, attr: str) -> Any:
        """Read an attribute from the display source."""
        return self._attr_from(self._display_source, attr)

    def _mode_entities(self, mode: HVACMode) -> list[str]:
        """Return the sources a mode uses: heat and cool for the combined HEAT_COOL."""
        if mode is HVACMode.HEAT_COOL and self._combined:
            return [self._mode_sources[phase] for phase in PHASES]
        return [self._mode_sources[mode]]

    def _mode_usable(self, mode: HVACMode) -> bool:
        """Return True when the sources of a mode are usable and offer it."""
        modes = PHASES if mode is HVACMode.HEAT_COOL and self._combined else (mode,)
        return all(
            self._state(self._mode_sources[source_mode]) is not None
            and source_mode not in self.coordinator.unsupported_modes
            for source_mode in modes
        )

    # Entity properties

    @property
    def force_update(self) -> bool:
        """Return True to send the next state even when nothing changed."""
        return self._force_write

    @property
    def available(self) -> bool:
        """Return True when at least one source is usable."""
        return self._display_source is not None

    def _source_features(self, entity_id: str | None) -> ClimateEntityFeature:
        """Return the supported features of a source entity."""
        return ClimateEntityFeature(
            self._attr_from(entity_id, ATTR_SUPPORTED_FEATURES) or 0
        )

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the features of the sources this entity implements.

        Temperature features are combined over every source, so they do not
        change with the mode. The combined HEAT_COOL adds the low/high
        targets. Fan and swing (vertical and horizontal) come from the source
        of the current mode, when it lists at least one option.
        """
        features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        for entity_id in self.coordinator.source_entity_ids:
            features |= self._source_features(entity_id) & SOURCE_FEATURES
        if self._combined:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE

        active = self._active_source
        for setting in SETTINGS:
            if self._setting_options(active, setting):
                features |= setting.feature
        return features

    @property
    def native_temperature_unit(self) -> str:
        """Return the unit of measurement.

        Climate state attributes are always in the system unit, so the
        values read from the sources are in that unit too.
        """
        return self.hass.config.units.temperature_unit

    @property
    def native_current_temperature(self) -> float | None:
        """Return the room temperature: the sensor, else the display source."""
        return self._room_temperature()

    def _shown_target(self, attr: str) -> float | None:
        """Return a target attribute as shown by the entity.

        Heat shows the low target as the single target and cool the high one;
        the low/high attributes are empty. HEAT_COOL shows low/high and no
        single target. The other modes show the single target. While off, the
        low/high targets are shown when the entity has them, else the targets
        of the mode turn_on goes to.

        A target the active source gets is read from it: it shows what is
        applied, even a target set on it outside the limits. During the
        settle time, or from a source without that target, the target of
        this entity is shown, as the active source gets it. The target of the
        other phase of the combined mode is shown as its source gets it.
        """
        mode = self._current_mode()
        mapping = self._target_map()
        if mode is HVACMode.OFF and (
            ClimateEntityFeature.TARGET_TEMPERATURE_RANGE in self.supported_features
        ):
            # Off, both setpoints are shown, to be set before turning on.
            target = None if attr == ATTR_TEMPERATURE else attr
        else:
            if mode is HVACMode.OFF:
                # No low/high targets: those of the mode turn_on goes to.
                mode = self._next_mode()
            if mode is HVACMode.HEAT_COOL:
                if attr == ATTR_TEMPERATURE:
                    target = ATTR_TEMPERATURE if ATTR_TEMPERATURE in mapping.values() else None
                else:
                    target = attr if self._combined or attr in mapping.values() else None
            elif attr == ATTR_TEMPERATURE:
                target = SINGLE_TARGETS.get(mode, ATTR_TEMPERATURE)
            else:
                target = None
        if target is None:
            return None

        active = self._active_source
        for source_attr, mapped in mapping.items():
            if mapped != target:
                continue
            value = self._attr_from(active, source_attr)
            if (
                self._settle_cancel is None
                and TARGET_FEATURES[source_attr] in self._source_features(active)
                and _is_number(value)
            ):
                return value
            return self._applied(target, active)
        return self._applied(target, self._target_source(target))

    @property
    def native_target_temperature(self) -> float | None:
        """Return the target temperature (see _shown_target)."""
        return self._shown_target(ATTR_TEMPERATURE)

    @property
    def native_target_temperature_high(self) -> float | None:
        """Return the high target temperature (see _shown_target)."""
        return self._shown_target(ATTR_TARGET_TEMP_HIGH)

    @property
    def native_target_temperature_low(self) -> float | None:
        """Return the low target temperature (see _shown_target)."""
        return self._shown_target(ATTR_TARGET_TEMP_LOW)

    if not hasattr(ClimateEntity, "native_temperature_unit"):
        # Home Assistant < 2026.11 only reads the names without "native_".
        temperature_unit = native_temperature_unit
        current_temperature = native_current_temperature
        target_temperature = native_target_temperature
        target_temperature_high = native_target_temperature_high
        target_temperature_low = native_target_temperature_low

    @property
    def target_temperature_step(self) -> float | None:
        """Return the temperature step of the display source."""
        return self._attr_from_display(ATTR_TARGET_TEMP_STEP)

    def _source_range(self, entity_ids: list[str]) -> tuple[float, float]:
        """Return the widest temperature range of the given sources.

        Home Assistant defaults when no source gives one.
        """
        mins = [
            value
            for entity_id in entity_ids
            if (value := self._attr_from(entity_id, ATTR_MIN_TEMP)) is not None
        ]
        maxs = [
            value
            for entity_id in entity_ids
            if (value := self._attr_from(entity_id, ATTR_MAX_TEMP)) is not None
        ]
        unit = self.hass.config.units.temperature_unit
        low = min(mins) if mins else TemperatureConverter.convert(
            DEFAULT_MIN_TEMP, UnitOfTemperature.CELSIUS, unit
        )
        high = max(maxs) if maxs else TemperatureConverter.convert(
            DEFAULT_MAX_TEMP, UnitOfTemperature.CELSIUS, unit
        )
        return low, high

    def _temperature_range(self) -> tuple[float, float]:
        """Return the range of the entity.

        On: the range of the sources of the current mode (heat and cool for
        the combined HEAT_COOL). Off: the widest range of the sources. Both
        narrowed by the configured limits.
        """
        mode = self._current_mode()
        return self._limited_range(
            self.coordinator.source_entity_ids
            if mode is HVACMode.OFF
            else self._mode_entities(mode)
        )

    def _limited_range(self, entity_ids: list[str]) -> tuple[float, float]:
        """Return the range of the given sources, narrowed by the configured limits.

        A limit can only narrow the range. A limit outside the source range
        is ignored, so the minimum always stays below the maximum.
        """
        low, high = self._source_range(entity_ids)
        settings = entry_settings(self._entry)
        limit_min = settings.get(CONF_MIN_TEMP)
        limit_max = settings.get(CONF_MAX_TEMP)
        if limit_min is not None and limit_min < high:
            low = max(low, limit_min)
        if limit_max is not None and limit_max > low:
            high = min(high, limit_max)
        return low, high

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return self._temperature_range()[0]

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return self._temperature_range()[1]

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current mode."""
        return self._current_mode()

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return OFF plus every mode that has a source, HEAT_COOL when combined."""
        return [
            HVACMode.OFF,
            *(
                mode
                for mode in MODE_SOURCE_KEYS
                if mode in self._mode_sources
                or (mode is HVACMode.HEAT_COOL and self._combined)
            ),
        ]

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current action of the active source."""
        if self._current_mode() is HVACMode.OFF:
            return HVACAction.OFF

        action = self._attr_from(self._active_source, ATTR_HVAC_ACTION)
        if action is None:
            return None
        try:
            return HVACAction(action)
        except ValueError:
            return None

    @property
    def fan_mode(self) -> str | None:
        """Return the fan mode of the active source."""
        return self._attr_from(self._active_source, ATTR_FAN_MODE)

    @property
    def fan_modes(self) -> list[str] | None:
        """Return the fan modes of the active source."""
        return self._attr_from(self._active_source, ATTR_FAN_MODES)

    @property
    def swing_mode(self) -> str | None:
        """Return the swing mode of the active source."""
        return self._attr_from(self._active_source, ATTR_SWING_MODE)

    @property
    def swing_modes(self) -> list[str] | None:
        """Return the swing modes of the active source."""
        return self._attr_from(self._active_source, ATTR_SWING_MODES)

    @property
    def swing_horizontal_mode(self) -> str | None:
        """Return the horizontal swing mode of the active source."""
        return self._attr_from(self._active_source, ATTR_SWING_HORIZONTAL_MODE)

    @property
    def swing_horizontal_modes(self) -> list[str] | None:
        """Return the horizontal swing modes of the active source."""
        return self._attr_from(self._active_source, ATTR_SWING_HORIZONTAL_MODES)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return {
            "active_entity_id": self._active_source,
            "mode_entity_ids": {
                str(mode): entity_id for mode, entity_id in self._mode_sources.items()
            },
            # Modes still listed, but whose source cannot be used right now
            # (unavailable, or it does not offer the mode).
            "unavailable_modes": [
                str(mode) for mode in self.hvac_modes[1:] if not self._mode_usable(mode)
            ],
        }

    # Commands

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the targets and send them to the source of the current mode.

        The single target is the heating setpoint in heat and the cooling one
        in cool (see _target_map); the low and high targets are those of
        HEAT_COOL. Setting one keeps the configured gap with the other (see
        _apply_gap). A low/high target is kept rounded and in the range of the
        source it goes to (see _target_source). The targets are kept even when
        off, or when the current mode does not use them: the next mode gets
        them. With a new mode, the source gets the targets once it shows that
        mode. In the combined HEAT_COOL, new low/high targets may switch the
        phase.
        """
        hvac_mode = kwargs.get(ATTR_HVAC_MODE)
        if hvac_mode is not None and hvac_mode not in self.hvac_modes:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_hvac_mode",
                translation_placeholders={"hvac_mode": str(hvac_mode)},
            )
        # The single target is the heating setpoint in heat, the cooling one
        # in cool (of the new mode when one is asked).
        mode = HVACMode(hvac_mode) if hvac_mode is not None else self._current_mode()
        if mode is HVACMode.OFF:
            mode = self._next_mode()
        changed: list[str] = []
        for attr in TARGETS:
            if kwargs.get(attr) is None:
                continue
            target = SINGLE_TARGETS.get(mode, attr) if attr == ATTR_TEMPERATURE else attr
            self._targets[target] = self._keep(target, float(kwargs[attr]))
            changed.append(target)
        self._apply_gap(changed)

        if hvac_mode is not None and HVACMode(hvac_mode) != self._current_mode():
            await self.async_set_hvac_mode(HVACMode(hvac_mode))
        elif self._current_mode() is not HVACMode.OFF:
            self._check_phase()
            await self._async_send_targets(self._target_key())
        # A target the source cannot take (out of its range) leaves the state
        # as it was. It is sent anyway, so the frontend drops the value it
        # shows and shows the target applied again.
        self._force_write = True
        try:
            self.async_write_ha_state()
        finally:
            self._force_write = False

    def _keep(self, target: str, value: float) -> float:
        """Return a value to keep for a target.

        A target that only goes to one source (see _target_source) is kept as
        that source gets it, so the phase switches where the source works.
        Otherwise it is kept as is, for every source.
        """
        source = self._target_source(target)
        if source is not None and self._state(source) is not None:
            return self._fit(value, source)
        return value

    def _gap_respected(self, gap: float) -> bool:
        """Return True when the low target is at least gap below the high one."""
        low = self._targets[ATTR_TARGET_TEMP_LOW]
        high = self._targets[ATTR_TARGET_TEMP_HIGH]
        return (
            low is None
            or high is None
            or low <= high - gap
            or _same_temperature(low, high - gap)
        )

    def _apply_gap(self, changed: list[str]) -> None:
        """Keep the low target the configured gap below the high one.

        The target just set stays; the other one moves. If its source cannot
        follow (range), the target just set moves back as far as needed. When
        both were set, the high target moves.
        """
        low_high = {ATTR_TARGET_TEMP_LOW, ATTR_TARGET_TEMP_HIGH}
        gap = float(entry_settings(self._entry).get(CONF_MIN_GAP) or 0)
        if not low_high & set(changed) or self._gap_respected(gap):
            return
        pivot = (
            ATTR_TARGET_TEMP_LOW
            if ATTR_TARGET_TEMP_LOW in changed
            else ATTR_TARGET_TEMP_HIGH
        )
        other = (
            ATTR_TARGET_TEMP_HIGH
            if pivot == ATTR_TARGET_TEMP_LOW
            else ATTR_TARGET_TEMP_LOW
        )
        for moved, fixed in ((other, pivot), (pivot, other)):
            sign = 1 if moved == ATTR_TARGET_TEMP_HIGH else -1
            self._targets[moved] = self._keep(
                moved, self._targets[fixed] + sign * gap
            )
            if self._gap_respected(gap):
                return

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode of the active source.

        Home Assistant has already checked that fan_mode is in fan_modes.
        """
        await self._async_source_call("set_fan_mode", {ATTR_FAN_MODE: fan_mode})

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set the swing mode of the active source.

        Home Assistant has already checked that swing_mode is in swing_modes.
        """
        await self._async_source_call("set_swing_mode", {ATTR_SWING_MODE: swing_mode})

    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode: str) -> None:
        """Set the horizontal swing mode of the active source.

        Home Assistant has already checked that swing_horizontal_mode is in
        swing_horizontal_modes.
        """
        await self._async_source_call(
            "set_swing_horizontal_mode",
            {ATTR_SWING_HORIZONTAL_MODE: swing_horizontal_mode},
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Switch to a mode.

        Every other source that is not off is turned off first, so two
        sources never run at once, even when several were turned on elsewhere.
        The remembered fan and swing settings of the mode are then sent to
        its source. Home Assistant has already checked that hvac_mode is in
        hvac_modes.
        The combined HEAT_COOL runs the heat or cool source (see _wanted_phase).
        A mode whose source is unavailable is refused before anything is
        turned off: Home Assistant would skip the call to that source silently.
        So is a mode its source does not offer: the source would reject it.
        The combined HEAT_COOL needs both of its sources.
        """
        if hvac_mode is not HVACMode.OFF:
            for source_mode in (
                PHASES if hvac_mode is HVACMode.HEAT_COOL and self._combined else (hvac_mode,)
            ):
                self._check_source(hvac_mode, source_mode)

        if hvac_mode is HVACMode.HEAT_COOL and self._combined:
            phase = self._wanted_phase(None)
            self._start_phase(phase)
            await self._async_activate(phase, HVACMode.HEAT_COOL)
        else:
            self._leave_phase()
            if hvac_mode is HVACMode.OFF:
                await self.coordinator.async_turn_off_other_sources(None)
            else:
                await self._async_activate(hvac_mode, hvac_mode)
        if hvac_mode is not HVACMode.OFF:
            self._last_on_mode = hvac_mode
        # A source already in its mode sends no update: the new targets
        # are sent from here.
        self._update_phase()
        self._observe_sources()
        self.async_write_ha_state()

    def _check_source(self, hvac_mode: HVACMode, source_mode: HVACMode) -> None:
        """Refuse a mode whose source is unavailable or does not offer its mode."""
        entity_id = self._mode_sources[source_mode]
        placeholders = {"hvac_mode": str(hvac_mode), "entity_id": entity_id}
        if self._state(entity_id) is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="source_unavailable",
                translation_placeholders=placeholders,
            )
        if source_mode in self.coordinator.unsupported_modes:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="source_mode_not_supported",
                translation_placeholders=placeholders,
            )

    async def _async_activate(self, source_mode: HVACMode, mode: HVACMode) -> None:
        """Run the source of a mode, after turning the other sources off.

        source_mode is sent to the source; mode is the mode of this entity
        (HEAT_COOL for a phase of the combined mode).
        """
        entity_id = self._mode_sources[source_mode]
        self._switching_to = mode
        try:
            await self.coordinator.async_turn_off_other_sources(entity_id)
            await self._async_source_set_hvac_mode(entity_id, source_mode)
            await self._async_send_settings(source_mode, entity_id)
        finally:
            self._switching_to = None

    async def async_turn_on(self) -> None:
        """Turn on in the last used mode, else the first configured mode."""
        if self._current_mode() is not HVACMode.OFF:
            return

        mode = self._next_mode()
        if mode is not HVACMode.OFF:
            await self.async_set_hvac_mode(mode)

    def _next_mode(self) -> HVACMode:
        """Return the mode turn_on goes to: the last used one, else the first configured.

        While off, the targets shown and set are those of this mode.
        """
        modes = self.hvac_modes[1:]
        mode = self._last_on_mode
        if mode not in modes:
            mode = next(iter(modes), HVACMode.OFF)
        return mode

    async def async_turn_off(self) -> None:
        """Turn off every source that is on."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    def _require_active_source(self) -> str:
        """Return the active source, or refuse the command when off."""
        source = self._active_source
        if source is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_active_mode",
            )
        return source

    async def _async_source_call(self, service: str, data: dict[str, Any]) -> None:
        """Call a climate service on the active source."""
        await self.hass.services.async_call(
            CLIMATE_DOMAIN,
            service,
            {**data, ATTR_ENTITY_ID: self._require_active_source()},
            blocking=True,
        )

    async def _async_source_set_hvac_mode(
        self, entity_id: str, hvac_mode: HVACMode
    ) -> None:
        """Set the HVAC mode of a source entity."""
        await self.hass.services.async_call(
            CLIMATE_DOMAIN,
            "set_hvac_mode",
            {ATTR_ENTITY_ID: entity_id, ATTR_HVAC_MODE: hvac_mode},
            blocking=True,
        )
