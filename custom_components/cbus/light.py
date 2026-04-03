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
    → light.cbus_kitchen_downlights (unique_id: "cbus_254_56_1")

This is a stub — implementation follows the coordinator.
"""

from __future__ import annotations
