"""Base entity for C-Bus.

All C-Bus entity platforms (light, switch, event) inherit from
:class:`CbusEntity` to get consistent ``device_info`` and naming.

Device hierarchy in Home Assistant::

    C-Bus Network (device: hub)
    └── Unit 12 — "Kitchen Dimmer" (device: dimmer)
        ├── Group 1 — "Kitchen Downlights" (entity: light)
        └── Group 2 — "Kitchen Pendants"   (entity: light)
    └── Unit 15 — "Lounge Relay" (device: relay)
        └── Group 3 — "Lounge Lamp"        (entity: switch)

When C-Gate XML import data is available, each unit becomes an HA
device with its catalog number, serial number, and firmware as
device attributes.  Without import data, entities are grouped under
a single network-level device.

Entity naming:
    - With import: ``"{group.name}"`` (e.g. "Kitchen Downlights")
    - Without import: ``"C-Bus {app_name} Group {address}"``
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import CbusCoordinator


class CbusEntity(CoordinatorEntity["CbusCoordinator"]):
    """Base class for all C-Bus entities.

    Provides:
    - Unique ID generation: ``cbus_{entry_id}_{app_id}_{group}``
    - Device info pointing to a single network-level device per entry
    - ``_attr_has_entity_name = True`` so HA uses the device name prefix
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CbusCoordinator,
        app_id: int,
        group: int,
        name: str | None = None,
    ) -> None:
        """Initialise a C-Bus entity.

        Args:
            coordinator: The owning CbusCoordinator.
            app_id: C-Bus application ID (e.g. 0x38 for lighting).
            group: C-Bus group address (0-255).
            name: Optional friendly name (from XML import).
        """
        super().__init__(coordinator)
        self._app_id = app_id
        self._group = group

        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"cbus_{entry_id}_{app_id}_{group}"

        if name:
            self._attr_name = name
        else:
            self._attr_name = f"Group {group}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the C-Bus network hub."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name="C-Bus",
            manufacturer="Clipsal / Schneider Electric",
            model="PCI/CNI",
        )
