"""Async transport abstraction for C-Bus PCI (serial) and CNI (TCP).

The transport layer is the lowest layer in the pycbus stack.  It owns the
physical connection (serial port or TCP socket) and exposes a minimal
line-oriented interface that the protocol state machine consumes.

Architecture::

    Protocol (state machine)
        |
        v
    Transport (this module)
        |
        +-- TcpTransport   -> asyncio.open_connection (CNI on port 10001)
        +-- SerialTransport -> serial_asyncio.open_serial_connection (PCI 9600 8N1)

Design principles:
    - Transports are **stateless** with respect to the C-Bus protocol.
      They know nothing about checksums, SAL commands, or init sequences.
    - All I/O is async (``await``-based).
    - Line-oriented: C-Bus frames are delimited by CR (0x0D).
    - The :class:`CbusTransport` protocol class (structural subtyping)
      allows the protocol layer to accept any transport without inheritance.
    - Concrete transports own their reconnection **attempt** but not the
      retry *policy* (that belongs to the protocol layer / coordinator).

Usage::

    transport = TcpTransport(host="192.168.1.50", port=10001)
    await transport.connect()
    await transport.write(b"\\\\05380079 01FF50\\r")
    line = await transport.read_line()
    await transport.disconnect()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from .constants import (
    SERIAL_BAUD,
    SERIAL_BYTESIZE,
    SERIAL_PARITY,
    SERIAL_STOPBITS,
    TCP_PORT,
)
from .exceptions import CbusConnectionError, CbusTimeoutError

_LOGGER = logging.getLogger(__name__)

# CR byte used as the C-Bus line delimiter.
_CR = b"\r"

# Default timeout (seconds) for connect and read operations.
_DEFAULT_TIMEOUT = 10.0


class CbusTransport(Protocol):
    """Structural interface that all C-Bus transports must satisfy.

    This is a :class:`typing.Protocol` (structural subtyping), meaning
    concrete classes do **not** need to inherit from it -- they just need
    to implement the same method signatures.
    """

    async def connect(self) -> None:
        """Open the connection to the C-Bus interface."""
        ...

    async def disconnect(self) -> None:
        """Close the connection and release resources."""
        ...

    async def read_line(self) -> bytes:
        """Read one CR-terminated line from the interface.

        Returns:
            The raw bytes of the next line, **excluding** the CR delimiter.

        Raises:
            CbusConnectionError: If the transport is not connected.
            CbusTimeoutError: If no line arrives within the timeout.
        """
        ...

    async def write(self, data: bytes) -> None:
        """Write raw bytes to the interface.

        Args:
            data: The bytes to transmit (already framed by the caller).

        Raises:
            CbusConnectionError: If the transport is not connected.
        """
        ...

    @property
    def connected(self) -> bool:
        """Whether the transport currently has an active connection."""
        ...


class TcpTransport:
    """Async TCP transport for a C-Bus CNI (network interface).

    The CNI listens on TCP port 10001 by default and speaks the same
    line-oriented protocol as a serial PCI.

    Args:
        host: Hostname or IP address of the CNI.
        port: TCP port (default 10001).
        timeout: Seconds to wait for connect and read operations.
    """

    def __init__(
        self,
        host: str,
        port: int = TCP_PORT,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    @property
    def host(self) -> str:
        """The CNI hostname or IP address."""
        return self._host

    @property
    def port(self) -> int:
        """The CNI TCP port."""
        return self._port

    @property
    def connected(self) -> bool:
        """``True`` when the TCP socket is open."""
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        """Open a TCP connection to the CNI.

        Raises:
            CbusConnectionError: On TCP socket failures.
            CbusTimeoutError: If the connection is not established in time.
        """
        if self.connected:
            _LOGGER.debug("Already connected to %s:%d", self._host, self._port)
            return

        _LOGGER.debug("Connecting to CNI at %s:%d", self._host, self._port)
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=self._timeout,
            )
        except TimeoutError as exc:
            raise CbusTimeoutError(
                f"Timeout connecting to {self._host}:{self._port}"
            ) from exc
        except OSError as exc:
            raise CbusConnectionError(
                f"Cannot connect to {self._host}:{self._port}: {exc}"
            ) from exc
        _LOGGER.info("Connected to CNI at %s:%d", self._host, self._port)

    async def disconnect(self) -> None:
        """Close the TCP connection gracefully."""
        if self._writer is None:
            return
        _LOGGER.debug("Disconnecting from %s:%d", self._host, self._port)
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except OSError:
            pass  # Already closed / broken pipe -- nothing to do.
        finally:
            self._reader = None
            self._writer = None
        _LOGGER.info("Disconnected from CNI at %s:%d", self._host, self._port)

    async def read_line(self) -> bytes:
        """Read one CR-terminated line from the CNI.

        Returns:
            The raw line bytes **excluding** the trailing CR.

        Raises:
            CbusConnectionError: If not connected or the connection drops.
            CbusTimeoutError: If no complete line arrives within the timeout.
        """
        if self._reader is None:
            raise CbusConnectionError("Not connected")
        try:
            raw = await asyncio.wait_for(
                self._reader.readuntil(_CR),
                timeout=self._timeout,
            )
        except TimeoutError as exc:
            raise CbusTimeoutError("Timeout waiting for data from CNI") from exc
        except (
            asyncio.IncompleteReadError,
            ConnectionResetError,
            BrokenPipeError,
        ) as exc:
            await self.disconnect()
            raise CbusConnectionError(
                f"Connection lost to {self._host}:{self._port}"
            ) from exc
        # Strip the CR delimiter; also strip any trailing LF or whitespace.
        return raw.rstrip(b"\r\n")

    async def write(self, data: bytes) -> None:
        """Write raw bytes to the CNI.

        Args:
            data: Pre-framed command bytes (the caller adds ``\\`` and CR).

        Raises:
            CbusConnectionError: If not connected or the write fails.
        """
        if self._writer is None:
            raise CbusConnectionError("Not connected")
        _LOGGER.debug("TX → %s", data.hex())
        try:
            self._writer.write(data)
            await self._writer.drain()
        except (ConnectionResetError, BrokenPipeError, OSError) as exc:
            await self.disconnect()
            raise CbusConnectionError(
                f"Write failed to {self._host}:{self._port}"
            ) from exc


class SerialTransport:
    """Async serial transport for a C-Bus PCI (USB/RS-232 interface).

    Uses ``serial_asyncio`` (``pyserial-asyncio`` package) for non-blocking
    serial I/O over asyncio.

    Args:
        url: Serial device path (e.g. ``/dev/ttyUSB0`` or ``COM3``).
        baud: Baud rate (default 9600).
        timeout: Seconds to wait for connect and read operations.
    """

    def __init__(
        self,
        url: str,
        baud: int = SERIAL_BAUD,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._url = url
        self._baud = baud
        self._timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    @property
    def url(self) -> str:
        """The serial device path."""
        return self._url

    @property
    def baud(self) -> int:
        """The configured baud rate."""
        return self._baud

    @property
    def connected(self) -> bool:
        """``True`` when the serial port is open."""
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        """Open the serial connection to the PCI.

        Raises:
            CbusConnectionError: If the serial port cannot be opened.
            CbusTimeoutError: If the connection is not established in time.
        """
        if self.connected:
            _LOGGER.debug("Already connected to %s", self._url)
            return

        _LOGGER.debug("Opening serial port %s at %d baud", self._url, self._baud)
        try:
            import serial_asyncio  # type: ignore[import-untyped]

            self._reader, self._writer = await asyncio.wait_for(
                serial_asyncio.open_serial_connection(
                    url=self._url,
                    baudrate=self._baud,
                    bytesize=SERIAL_BYTESIZE,
                    parity=SERIAL_PARITY,
                    stopbits=SERIAL_STOPBITS,
                ),
                timeout=self._timeout,
            )
        except TimeoutError as exc:
            raise CbusTimeoutError(f"Timeout opening serial port {self._url}") from exc
        except (OSError, ImportError) as exc:
            raise CbusConnectionError(
                f"Cannot open serial port {self._url}: {exc}"
            ) from exc
        _LOGGER.info("Connected to PCI at %s (%d baud)", self._url, self._baud)

    async def disconnect(self) -> None:
        """Close the serial connection gracefully."""
        if self._writer is None:
            return
        _LOGGER.debug("Closing serial port %s", self._url)
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except OSError:
            pass  # Port already closed.
        finally:
            self._reader = None
            self._writer = None
        _LOGGER.info("Disconnected from PCI at %s", self._url)

    async def read_line(self) -> bytes:
        """Read one CR-terminated line from the PCI.

        Returns:
            The raw line bytes **excluding** the trailing CR.

        Raises:
            CbusConnectionError: If not connected or the port drops.
            CbusTimeoutError: If no complete line arrives within the timeout.
        """
        if self._reader is None:
            raise CbusConnectionError("Not connected")
        try:
            raw = await asyncio.wait_for(
                self._reader.readuntil(_CR),
                timeout=self._timeout,
            )
        except TimeoutError as exc:
            raise CbusTimeoutError("Timeout waiting for data from PCI") from exc
        except (
            asyncio.IncompleteReadError,
            ConnectionResetError,
        ) as exc:
            await self.disconnect()
            raise CbusConnectionError(f"Connection lost to {self._url}") from exc
        return raw.rstrip(b"\r\n")

    async def write(self, data: bytes) -> None:
        """Write raw bytes to the PCI serial port.

        Args:
            data: Pre-framed command bytes.

        Raises:
            CbusConnectionError: If not connected or the write fails.
        """
        if self._writer is None:
            raise CbusConnectionError("Not connected")
        _LOGGER.debug("TX → %s", data.hex())
        try:
            self._writer.write(data)
            await self._writer.drain()
        except OSError as exc:
            await self.disconnect()
            raise CbusConnectionError(f"Write failed to {self._url}") from exc
