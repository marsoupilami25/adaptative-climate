"""Climate platform for Adaptative Climate.

AdaptativeClimateEntity is a facade over the engine (see engine/): it
builds the parts, runs the update cycle and the commands, and exposes the
Home Assistant properties.

- Update cycle (_handle_coordinator_update): check the combined phase
  against the sources, remember the last mode, observe the active source
  (settings and targets; a source entering a mode the entity did not ask
  for gives its targets), switch the phase if the temperature asks for it.
- Combined HEAT_COOL: the phase is chosen by wanted_phase and switched in
  the background, under the mode lock. A new phase is held for the minimum
  phase duration, unless the user sets new targets.
- Commands: set_temperature (targets, optional mode), set_hvac_mode,
  turn_on/off, fan and swing (sent to the active source).
- Restore: the parts save and read their own data; the entity merges it.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_SWING_HORIZONTAL_MODE,
    ATTR_SWING_HORIZONTAL_MODES,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TARGET_TEMP_STEP,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoredExtraData, RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AdaptativeClimateConfigEntry, AdaptativeClimateCoordinator
from .engine.model import SETTINGS, TARGETS, TargetKey
from .engine.modes import ModeTracker
from .engine.phase import CombinedPhase, wanted_phase
from .engine.profiles import build_profiles
from .engine.settings_memory import SettingsMemory
from .engine.sources import Sources
from .engine.target_sync import TargetSync
from .engine.targets import TargetStore

_LOGGER = logging.getLogger(__name__)

# Features this entity implements. Other features of the sources
# (presets, humidity...) are dropped: exposing them without implementing
# them makes Home Assistant fail when the entity is added.
SOURCE_FEATURES = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AdaptativeClimateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Adaptative Climate entities from a config entry."""
    async_add_entities([AdaptativeClimateEntity(entry.runtime_data)])


