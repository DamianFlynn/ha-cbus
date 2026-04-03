"""Config flow for C-Bus integration.

The config flow guides the user through setting up a C-Bus connection:

1. **Connection type** — TCP (CNI) or Serial (PCI).
2. **Connection details** — host:port for TCP, device path for serial.
3. **Optional import** — upload a C-Gate ``HOME.xml`` or Toolkit ``.cbz``
   file to pre-populate group names and unit-to-device mapping.
4. **Confirmation** — test connection, display discovered groups.

The flow stores the following in ``config_entry.data``::

    {
        "connection_type": "tcp" | "serial",
        "host": "192.168.1.50",    # TCP only
        "port": 10001,              # TCP only
        "device": "/dev/ttyUSB0",   # serial only
        "network": 254,             # C-Bus network number
        "project_data": { ... },    # optional C-Gate XML import
    }

Options flow:
    After initial setup, the options flow allows adding/editing group
    names and adjusting connection parameters without removing the entry.

This is a stub — implementation follows the coordinator and protocol.
"""

from __future__ import annotations
