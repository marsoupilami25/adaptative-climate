"""External sensors (spec §1.3.5.2): the value of the temperature sensor written to them."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..model.events import HA_START, T_TEMPERATURE, XS_CALL_FAILED, XS_USABLE, Event
from ..model.values import TEMPERATURE_UNITS, clean, convert_temperature, round_to_step

if TYPE_CHECKING:
    from .entity import ACEntity

RESEND_TIMER = "resend"


class ExternalSensors:
    """Writes temperature@T to each external sensor entity, at once (ENT-EXT-1)."""

    def __init__(self, entity: ACEntity) -> None:
        self._entity = entity
        self._out_of_range: set[str] = set()

    def handle(self, event: Event) -> None:
        """Events of the external sensors."""
        entity = self._entity
        if not entity.entry.external_sensors:
            return
        kind = event.kind
        if kind == HA_START:
            self._write_all(entity.sensor_temperature())
        elif kind == T_TEMPERATURE:
            self._write_all(event.value)
        elif kind == XS_USABLE:
            value = entity.sensor_temperature()
            if value is not None:
                self._write(event.sender, value)
        elif kind == XS_CALL_FAILED:
            entity.notify.log("warning", f"Writing the temperature to {event.sender} failed")
        elif event.is_timeout(RESEND_TIMER):
            self._write_all(entity.sensor_temperature())

    def _write_all(self, value: float | None) -> None:
        """Write to every external sensor; the periodic rewrite runs while valid (ENT-EXT-4, 5)."""
        timers = self._entity.timers
        if value is None:
            timers.cancel(RESEND_TIMER)
            return
        for entity_id in self._entity.entry.external_sensors:
            self._write(entity_id, value)
        timers.start(RESEND_TIMER, self._entity.entry.external_sensor_resend_timer)

    def _write(self, entity_id: str, value: float) -> None:
        """ENT-EXT-2: converted, rounded to its step, not written out of its range."""
        entity = self._entity
        port = entity.xs_ports.get(entity_id)
        if port is None:
            return
        attributes = port.attributes()
        if attributes is None:
            return
        unit = attributes.unit if attributes.unit in TEMPERATURE_UNITS else entity.entry.unit
        converted = convert_temperature(value, entity.entry.unit, unit)
        if attributes.step:
            converted = round_to_step(converted, attributes.step)
        converted = clean(converted)
        low, high = attributes.minimum, attributes.maximum
        if (low is not None and converted < low) or (high is not None and converted > high):
            if entity_id not in self._out_of_range:
                self._out_of_range.add(entity_id)
                entity.notify.log(
                    "warning",
                    f"{converted} {unit} is out of the range of {entity_id} ({low} to {high}): not written",
                )
            return
        if entity_id in self._out_of_range:
            self._out_of_range.discard(entity_id)
            entity.notify.log("info", f"{converted} {unit} is back in the range of {entity_id}")
        port.set_value(converted)
