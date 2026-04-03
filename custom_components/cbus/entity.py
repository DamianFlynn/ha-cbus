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

This is a stub — implementation follows the coordinator.
"""

from __future__ import annotations
