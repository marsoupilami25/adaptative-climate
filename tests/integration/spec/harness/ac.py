"""The AC entity and its monitoring sensors, as Home Assistant shows them.

Only the names of the spec (§2): `climate.<name>`,
`binary_sensor.<name>_monitoring_sources`, `..._monitoring_temperatures`, and
the attributes of §2.2 and §4.1. The user requests are service calls of
Home Assistant, as from a card or an automation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.util import slugify

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, State

    from .bench import Bench


class Shown:
    """An entity as Home Assistant shows it now."""

    def __init__(self, bench: Bench, entity_id: str) -> None:
        self._bench = bench
        self.entity_id = entity_id

    @property
    def hass(self) -> HomeAssistant:
        return self._bench.hass

    @property
    def state_object(self) -> State | None:
        return self.hass.states.get(self.entity_id)

    @property
    def exists(self) -> bool:
        return self.state_object is not None

    @property
    def state(self) -> str | None:
        """The state shown; None when the entity does not exist."""
        state = self.state_object
        return None if state is None else state.state

    @property
    def available(self) -> bool:
        return self.state not in (None, STATE_UNAVAILABLE)

    @property
    def attributes(self) -> dict[str, Any]:
        state = self.state_object
        return {} if state is None else dict(state.attributes)

    def attr(self, name: str) -> Any:
        """An attribute; None when not shown."""
        return self.attributes.get(name)

    def __repr__(self) -> str:
        return f"<{self.entity_id} {self.state} {self.attributes}>"


class AC(Shown):
    """`climate.<name>`."""

    def __init__(self, bench: Bench, name: str) -> None:
        super().__init__(bench, f"climate.{slugify(name)}")
        self.name = name
        self.monitoring_sources = Shown(bench, f"binary_sensor.{slugify(name)}_monitoring_sources")
        self.monitoring_temperatures = Shown(
            bench, f"binary_sensor.{slugify(name)}_monitoring_temperatures"
        )

    # --- What is shown ---------------------------------------------------------------

    @property
    def hvac_mode(self) -> str | None:
        """The mode shown: None when unknown (WAITING) or unavailable."""
        state = self.state
        return None if state in (None, STATE_UNAVAILABLE, STATE_UNKNOWN) else state

    @property
    def features(self) -> int:
        return int(self.attr("supported_features") or 0)

    # --- User requests ------------------------------------------------------------------

    async def _call(self, service: str, **data: Any) -> None:
        await self.hass.services.async_call(
            "climate", service, {"entity_id": self.entity_id, **data}, blocking=True
        )
        await self.hass.async_block_till_done()

    async def set_hvac_mode(self, mode: str) -> None:
        await self._call("set_hvac_mode", hvac_mode=mode)

    async def turn_on(self) -> None:
        await self._call("turn_on")

    async def turn_off(self) -> None:
        await self._call("turn_off")

    async def set_temperature(self, **targets: Any) -> None:
        """`temperature=...`, or `target_temp_low=..., target_temp_high=...`."""
        await self._call("set_temperature", **targets)

    async def set_fan_mode(self, fan_mode: str) -> None:
        await self._call("set_fan_mode", fan_mode=fan_mode)

    async def set_swing_mode(self, swing_mode: str) -> None:
        await self._call("set_swing_mode", swing_mode=swing_mode)

    async def set_swing_horizontal_mode(self, swing_horizontal_mode: str) -> None:
        await self._call("set_swing_horizontal_mode", swing_horizontal_mode=swing_horizontal_mode)
