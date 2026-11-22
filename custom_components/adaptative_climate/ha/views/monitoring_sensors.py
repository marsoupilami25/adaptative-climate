"""The two monitoring binary sensors (spec §4.1)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.util import slugify

from ...core.model.problems import SENSOR_SOURCES, SENSOR_TEMPERATURES
from ..entry.host import EntryHost
from .climate_view import device_info


class MonitoringSensor(BinarySensorEntity):
    """`binary_sensor.<name>_monitoring_sources` / `..._monitoring_temperatures`."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, host: EntryHost, sensor: str) -> None:
        self._host = host
        self._sensor = sensor
        self._attr_translation_key = f"monitoring_{sensor}"
        self._attr_unique_id = f"{host.model.entry_id}_monitoring_{sensor}"
        self._attr_device_info = device_info(host)
        # Spec §2.1: the entity id does not follow the language of Home Assistant (the
        # name shown does); a free id at the first registration, kept by the registry after
        self.entity_id = f"binary_sensor.{slugify(host.model.name)}_monitoring_{sensor}"
        self._written: str | None = None

    async def async_added_to_hass(self) -> None:
        """Registered as a view of the host."""
        self._host.views.append(self)
        self._host.sensor_entity_ids[self._sensor] = self.entity_id

    async def async_will_remove_from_hass(self) -> None:
        """No longer a view."""
        if self in self._host.views:
            self._host.views.remove(self)

    def refresh(self) -> None:
        """Written after each stimulus, when it changed."""
        signature = repr(self._problems())
        if signature == self._written or self.hass is None:
            return
        self._written = signature
        self.async_write_ha_state()

    def _problems(self) -> list[dict[str, Any]]:
        return self._host.monitoring.reported(self._sensor)

    @property
    def available(self) -> bool:
        """Never unavailable while the entry is loaded (MON-SENS-4)."""
        return True

    @property
    def is_on(self) -> bool:
        """On while at least one of its problems is reported (MON-SENS-1)."""
        return bool(self._problems())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """MON-SENS-2."""
        attributes: dict[str, Any] = {"problems": self._problems()}
        if self._sensor == SENSOR_TEMPERATURES:
            attributes["max_gap"] = self._host.model.monitoring_gap
        return attributes


def monitoring_sensors(host: EntryHost) -> list[MonitoringSensor]:
    """Both sensors of an entry."""
    return [MonitoringSensor(host, SENSOR_SOURCES), MonitoringSensor(host, SENSOR_TEMPERATURES)]
