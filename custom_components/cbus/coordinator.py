"""DataUpdateCoordinator for C-Bus.

The coordinator sits between the Home Assistant entity platforms and the
pycbus protocol layer.  Its responsibilities:

1. **Lifecycle management** — create, start, and stop the
   :class:`pycbus.protocol.CbusProtocol` state machine.
2. **State cache** — maintain a dict of ``{(app_id, group): level}``
   representing the last-known state of every group on the bus.
3. **Event dispatch** — when the protocol receives a monitor SAL event
   (e.g. a level change from a wall switch), update the cache and call
   ``async_set_updated_data()`` to notify all listening entities.
4. **Command proxy** — entity platforms call coordinator methods
   (e.g. ``async_turn_on(group, level, ramp)``) which encode the SAL
   command and queue it for transmission.

Refresh model:
    This coordinator does **not** poll.  C-Bus is inherently push-based:
    the PCI/CNI sends monitor events for every SAL on the network.
    The coordinator's ``_async_update_data`` is a no-op; all state
    changes flow through the protocol's event callback.

This is a stub — implementation follows the protocol layer.
"""

from __future__ import annotations
