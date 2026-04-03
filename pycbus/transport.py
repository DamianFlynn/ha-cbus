"""Async transport abstraction for C-Bus PCI (serial) and CNI (TCP).

The transport layer is the lowest layer in the pycbus stack.  It owns the
physical connection (serial port or TCP socket) and exposes a minimal
line-oriented interface that the protocol state machine consumes.

Architecture::

    Protocol (state machine)
        │
        ▼
    Transport (this module)
        │
        ├── TcpTransport   → asyncio.open_connection (CNI on port 10001)
        └── SerialTransport → pyserial-asyncio (PCI at 9600 8N1)

Design principles:
    - Transports are **stateless** with respect to the C-Bus protocol.
      They know nothing about checksums, SAL commands, or init sequences.
    - All I/O is async (``await``-based).
    - Line-oriented: C-Bus frames are delimited by ``\\r`` (0x0D).
    - The ``CbusTransport`` protocol class (structural subtyping) allows
      the protocol layer to accept any transport without inheritance.

The concrete ``TcpTransport`` and ``SerialTransport`` implementations
will be added in a subsequent PR.

Usage (once concrete transports are implemented)::

    transport = TcpTransport(host="192.168.1.50", port=10001)
    await transport.connect()
    await transport.write(b"\\\\05380079 01FF50\\r")
    response = await transport.read_line()
    await transport.disconnect()
"""

from __future__ import annotations

from typing import Protocol


class CbusTransport(Protocol):
    """Structural interface that all C-Bus transports must satisfy.

    This is a :class:`typing.Protocol` (structural subtyping), meaning
    concrete classes do **not** need to inherit from it — they just need
    to implement the same method signatures.

    Methods:
        connect:     Establish the physical connection.
        disconnect:  Tear down the connection gracefully.
        read_line:   Read one CR-terminated line from the interface.
        write:       Send raw bytes to the interface.

    Properties:
        connected:   ``True`` when the transport has an active connection.
    """

    async def connect(self) -> None:
        """Open the connection to the C-Bus interface."""
        ...

    async def disconnect(self) -> None:
        """Close the connection and release resources."""
        ...

    async def read_line(self) -> bytes:
        """Read one line (up to and including the CR delimiter).

        Returns:
            The raw bytes of the next line from the interface.

        Raises:
            ConnectionError: If the transport is not connected.
        """
        ...

    async def write(self, data: bytes) -> None:
        """Write raw bytes to the interface.

        Args:
            data: The bytes to transmit (already framed with ``\\`` and ``\\r``).

        Raises:
            ConnectionError: If the transport is not connected.
        """
        ...

    @property
    def connected(self) -> bool:
        """Whether the transport currently has an active connection."""
        ...
