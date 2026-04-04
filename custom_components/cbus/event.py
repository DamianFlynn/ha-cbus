"""Event platform for C-Bus Trigger Control application (app 202 / 0xCA).

Trigger groups are *fire-and-forget* events -- they have no persistent
state.  A trigger is sent (e.g. from a wall-mounted scene button) and
received by all units listening on that trigger group.  In Home Assistant,
each trigger group maps to a :class:`homeassistant.components.event.EventEntity`.

SAL structure:
    - Trigger Group (0-255): identifies the trigger.
    - Action Selector (0-255): identifies which action within the group.

HA event data::

    {
        "event_type": "trigger_action",
        "group": 5,
        "action": 0
    }

Entity mapping::

    CbusGroup(address=5, name="All Off")
    -> event.cbus_all_off (unique_id: "cbus_254_202_5")

Reference: *Chapter 07 -- C-Bus Trigger Control Application*
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from homeassistant.components.event import EventEntity

from pycbus.constants import ApplicationId

from .entity import CbusEntity

if TYPE_CHECKING:
    import collections.abc

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import CbusCoordinator

EVENT_TRIGGER_ACTION = "trigger_action"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up C-Bus event entities from a config entry."""
    from .const import DOMAIN

    coordinator: CbusCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Track known trigger groups so we can add new ones dynamically.
    known_groups: set[int] = set()
    entities: list[CbusTriggerEvent] = []

    # Pre-populate from any trigger groups already seen in the state cache.
    for app_id, group in coordinator.data:
        if app_id == ApplicationId.TRIGGER:
            known_groups.add(group)
            entities.append(CbusTriggerEvent(coordinator, group))

    async_add_entities(entities)

    def _on_trigger(group: int, action: int) -> None:
        """Handle a trigger SAL from the coordinator."""
        if group not in known_groups:
            known_groups.add(group)
            entity = CbusTriggerEvent(coordinator, group)
            async_add_entities([entity])
            # Fire immediately on the new entity after it's added.
            entity.fire_trigger(action)
        else:
            # Find and fire on the existing entity via hass event bus
            # is not needed — the entity registers its own trigger callback.
            pass

    unsub = coordinator.on_trigger(_on_trigger)
    entry.async_on_unload(unsub)


class CbusTriggerEvent(CbusEntity, EventEntity):
    """Representation of a C-Bus trigger group as an HA event entity.

    Fires ``trigger_action`` events when a trigger SAL is received
    for this group.  The action selector is included in the event data.
    """

    _attr_event_types: ClassVar[list[str]] = [EVENT_TRIGGER_ACTION]

    def __init__(
        self,
        coordinator: CbusCoordinator,
        group: int,
        name: str | None = None,
    ) -> None:
        super().__init__(
            coordinator,
            app_id=ApplicationId.TRIGGER,
            group=group,
            name=name,
        )
        self._unsub_trigger: collections.abc.Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Register trigger callback when entity is added."""
        await super().async_added_to_hass()
        self._unsub_trigger = self.coordinator.on_trigger(self._on_trigger)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister trigger callback when entity is removed."""
        if self._unsub_trigger is not None:
            self._unsub_trigger()
            self._unsub_trigger = None
        await super().async_will_remove_from_hass()

    def _on_trigger(self, group: int, action: int) -> None:
        """Handle a trigger event from the coordinator."""
        if group == self._group:
            self.fire_trigger(action)

    def fire_trigger(self, action: int) -> None:
        """Fire the HA event with the action selector."""
        self._trigger_event(EVENT_TRIGGER_ACTION, {"action": action})
