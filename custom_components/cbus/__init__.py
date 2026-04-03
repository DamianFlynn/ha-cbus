"""C-Bus integration for Home Assistant.

This custom integration provides native Home Assistant support for
Clipal C-Bus home automation networks, communicating directly with a
PCI (serial) or CNI (TCP/IP) interface — no C-Gate middleware required.

Integration architecture::

    Home Assistant
    ├── config_flow.py   — UI-guided setup (TCP/serial, optional XML import)
    ├── coordinator.py   — manages pycbus Protocol lifecycle + state cache
    ├── entity.py        — shared base entity with device_info
    ├── light.py         — Lighting application (app 56) → LightEntity
    ├── switch.py        — Enable Control (app 203) → SwitchEntity
    └── event.py         — Trigger Control (app 202) → EventEntity

Versioning:
    The integration follows CalVer (YYYY.M.patch) to align with
    Home Assistant’s release cadence.  The underlying pycbus library
    uses SemVer independently.

Setup entry points:
    - ``async_setup_entry``  — called when HA loads a config entry
    - ``async_unload_entry`` — called when HA removes/reloads the entry

Platforms loaded:
    PLATFORMS = ["light", "switch", "event"]

This is a stub — the setup logic will be implemented once the
protocol and coordinator layers are complete.
"""

from __future__ import annotations
