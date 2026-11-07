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
    CONF_MIN_TEMP,
    DOMAIN,
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


def _parse_temperature(data: dict[str, Any]) -> float | None:
    """Read the target temperature saved before a restart."""
    value = data.get("target_temperature")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _same_temperature(a: Any, b: Any) -> bool:
    """Return True when two temperatures are equal, ignoring float noise."""
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return False
    return math.isclose(a, b, abs_tol=1e-6)


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

    Each mode remembers its fan and swing settings and sends them back to its
    source when the entity switches to it. The synchronized modes share one
    memory, which only keeps values that all their sources accept.

    The target temperature belongs to this entity, not to the sources: it
    is sent to the source of each mode the entity enters, rounded to the
    step of that source and kept in its range (see _observe_temperature).
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: AdaptativeClimateCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._entry = coordinator.config_entry
        self._mode_sources = coordinator.mode_sources
        self._attr_unique_id = self._entry.entry_id
        self._attr_name = self._entry.title
        # Mode restored by turn_on. Kept in memory only.
        self._last_on_mode: HVACMode | None = None
        # Fan and swing settings of each mode, kept across restarts.
        self._memory: SettingsMemory = {}
        # Mode and settings of the active source at the last update, to
        # tell a mode change from a setting change.
        self._observed: tuple[HVACMode, dict[str, Any]] | None = None
        # Mode being switched to by this entity, while it is in progress.
        self._switching_to: HVACMode | None = None
        # Target temperature wanted by the user, kept across restarts. The
        # sources receive it rounded and in their range, but it stays as is.
        self._target_temperature: float | None = None
        # Settle time after entering a mode (see SETTLE_TIME): cancels its
        # timer, None outside of it.
        self._settle_cancel: CALLBACK_TYPE | None = None
        # The target was sent to the source during the settle time, so the
        # source showing it confirms the mode.
        self._settle_sent = False
        # The source showed another target during the settle time.
        self._settle_received = False

    async def async_added_to_hass(self) -> None:
        """Restore the remembered settings."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_extra_data()) is not None:
            self._memory = _parse_memory(last.as_dict())
            self._target_temperature = _parse_temperature(last.as_dict())
        self._observe_sources()

    async def async_will_remove_from_hass(self) -> None:
        """Stop the settle timer."""
        self._end_settle()
        await super().async_will_remove_from_hass()

    @property
    def extra_restore_state_data(self) -> RestoredExtraData:
        """Save the remembered settings of the configured modes."""
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
                "target_temperature": self._target_temperature,
            }
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Remember the last mode, the settings and the target, then update state."""
        mode = self._current_mode()
        if mode is not HVACMode.OFF:
            self._last_on_mode = mode
        self._observe_sources()
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
        """Follow the active source: its settings and its target temperature.

        Nothing is taken from the sources while the entity is off.
        """
        if self._target_temperature is None:
            self._target_temperature = self._initial_temperature()

        mode = self._current_mode()
        if mode is HVACMode.OFF:
            self._observed = None
            self._end_settle()
            return

        source = self._mode_sources[mode]
        values = {setting.attr: self._attr_from(source, setting.attr) for setting in SETTINGS}
        values[ATTR_TEMPERATURE] = self._attr_from(source, ATTR_TEMPERATURE)
        previous = self._observed
        self._observed = (mode, values)
        # While switching, the source may still show the previous mode.
        if self._switching_to is not None and mode != self._switching_to:
            return

        before = None if previous is None or previous[0] != mode else previous[1]
        self._observe_settings(mode, values, before)
        self._observe_temperature(mode, source, values, before)

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
    def _observe_temperature(
        self,
        mode: HVACMode,
        source: str,
        values: dict[str, Any],
        before: dict[str, Any] | None,
    ) -> None:
        """Send the target to a source entering its mode, or take a change made on it.

        Entering a mode (by this entity or elsewhere) starts the settle time
        and sends the target once the source shows the mode. During the
        settle time, the targets of the source are ignored: it may report
        its own target for the mode, late. The source showing the target
        sent to it ends the settle time. Otherwise, at its end, the target
        is sent again if the source showed another target in the meantime.
        If it showed nothing, nothing is sent.

        Outside the settle time, a target changed on the source becomes the
        target of this entity, unless it is the value sent to it (rounded
        and in its range).
        """
        if before is None:
            self._start_settle(mode)
            self._schedule_send_temperature(mode)
            return
        value = values[ATTR_TEMPERATURE]
        applied = self._applied_temperature(source)
        if self._settle_cancel is not None:
            if self._settle_sent and _same_temperature(value, applied):
                self._end_settle()
            elif not _same_temperature(value, before[ATTR_TEMPERATURE]):
                self._settle_received = True
            return
        if not isinstance(value, (int, float)) or _same_temperature(
            value, before[ATTR_TEMPERATURE]
        ):
            return
        if _same_temperature(value, applied):
            return
        # The user took over from the source: it is kept as is, even outside
        # the range or the limits of this entity.
        self._target_temperature = float(value)

    @callback
    def _start_settle(self, mode: HVACMode) -> None:
        """Start the settle time of a mode just entered."""
        self._end_settle()

        @callback
        def _settled(_now: datetime) -> None:
            self._settle_cancel = None
            received = self._settle_received
            self._end_settle()
            if received:
                self._schedule_send_temperature(mode)
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
    def _schedule_send_temperature(self, mode: HVACMode) -> None:
        """Send the target to the source of a mode, without waiting."""
        self._entry.async_create_task(
            self.hass,
            self._async_send_temperature(mode),
            f"{DOMAIN} temperature {self._mode_sources[mode]}",
        )

    def _initial_temperature(self) -> float | None:
        """Return a first target: the one of a source, else the middle of the range.

        None while no source is usable yet.
        """
        if self._display_source is None:
            return None
        active = self._active_source
        entity_ids = [active] if active else self.coordinator.source_entity_ids
        for entity_id in entity_ids:
            value = self._attr_from(entity_id, ATTR_TEMPERATURE)
            if isinstance(value, (int, float)):
                return float(value)
        low, high = self._temperature_range()
        return (low + high) / 2

    def _applied_temperature(self, entity_id: str | None) -> float | None:
        """Return the target as a source gets it: rounded to its step, in its range.

        Without a source (entity off), the target is only kept in the range
        of the entity.
        """
        target = self._target_temperature
        if target is None:
            return None
        if entity_id is None:
            low, high = self._temperature_range()
        else:
            low, high = self._limited_range([entity_id])
            step = self._attr_from(entity_id, ATTR_TARGET_TEMP_STEP)
            if isinstance(step, (int, float)) and step > 0:
                target = round(math.floor(target / step + 0.5) * step, 6)
        return min(max(target, low), high)

    async def _async_send_temperature(self, mode: HVACMode) -> None:
        """Send the target to the source of a mode, if that mode is still on.

        A source without a target (fan only) gets nothing, and the target is
        kept for the next mode. A source error is logged without failing.
        """
        if self._current_mode() != mode:
            return
        entity_id = self._mode_sources[mode]
        if ClimateEntityFeature.TARGET_TEMPERATURE not in self._source_features(entity_id):
            return
        applied = self._applied_temperature(entity_id)
        if applied is None or _same_temperature(
            self._attr_from(entity_id, ATTR_TEMPERATURE), applied
        ):
            return
        # Set first: the source may show the target before the call returns.
        if self._settle_cancel is not None:
            self._settle_sent = True
        try:
            await self.hass.services.async_call(
                CLIMATE_DOMAIN,
                "set_temperature",
                {ATTR_TEMPERATURE: applied, ATTR_ENTITY_ID: entity_id},
                blocking=True,
            )
        except HomeAssistantError as err:
            _LOGGER.warning(
                "Could not set the temperature %s on %s: %s", applied, entity_id, err
            )

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

    def _current_mode(self) -> HVACMode:
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

    @property
    def _active_source(self) -> str | None:
        """Return the source of the current mode (None when off)."""
        return self._mode_sources.get(self._current_mode())

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

    # Entity properties

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
        change with the mode. Fan and swing (vertical and horizontal) come
        from the source of the current mode, when it lists at least one option.
        """
        features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        for entity_id in self.coordinator.source_entity_ids:
            features |= self._source_features(entity_id) & SOURCE_FEATURES

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
        """Return the current temperature."""
        return self._attr_from_display(ATTR_CURRENT_TEMPERATURE)

    @property
    def native_target_temperature(self) -> float | None:
        """Return the target of the active source, else the target of this entity.

        The active source shows what is applied, even a target set on it
        outside the limits. During the settle time, off, or with a source
        without target (fan only), the target of this entity is shown, as
        the active source gets it.
        """
        active = self._active_source
        value = self._attr_from(active, ATTR_TEMPERATURE)
        if (
            self._settle_cancel is None
            and ClimateEntityFeature.TARGET_TEMPERATURE in self._source_features(active)
            and isinstance(value, (int, float))
        ):
            return value
        return self._applied_temperature(active)

    @property
    def native_target_temperature_high(self) -> float | None:
        """Return the high target temperature."""
        return self._attr_from(self._active_source, ATTR_TARGET_TEMP_HIGH)

    @property
    def native_target_temperature_low(self) -> float | None:
        """Return the low target temperature."""
        return self._attr_from(self._active_source, ATTR_TARGET_TEMP_LOW)

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

        On: the range of the active source. Off: the widest range of the
        sources. Both narrowed by the configured limits.
        """
        active = self._active_source
        return self._limited_range(
            [active] if active else self.coordinator.source_entity_ids
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
        """Return OFF plus every mode that has a source configured."""
        return [HVACMode.OFF, *self._mode_sources]

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
                str(mode)
                for mode, entity_id in self._mode_sources.items()
                if self._state(entity_id) is None
                or mode in self.coordinator.unsupported_modes
            ],
        }

    # Commands

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature and send it to the source of the current mode.

        The target is kept even when off or when the source has none (fan
        only): the next mode gets it. With a new mode, the source gets the
        target once it shows that mode. Low/high targets go to the source as is.
        """
        hvac_mode = kwargs.get(ATTR_HVAC_MODE)
        if hvac_mode is not None and hvac_mode not in self.hvac_modes:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_hvac_mode",
                translation_placeholders={"hvac_mode": str(hvac_mode)},
            )
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            self._target_temperature = float(temperature)
        service_data = {
            key: kwargs[key]
            for key in (ATTR_TARGET_TEMP_LOW, ATTR_TARGET_TEMP_HIGH)
            if key in kwargs
        }

        if hvac_mode is not None and HVACMode(hvac_mode) != self._current_mode():
            await self.async_set_hvac_mode(HVACMode(hvac_mode))
            if hvac_mode == HVACMode.OFF:
                self.async_write_ha_state()
                return
            source = self._mode_sources[HVACMode(hvac_mode)]
        elif self._current_mode() is HVACMode.OFF:
            if service_data:
                self._require_active_source()
            self.async_write_ha_state()
            return
        else:
            source = self._mode_sources[self._current_mode()]
            applied = self._applied_temperature(source)
            if (
                temperature is not None
                and applied is not None
                and ClimateEntityFeature.TARGET_TEMPERATURE
                in self._source_features(source)
            ):
                service_data[ATTR_TEMPERATURE] = applied

        if service_data:
            # Set last: the call must always go to the source entity.
            service_data[ATTR_ENTITY_ID] = source
            await self.hass.services.async_call(
                CLIMATE_DOMAIN,
                "set_temperature",
                service_data,
                blocking=True,
            )
        self.async_write_ha_state()

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
        A mode whose source is unavailable is refused before anything is
        turned off: Home Assistant would skip the call to that source silently.
        So is a mode its source does not offer: the source would reject it.
        """
        target = self._mode_sources.get(hvac_mode)
        if target is not None and self._state(target) is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="source_unavailable",
                translation_placeholders={
                    "hvac_mode": str(hvac_mode),
                    "entity_id": target,
                },
            )
        if target is not None and hvac_mode in self.coordinator.unsupported_modes:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="source_mode_not_supported",
                translation_placeholders={
                    "hvac_mode": str(hvac_mode),
                    "entity_id": target,
                },
            )
        await self.coordinator.async_turn_off_other_sources(target)

        if target is not None:
            self._switching_to = hvac_mode
            try:
                await self._async_source_set_hvac_mode(target, hvac_mode)
                self._last_on_mode = hvac_mode
                await self._async_send_settings(hvac_mode, target)
            finally:
                self._switching_to = None

    async def async_turn_on(self) -> None:
        """Turn on in the last used mode, else the first configured mode."""
        if self._current_mode() is not HVACMode.OFF:
            return

        mode = self._last_on_mode
        if mode not in self._mode_sources:
            mode = next(iter(self._mode_sources), None)
        if mode is not None:
            await self.async_set_hvac_mode(mode)

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