class AdaptativeClimateEntity(
    CoordinatorEntity[AdaptativeClimateCoordinator],
    ClimateEntity,
    RestoreEntity,
):
    """Climate entity driving one source climate entity per mode.

    The entity is a facade over the engine:

    - Sources reads and commands the source entities.
    - ModeTracker reads the current mode from the sources and switches it;
      each mode has a profile (see engine.profiles).
    - CombinedPhase keeps the phase of the combined HEAT_COOL (no heat_cool
      source: it runs the heat or cool source, chosen from the room
      temperature and the low/high targets).
    - SettingsMemory remembers the fan and swing settings of each mode and
      sends them back when the entity switches to it.
    - TargetStore keeps the targets, which belong to this entity, not to the
      sources; TargetSync sends them to the source of each mode the entity
      enters and takes the changes made on it.

    The entity follows the sources on each update (see
    _handle_coordinator_update) and runs the commands.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: AdaptativeClimateCoordinator) -> None:
        """Initialize the entity and its engine."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = entry.entry_id
        self._attr_name = entry.title
        self._sources = Sources(coordinator)
        self._memory = SettingsMemory(coordinator, self._sources)
        self._phase = CombinedPhase(
            coordinator.hass,
            coordinator.combined_heat_cool,
            self._phase_wait_ended,
            coordinator.min_phase_duration,
        )
        self._modes = ModeTracker(
            coordinator,
            self._sources,
            build_profiles(self._sources, coordinator.combined_heat_cool),
            self._phase,
            self._memory,
        )
        self._target_store = TargetStore()
        self._targets = TargetSync(
            coordinator,
            self._sources,
            self._modes,
            self._phase,
            self._target_store,
            self.async_write_ha_state,
        )
        # Target key and readings of the active source at the last update,
        # to tell a mode change from a change within the mode.
        self._observed: tuple[TargetKey, dict[str, Any]] | None = None
        # The next state write is sent even when nothing changed (see
        # async_set_temperature).
        self._force_write = False

    async def async_added_to_hass(self) -> None:
        """Restore the remembered settings, the targets and the combined mode."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_extra_data()) is not None:
            data = last.as_dict()
            self._memory.restore(data)
            self._target_store.restore(data)
            self._targets.apply_gap([ATTR_TARGET_TEMP_LOW])
            self._phase.restore(data)
        self._update_phase()
        self._observe_sources()

    async def async_will_remove_from_hass(self) -> None:
        """Stop the timers."""
        self._targets.end_settle()
        self._phase.stop_timers()
        await super().async_will_remove_from_hass()

    @property
    def extra_restore_state_data(self) -> RestoredExtraData:
        """Save the remembered settings, the targets and the combined mode."""
        return RestoredExtraData(
            {
                **self._memory.as_dict(),
                **self._target_store.as_dict(),
                **self._phase.as_dict(),
            }
        )

    # Following the sources

    @callback
    def _handle_coordinator_update(self) -> None:
        """Follow the sources, then update state."""
        self._update_phase()
        mode = self._modes.current()
        if mode is not HVACMode.OFF:
            self._modes.last_on_mode = mode
        self._observe_sources()
        self._check_phase()
        super()._handle_coordinator_update()

    @callback
    def _observe_sources(self) -> None:
        """Follow the active source: its settings and its targets.

        Nothing is taken from the sources while the entity is off.
        """
        self._targets.init()

        mode = self._modes.current()
        source_mode = self._modes.source_mode(mode)
        if mode is HVACMode.OFF or self._sources.running_mode() != source_mode:
            # Off, or the combined HEAT_COOL whose source does not show the
            # phase yet.
            self._observed = None
            self._targets.end_settle()
            return

        source = self._sources.mode_sources[source_mode]
        key = self._targets.key()
        values = {
            attr: self._sources.attr(source, attr)
            for attr in (*(setting.attr for setting in SETTINGS), *TARGETS)
        }
        previous = self._observed
        self._observed = (key, values)
        # While switching, the source may still show the previous mode.
        switching_to = self._modes.switching_to
        if switching_to is not None and mode != switching_to:
            return

        before = None if previous is None or previous[0] != key else previous[1]
        # Entering a mode: asked by this entity, or the source was turned on
        # elsewhere (remote, app), which then gives its targets.
        requested = before is None and self._modes.take_request(source, source_mode)
        self._memory.observe(source_mode, values, before)
        self._targets.observe(key, source_mode, values, before, requested=requested)

    # Combined HEAT_COOL

    def _wanted_phase(self, current: HVACMode | None) -> HVACMode:
        """Return the phase the combined HEAT_COOL should run in."""
        return wanted_phase(
            current,
            self._sources.phase_temperatures(),
            self._target_store[ATTR_TARGET_TEMP_LOW],
            self._target_store[ATTR_TARGET_TEMP_HIGH],
            self._sources.running_mode(),
        )

    @callback
    def _update_phase(self) -> None:
        """Leave the combined HEAT_COOL when its source left the phase elsewhere."""
        self._phase.update(
            self._sources.running_mode(),
            lambda: self._modes.usable(HVACMode.HEAT_COOL),
            self._modes.switching,
        )

    @callback
    def _check_phase(self, *, forced: bool = False) -> None:
        """Switch the combined HEAT_COOL to the phase the temperature asks for.

        A new phase is held for the minimum phase duration before it switches
        by itself again; forced (new targets from the user) ignores it.
        """
        if not self._phase.can_switch(self._modes.switching, forced=forced):
            return
        phase = self._wanted_phase(self._phase.phase)
        if phase != self._phase.phase:
            self._phase.start(phase)
            self.coordinator.config_entry.async_create_task(
                self.hass,
                self._async_switch_phase(phase),
                f"{DOMAIN} phase {phase}",
            )

    @callback
    def _phase_wait_ended(self) -> None:
        """Follow the sources again once they had time to show the phase."""
        self._update_phase()
        self._observe_sources()
        self._check_phase()
        self.async_write_ha_state()

    async def _async_switch_phase(self, phase: HVACMode) -> None:
        """Run the source of a new phase, if the phase did not change since.

        It waits for a mode change in progress, which may change the phase.
        """
        async with self._modes.lock:
            if self._phase.phase != phase:
                return
            try:
                await self._modes.async_activate(phase, HVACMode.HEAT_COOL)
            except HomeAssistantError as err:
                _LOGGER.warning(
                    "Could not switch %s to %s: %s", self.entity_id, phase, err
                )
        self._observe_sources()
        self.async_write_ha_state()

    # Entity properties

    @property
    def force_update(self) -> bool:
        """Return True to send the next state even when nothing changed."""
        return self._force_write

    @property
    def available(self) -> bool:
        """Return True when at least one source is usable."""
        return self._modes.display_source() is not None

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the features of the sources this entity implements.

        Temperature features are combined over every source, so they do not
        change with the mode. The combined HEAT_COOL adds the low/high
        targets. Fan and swing (vertical and horizontal) come from the source
        of the current mode, when it lists at least one option.
        """
        features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        for entity_id in self._sources.entity_ids:
            features |= self._sources.features(entity_id) & SOURCE_FEATURES
        for mode in self._modes.modes[1:]:
            features |= self._modes.profile(mode).features

        active = self._modes.active_source()
        for setting in SETTINGS:
            if self._memory.options(active, setting):
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
        return self._sources.room_temperature(self._modes.display_mode())

    def _shown_target(self, attr: str) -> float | None:
        """Return a target attribute as shown by the entity (see TargetSync.shown)."""
        range_supported = (
            ClimateEntityFeature.TARGET_TEMPERATURE_RANGE in self.supported_features
        )
        return self._targets.shown(attr, range_supported)

    @property
    def native_target_temperature(self) -> float | None:
        """Return the target temperature."""
        return self._shown_target(ATTR_TEMPERATURE)

    @property
    def native_target_temperature_high(self) -> float | None:
        """Return the high target temperature."""
        return self._shown_target(ATTR_TARGET_TEMP_HIGH)

    @property
    def native_target_temperature_low(self) -> float | None:
        """Return the low target temperature."""
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
        return self._sources.attr(self._modes.display_source(), ATTR_TARGET_TEMP_STEP)

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return self._modes.temperature_range()[0]

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return self._modes.temperature_range()[1]

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current mode."""
        return self._modes.current()

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return OFF plus every mode that has a source, HEAT_COOL when combined."""
        return self._modes.modes

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current action of the active source."""
        if self._modes.current() is HVACMode.OFF:
            return HVACAction.OFF

        action = self._active_attr(ATTR_HVAC_ACTION)
        if action is None:
            return None
        try:
            return HVACAction(action)
        except ValueError:
            return None

    def _active_attr(self, attr: str) -> Any:
        """Read an attribute from the active source."""
        return self._sources.attr(self._modes.active_source(), attr)

    @property
    def fan_mode(self) -> str | None:
        """Return the fan mode of the active source."""
        return self._active_attr(ATTR_FAN_MODE)

    @property
    def fan_modes(self) -> list[str] | None:
        """Return the fan modes of the active source."""
        return self._active_attr(ATTR_FAN_MODES)

    @property
    def swing_mode(self) -> str | None:
        """Return the swing mode of the active source."""
        return self._active_attr(ATTR_SWING_MODE)

    @property
    def swing_modes(self) -> list[str] | None:
        """Return the swing modes of the active source."""
        return self._active_attr(ATTR_SWING_MODES)

    @property
    def swing_horizontal_mode(self) -> str | None:
        """Return the horizontal swing mode of the active source."""
        return self._active_attr(ATTR_SWING_HORIZONTAL_MODE)

    @property
    def swing_horizontal_modes(self) -> list[str] | None:
        """Return the horizontal swing modes of the active source."""
        return self._active_attr(ATTR_SWING_HORIZONTAL_MODES)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return {
            "active_entity_id": self._modes.active_source(),
            "mode_entity_ids": {
                str(mode): entity_id
                for mode, entity_id in self._sources.mode_sources.items()
            },
            # Modes still listed, but whose source cannot be used right now
            # (unavailable, or it does not offer the mode).
            "unavailable_modes": [
                str(mode) for mode in self.hvac_modes[1:] if not self._modes.usable(mode)
            ],
            # Sources running in a mode they do not serve here (set
            # elsewhere), which the entity ignores.
            "foreign_modes": self._sources.foreign_modes(),
            # Every target kept by the entity, also those the current mode
            # does not show, as set (before offset and rounding).
            "saved_targets": {target: self._target_store[target] for target in TARGETS},
        }

    # Commands

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the targets and send them to the source of the current mode.

        The targets are set for the current mode, or the new one when asked
        (see TargetSync.set). They are kept even when off, or when the current
        mode does not use them: the next mode gets them. With a new mode, the
        source gets the targets once it shows that mode. In the combined
        HEAT_COOL, new low/high targets may switch the phase.
        """
        hvac_mode = kwargs.get(ATTR_HVAC_MODE)
        if hvac_mode is not None and hvac_mode not in self.hvac_modes:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_hvac_mode",
                translation_placeholders={"hvac_mode": str(hvac_mode)},
            )
        mode = HVACMode(hvac_mode) if hvac_mode is not None else self._modes.current()
        if mode is HVACMode.OFF:
            mode = self._modes.next_mode()
        self._targets.set(
            {attr: float(kwargs[attr]) for attr in TARGETS if kwargs.get(attr) is not None},
            mode,
        )

        if hvac_mode is not None and HVACMode(hvac_mode) != self._modes.current():
            await self.async_set_hvac_mode(HVACMode(hvac_mode))
        elif self._modes.current() is not HVACMode.OFF:
            self._check_phase(forced=True)
            await self._targets.async_send(self._targets.key())
        # A target the source cannot take (out of its range) leaves the state
        # as it was. It is sent anyway, so the frontend drops the value it
        # shows and shows the target applied again.
        self._force_write = True
        try:
            self.async_write_ha_state()
        finally:
            self._force_write = False

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
        The combined HEAT_COOL runs the heat or cool source (see wanted_phase).
        A mode whose source is unavailable is refused before anything is
        turned off: Home Assistant would skip the call to that source silently.
        So is a mode its source does not offer: the source would reject it.
        The combined HEAT_COOL needs both of its sources.
        """
        if hvac_mode is not HVACMode.OFF:
            self._modes.check(hvac_mode)

        async with self._modes.lock:
            if hvac_mode is HVACMode.HEAT_COOL and self._phase.enabled:
                # Already in the combined mode: its phase is kept between the
                # targets, as in _check_phase.
                phase = self._wanted_phase(self._phase.phase)
                self._phase.start(phase)
                await self._modes.async_activate(phase, HVACMode.HEAT_COOL)
            else:
                self._phase.leave()
                if hvac_mode is HVACMode.OFF:
                    await self._modes.async_turn_off()
                else:
                    await self._modes.async_activate(hvac_mode, hvac_mode)
        if hvac_mode is not HVACMode.OFF:
            self._modes.last_on_mode = hvac_mode
        # A source already in its mode sends no update: the new targets
        # are sent from here.
        self._update_phase()
        self._observe_sources()
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        """Turn on in the last used mode, else the first configured mode."""
        if self._modes.current() is not HVACMode.OFF:
            return

        mode = self._modes.next_mode()
        if mode is not HVACMode.OFF:
            await self.async_set_hvac_mode(mode)

    async def async_turn_off(self) -> None:
        """Turn off every source that is on."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def _async_source_call(self, service: str, data: dict[str, Any]) -> None:
        """Call a climate service on the active source, or refuse it when off."""
        source = self._modes.active_source()
        if source is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_active_mode",
            )
        await self._sources.async_call(service, source, data)
