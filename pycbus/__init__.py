"""pycbus — Pure-Python async C-Bus PCI/CNI protocol library.

This package implements the Clipsal C-Bus serial protocol as documented in the
*C-Bus Serial Interface User Guide* and the various application chapter PDFs
from Schneider Electric.  It talks directly to a C-Bus PCI (serial) or CNI
(TCP/IP) interface, bypassing the C-Gate middleware entirely.

Architecture overview::

    ┌──────────────┐
    │  HA platform  │  light / switch / event / climate …
    └──────┬───────┘
           │  async calls
    ┌──────▼───────┐
    │  Coordinator  │  manages protocol lifecycle & state cache
    └──────┬───────┘
           │
    ┌──────▼───────┐
    │   Protocol    │  PCI init sequence, SAL framing, state machine
    └──────┬───────┘
           │
    ┌──────▼───────┐
    │  Transport    │  TcpTransport (CNI) / SerialTransport (PCI)
    └──────────────┘

Key modules:

- :mod:`pycbus.checksum`    — Two's-complement checksum used in every frame.
- :mod:`pycbus.constants`   — Protocol enumerations (apps, opcodes, options).
- :mod:`pycbus.model`       — Dataclass topology: project → network → app → group.
- :mod:`pycbus.commands`    — SAL command builders (lighting, trigger, enable).
- :mod:`pycbus.transport`   — Async transport protocol (TCP / serial).
- :mod:`pycbus.protocol`    — PCI/CNI init and runtime state machine.
- :mod:`pycbus.applications`— Per-application SAL definitions (extensible).
- :mod:`pycbus.exceptions`  — Library exception hierarchy.

Minimum Python version: 3.12 (uses modern ``type`` statement support).

License: Apache-2.0
"""

__version__ = "0.1.0"

from .exceptions import CbusConnectionError, CbusError, CbusTimeoutError
from .protocol import CbusProtocol, ProtocolState
from .transport import CbusTransport, SerialTransport, TcpTransport

__all__ = [
    "CbusConnectionError",
    "CbusError",
    "CbusProtocol",
    "CbusTimeoutError",
    "CbusTransport",
    "ProtocolState",
    "SerialTransport",
    "TcpTransport",
]
