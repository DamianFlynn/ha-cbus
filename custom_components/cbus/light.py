"""Light platform for C-Bus Lighting application (app 56 / 0x38).

Each C-Bus lighting group maps to a :class:`homeassistant.components.light.LightEntity`.

Supported features:
    - **Brightness** (0-255): directly mapped from C-Bus level (0x00-0xFF).
    - **Transition**: mapped to the closest C-Bus ramp rate using
      :data:`pycbus.constants.RAMP_DURATIONS`.
    - **Turn on / turn off**: uses SAL ON (0x79) and OFF (0x01) commands.
    - **State tracking**: updated in real-time from PCI monitor events.

Color modes:
    C-Bus lighting is a single-channel dimmer protocol.  The only
    supported color mode is ``ColorMode.BRIGHTNESS`` (or ``ONOFF`` for
    relay-only groups).  RGB and colour temperature are not applicable.

Entity mapping::

    CbusGroup(address=1, name="Kitchen Downlights")
    -> light.cbus_kitchen_downlights (unique_id: "cbus_254_56_1")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_TRANSITION,
    ColorMode,
    LightEntity,
)

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
    """Set up C-Bus light entities from a config entry."""
    from .const import DOMAIN

    coordinator: CbusCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Create a light entity for every lighting group already in the state cache.
    # As new groups appear from SAL events, entities are added dynamically.
    entities: list[CbusLight] = []
    for (app_id, group), _level in coordinator.data.items():
        if app_id == ApplicationId.LIGHTING:
            entities.append(CbusLight(coordinator, group))

    async_add_entities(entities)

    # Register a listener to add new groups as they appear.
    known_groups: set[int] = {
        g for (a, g) in coordinator.data if a == ApplicationId.LIGHTING
    }

    def _on_data_update() -> None:
        new_entities: list[CbusLight] = []
        for (app_id, group), _level in coordinator.data.items():
            if app_id == ApplicationId.LIGHTING and group not in known_groups:
                known_groups.add(group)
                new_entities.append(CbusLight(coordinator, group))
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_on_data_update))


class CbusLight(CbusEntity, LightEntity):
    """Representation of a C-Bus lighting group as an HA light entity.

    Brightness is natively 0-255, matching C-Bus levels exactly.
    Transition times are mapped to the nearest C-Bus ramp rate.
    """

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes: ClassVar[set[ColorMode]] = {ColorMode.BRIGHTNESS}

    def __init__(
        self,
        coordinator: CbusCoordinator,
        group: int,
        name: str | None = None,
    ) -> None:
        super().__init__(
            coordinator,
            app_id=ApplicationId.LIGHTING,
            group=group,
            name=name,
        )

    @property
    def brightness(self) -> int | None:
        """Return the current brightness (0-255)."""
        level = self.coordinator.data.get((ApplicationId.LIGHTING, self._group))
        return level

    @property
    def is_on(self) -> bool:
        """Return True if the light is on."""
        level = self.coordinator.data.get((ApplicationId.LIGHTING, self._group))
        return level is not None and level > 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on, optionally with brightness and transition."""
        brightness: int | None = kwargs.get(ATTR_BRIGHTNESS)
        transition: float | None = kwargs.get(ATTR_TRANSITION)

        if brightness is not None:
            await self.coordinator.async_light_ramp(
                group=self._group,
                level=brightness,
                transition=transition or 0.0,
            )
        elif transition is not None:
            # Transition without brightness: ramp to full.
            await self.coordinator.async_light_ramp(
                group=self._group,
                level=255,
                transition=transition,
            )
        else:
            await self.coordinator.async_light_on(group=self._group)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off, optionally with transition."""
        transition: float | None = kwargs.get(ATTR_TRANSITION)

        if transition is not None:
            await self.coordinator.async_light_ramp(
                group=self._group,
                level=0,
                transition=transition,
            )
        else:
            await self.coordinator.async_light_off(group=self._group)
