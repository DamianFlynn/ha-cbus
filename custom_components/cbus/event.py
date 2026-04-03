"""Event platform for C-Bus Trigger Control application (app 202 / 0xCA).

Trigger groups are *fire-and-forget* events — they have no persistent
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
    → event.cbus_all_off (unique_id: "cbus_254_202_5")

Reference: *Chapter 07 — C-Bus Trigger Control Application*

This is a stub — implementation follows the coordinator.
"""

from __future__ import annotations
