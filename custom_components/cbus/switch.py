"""Switch platform for C-Bus Enable Control application (app 203 / 0xCB).

The Enable Control application provides simple binary on/off control for
C-Bus groups that don’t need dimming.  Each group maps to a
:class:`homeassistant.components.switch.SwitchEntity`.

SAL commands:
    - **Enable** (ON):  group level → 0xFF
    - **Disable** (OFF): group level → 0x00

There are no ramp rates or intermediate levels for Enable groups.

Entity mapping::

    CbusGroup(address=10, name="Garden Irrigation")
    → switch.cbus_garden_irrigation (unique_id: "cbus_254_203_10")

Reference: *Chapter 08 — C-Bus Enable Control Application*

This is a stub — implementation follows the coordinator.
"""

from __future__ import annotations
