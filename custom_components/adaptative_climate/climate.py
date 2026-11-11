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
- Waiting: the source of the mode became unavailable. The mode is unknown
  (hvac_mode None), the entity shows the targets, range and settings of
  the mode waited for, and keeps the changes for its source (see
  ModeTracker.waiting). The combined HEAT_COOL stays HEAT_COOL.
- Commands: set_temperature (targets, optional mode), set_hvac_mode,
  turn_on/off, fan and swing (sent to the active source, or remembered
  for the mode when no source can get them).
- Restore: the parts save and read their own data; the entity merges it.
  What the sources offer is kept by the coordinator (coordinator.known).
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
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
from .engine.model import FAN, SETTINGS, SWING, SWING_HORIZONTAL, TARGETS, Setting, TargetKey
from .engine.modes import ModeTracker
from .engine.phase import CombinedPhase, wanted_phase
from .engine.profiles import build_profiles
from .engine.settings_memory import SettingsMemory
from .engine.sources import Sources
from .engine.target_sync import TargetSync
from .engine.targets import TargetStore

_LOGGER = logging.getLogger(__name__)

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
    # The remembered fan and swing settings are not kept in the history.
    # The saved targets are, to follow them over time.
    _unrecorded_attributes = frozenset({"saved_settings"})

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
        """Restore what the sources offer, the settings, targets, phase and mode waited for."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_extra_data()) is not None:
            data = last.as_dict()
            self.coordinator.async_restore_known(data)
            self._modes.restore(data)
            self._memory.restore(data)
            self._target_store.restore(data)
            self._targets.apply_gap([ATTR_TARGET_TEMP_LOW])
            self._phase.restore(data)
        self._update_phase()
        self._observe_sources()
        self._targets.start_resync()

    async def async_will_remove_from_hass(self) -> None:
        """Stop the timers."""
        self._targets.stop_timers()
        self._phase.stop_timers()
        await super().async_will_remove_from_hass()

    @property
    def extra_restore_state_data(self) -> RestoredExtraData:
        """Save what the sources offer, the settings, targets, phase and mode waited for."""
        return RestoredExtraData(
            {
                **self.coordinator.known.as_dict(),
                **self._modes.as_dict(),
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
            # phase yet (or is unavailable).
            self._follow_lost()
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
        # Entering a mode: asked by this entity, or the active source back
        # in its mode after being unavailable, which get the targets (and
        # the settings) of the entity. Otherwise the source was turned on
        # elsewhere (remote, app), and gives its targets.
        requested = False
        if before is None:
            waiting = self._modes.waiting
            back = waiting is not None and waiting[:2] == (source, source_mode)
            self._modes.waiting = None
            requested = self._modes.take_request(source, source_mode) or back
            if back:
                self.coordinator.config_entry.async_create_task(
                    self.hass,
                    self._memory.async_send(source_mode, source),
                    f"{DOMAIN} settings {source}",
                )
        self._memory.observe(source_mode, values, before)
        self._targets.observe(key, source_mode, values, before, requested=requested)

    @callback
    def _follow_lost(self) -> None:
        """Wait for the active source when it becomes unavailable.

        Forgotten once it is back in another mode or off (it was changed
        meanwhile), or when the user switches modes.
        """
        waiting = self._modes.waiting
        if self._observed is not None:
            key = self._observed[0]
            source_mode = key[1] or key[0]
            entity_id = self._sources.mode_sources.get(source_mode)
            if entity_id is not None and self._sources.state(entity_id) is None:
                self._modes.waiting = (entity_id, source_mode, key[0])
        elif waiting is not None and self._sources.state(waiting[0]) is not None:
            self._modes.waiting = None

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
            self._modes.phase_lost,
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

    @callback
    def async_write_ha_state(self) -> None:
        """Tell the sensors the target mismatches, gaps and missing sources, then write the state.

        The monitoring gets the targets the source does not show, the target
        gap sensor those shown otherwise than kept, the source unavailable
        sensor the sources of the selected mode that are unavailable.
        """
        self.coordinator.async_set_target_mismatches(self._targets.mismatches())
        self.coordinator.async_set_target_gaps(self._targets.gaps(self._range_supported()))
        self.coordinator.async_set_missing_sources(self._modes.missing_sources())
        super().async_write_ha_state()

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

        Target features are combined over the configured modes (what each
        mode uses, see ModeProfile.target_features), so they do not change
        with the mode: an entity whose modes all use a single target never
        shows low/high, even off. Other features of the sources (presets,
        humidity...) are dropped: exposing them without implementing them
        makes Home Assistant fail when the entity is added. Fan and swing
        (vertical and horizontal) are shown when at least one source lists an
        option, even while unavailable (see SettingsMemory.offered_features),
        so the card keeps its size across modes; a mode whose source lacks
        them shows no option (see _setting_options).
        """
        features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        for mode in self._modes.modes[1:]:
            features |= self._modes.profile(mode).target_features()
        return features | self._memory.offered_features()

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

    def _range_supported(self) -> bool:
        """Return True when the entity has the low/high targets."""
        return ClimateEntityFeature.TARGET_TEMPERATURE_RANGE in self.supported_features

    def _shown_target(self, attr: str) -> float | None:
        """Return a target attribute as shown by the entity (see TargetSync.shown)."""
        return self._targets.shown(attr, self._range_supported())

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
    def target_temperature_step(self) -> float:
        """Return the step of the entity, from the steps of its sources (see Sources.step)."""
        return self._sources.step()

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return self._modes.temperature_range()[0]

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return self._modes.temperature_range()[1]

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current mode, unknown (None) while waiting for the source of a mode."""
        if self._modes.waiting_mode is not None:
            return None
        return self._modes.current()

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return OFF plus every mode that has a source, HEAT_COOL when combined."""
        return self._modes.modes

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current action of the active source (unknown while waiting)."""
        if self._modes.waiting_mode is not None:
            return None
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

    def _setting_mode(self) -> HVACMode | None:
        """Return the mode whose settings are shown.

        The selected mode (waited for too). Off, the first mode when every
        mode is synchronized (they share their settings), else none.
        """
        mode = self._modes.selected()
        if mode is not HVACMode.OFF:
            return self._modes.selected_source_mode()
        if self._memory.all_synchronized():
            return next(iter(self._sources.mode_sources), None)
        return None

    def _setting_options(self, setting: Setting) -> list[Any]:
        """Return the options shown for a setting (empty when none).

        Those of the source of the selected mode, known from when it was
        last usable while it is away. Off, the options shared by the sources
        when every mode is synchronized, else none.
        """
        if self._modes.selected() is HVACMode.OFF:
            if self._memory.all_synchronized():
                return self._memory.shared_options(setting)
            return []
        return self._memory.options(self._modes.selected_source(), setting)

    def _setting_value(self, setting: Setting) -> Any:
        """Return the value shown for a setting, None when it has no option.

        That of the active source; with no source running (waiting, or off
        with every mode synchronized), the one remembered for the mode.
        """
        if not self._setting_options(setting):
            return None
        if self._modes.active_source() is not None and self._modes.waiting_mode is None:
            return self._active_attr(setting.attr)
        mode = self._setting_mode()
        return None if mode is None else self._memory.value(mode, setting)

    @property
    def fan_mode(self) -> str | None:
        """Return the fan mode of the active source."""
        return self._setting_value(FAN)

    @property
    def fan_modes(self) -> list[str]:
        """Return the fan modes of the active source."""
        return self._setting_options(FAN)

    @property
    def swing_mode(self) -> str | None:
        """Return the swing mode of the active source."""
        return self._setting_value(SWING)

    @property
    def swing_modes(self) -> list[str]:
        """Return the swing modes of the active source."""
        return self._setting_options(SWING)

    @property
    def swing_horizontal_mode(self) -> str | None:
        """Return the horizontal swing mode of the active source."""
        return self._setting_value(SWING_HORIZONTAL)

    @property
    def swing_horizontal_modes(self) -> list[str]:
        """Return the horizontal swing modes of the active source."""
        return self._setting_options(SWING_HORIZONTAL)

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
            # does not show, on the step of the entity (before the offset and
            # the step of the source).
            "saved_targets": {target: self._target_store[target] for target in TARGETS},
            # Fan and swing settings remembered by each configured mode,
            # sent back when the entity switches to it.
            "saved_settings": self._memory.by_mode(),
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
        mode = HVACMode(hvac_mode) if hvac_mode is not None else self._modes.selected()
        if mode is HVACMode.OFF:
            mode = self._modes.next_mode()
        self._targets.set(
            {attr: float(kwargs[attr]) for attr in TARGETS if kwargs.get(attr) is not None},
            mode,
        )

        if hvac_mode is not None and HVACMode(hvac_mode) != self._modes.selected():
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

    def _check_setting(self, setting: Setting) -> None:
        """Refuse a fan or swing change the selected mode does not offer.

        Runs before the check of Home Assistant, whose message would only
        list no valid option.
        """
        if self._setting_mode() is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_active_mode",
            )
        if not self._setting_options(setting):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="setting_not_in_mode",
                translation_placeholders={"hvac_mode": str(self._modes.selected())},
            )

    async def async_handle_set_fan_mode_service(self, fan_mode: str) -> None:
        """Check the current mode has a fan, then let Home Assistant check the value."""
        self._check_setting(FAN)
        await super().async_handle_set_fan_mode_service(fan_mode)

    async def async_handle_set_swing_mode_service(self, swing_mode: str) -> None:
        """Check the current mode has a swing, then let Home Assistant check the value."""
        self._check_setting(SWING)
        await super().async_handle_set_swing_mode_service(swing_mode)

    async def async_handle_set_swing_horizontal_mode_service(
        self, swing_horizontal_mode: str
    ) -> None:
        """Check the current mode has a horizontal swing, then let Home Assistant check the value."""
        self._check_setting(SWING_HORIZONTAL)
        await super().async_handle_set_swing_horizontal_mode_service(swing_horizontal_mode)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode of the active source (or remember it, see _async_set_setting).

        Home Assistant has already checked that fan_mode is in fan_modes.
        """
        await self._async_set_setting(FAN, fan_mode)

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set the swing mode of the active source (or remember it, see _async_set_setting).

        Home Assistant has already checked that swing_mode is in swing_modes.
        """
        await self._async_set_setting(SWING, swing_mode)

    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode: str) -> None:
        """Set the horizontal swing mode of the active source (or remember it).

        Home Assistant has already checked that swing_horizontal_mode is in
        swing_horizontal_modes.
        """
        await self._async_set_setting(SWING_HORIZONTAL, swing_horizontal_mode)

    async def _async_set_setting(self, setting: Setting, value: str) -> None:
        """Send a fan or swing value to the active source.

        With no source running (waiting for the source of the mode, or off
        with every mode synchronized), it is remembered for the mode and
        sent to its source when the mode starts.
        """
        source = self._modes.active_source()
        if source is not None and self._modes.waiting_mode is None:
            await self._sources.async_call(setting.service, source, {setting.attr: value})
            return
        mode = self._setting_mode()
        if mode is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_active_mode",
            )
        self._memory.remember(mode, setting, value)
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Switch to a mode.

        The source of the mode is turned on and gets the remembered fan and
        swing settings of the mode, then every other source that is not off
        is turned off, even when several were turned on elsewhere. If the
        source fails, the others keep running; a source that does not turn
        off is tried again later (see async_enforce_exclusive). Home
        Assistant has already checked that hvac_mode is in hvac_modes.
        The combined HEAT_COOL runs the heat or cool source (see wanted_phase).
        A mode whose source is unavailable is refused before anything is
        changed: Home Assistant would skip the call to that source silently.
        So is a mode its source does not offer: the source would reject it.
        The combined HEAT_COOL needs both of its sources.
        """
        if hvac_mode is not HVACMode.OFF:
            self._modes.check(hvac_mode)
        self._modes.waiting = None

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
        """Turn on in the last used mode, else the first configured mode.

        Nothing to do while on, or waiting for the source of a mode.
        """
        if self._modes.selected() is not HVACMode.OFF:
            return

        mode = self._modes.next_mode()
        if mode is not HVACMode.OFF:
            await self.async_set_hvac_mode(mode)

    async def async_turn_off(self) -> None:
        """Turn off every source that is on."""
        await self.async_set_hvac_mode(HVACMode.OFF)
