"""Switch platform for C-Bus Enable Control application (app 203 / 0xCB).

The Enable Control application provides simple binary on/off control for
C-Bus groups that don't need dimming.  Each group maps to a
:class:`homeassistant.components.switch.SwitchEntity`.

SAL commands:
    - **Enable** (ON):  group level -> 0xFF
    - **Disable** (OFF): group level -> 0x00

There are no ramp rates or intermediate levels for Enable groups.

Entity mapping::

    CbusGroup(address=10, name="Garden Irrigation")
    -> switch.cbus_garden_irrigation (unique_id: "cbus_254_203_10")

Reference: *Chapter 08 -- C-Bus Enable Control Application*
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity

from pycbus.constants import ApplicationId

from .entity import CbusEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import CbusCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up C-Bus switch entities from a config entry."""
    from .const import DOMAIN

    coordinator: CbusCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[CbusSwitch] = []
    for (app_id, group), _level in coordinator.data.items():
        if app_id == ApplicationId.ENABLE:
            entities.append(CbusSwitch(coordinator, group))

    async_add_entities(entities)

    # Register a listener to add new groups as they appear.
    known_groups: set[int] = {
        g for (a, g) in coordinator.data if a == ApplicationId.ENABLE
    }

    def _on_data_update() -> None:
        new_entities: list[CbusSwitch] = []
        for (app_id, group), _level in coordinator.data.items():
            if app_id == ApplicationId.ENABLE and group not in known_groups:
                known_groups.add(group)
                new_entities.append(CbusSwitch(coordinator, group))
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_on_data_update))


class CbusSwitch(CbusEntity, SwitchEntity):
    """Representation of a C-Bus Enable group as an HA switch entity."""

    def __init__(
        self,
        coordinator: CbusCoordinator,
        group: int,
        name: str | None = None,
    ) -> None:
        super().__init__(
            coordinator,
            app_id=ApplicationId.ENABLE,
            group=group,
            name=name,
        )

    @property
    def is_on(self) -> bool:
        """Return True if the switch is on (enabled)."""
        level = self.coordinator.data.get((ApplicationId.ENABLE, self._group))
        return level is not None and level > 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on (enable) the group."""
        await self.coordinator.async_enable_on(group=self._group)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off (disable) the group."""
        await self.coordinator.async_enable_off(group=self._group)
