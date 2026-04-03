"""C-Bus PCI/CNI protocol state machine.

This module implements the full PCI initialisation sequence and runtime
message loop.  The state machine manages the connection lifecycle from
power-on reset through to steady-state SAL monitoring.

State diagram::

    DISCONNECTED
        |
        v  transport.connect()
    CONNECTING
        |
        v  drain any startup junk, send reset
    RESETTING
        |  send: ~~~\\r  (three tildes = PCI hard reset)
        v  wait for ready prompt
    INITIALISING
        |  1. Set Interface Options #3 (LOCAL_SAL + EXSTAT)
        |  2. Set Interface Options #1 (CONNECT + SRCHK + SMART + MONITOR + IDMON)
        v  all confirmed with g. responses
    READY
        |  - send SAL commands (lighting, trigger, enable ...)
        |  - receive monitor events (level changes, triggers)
        v  transport error or intentional disconnect
    DISCONNECTED

Error handling:
    If any init command receives a NEGATIVE (``!``) response, the state
    machine retries the init sequence up to ``max_retries`` times before
    raising :class:`CbusConnectionError`.

Threading model:
    The state machine runs entirely within a single asyncio task.
    Callers interact via :meth:`send_command` for outbound SAL frames and
    register callbacks via :meth:`on_event` for inbound monitor events.

Usage::

    from pycbus.protocol import CbusProtocol
    from pycbus.transport import TcpTransport

    transport = TcpTransport(host="192.168.1.50")
    protocol = CbusProtocol(transport)
    await protocol.connect()
    # protocol.state == ProtocolState.READY
    await protocol.send_command(b"0538007901FF50")
    await protocol.disconnect()
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from enum import Enum, auto
from typing import TYPE_CHECKING

from .checksum import checksum, verify
from .constants import (
    ConfirmationCode,
    InterfaceOption1,
    InterfaceOption3,
)
from .exceptions import CbusConnectionError, CbusTimeoutError

if TYPE_CHECKING:
    from .transport import CbusTransport

_LOGGER = logging.getLogger(__name__)

# Maximum init retries before giving up.
_MAX_RETRIES = 3

# Seconds to wait for a confirmation after sending a command.
_CONFIRMATION_TIMEOUT = 5.0

# PCI reset command: three tildes.
_RESET_CMD = b"~~~\r"

# Confirmation characters we look for in PCI responses.
_POSITIVE = bytes([ConfirmationCode.POSITIVE])
_NEGATIVE = bytes([ConfirmationCode.NEGATIVE])
_READY = bytes([ConfirmationCode.READY])


def _build_cal_command(parameter: int, offset: int, value: int) -> bytes:
    """Build a CAL (Configuration Adaptation Layer) write command.

    CAL commands set PCI interface parameters.  The wire format is::

        @A3 <param_hi> <param_lo> 00 <value> <checksum>

    where the ``@`` prefix tells the PCI this is a CAL frame (not SAL).
    The full frame on the wire is ``\\@A3...\\r``.

    Args:
        parameter: The PCI parameter number (e.g. 0x30 for options #1).
        offset: Sub-offset within the parameter (usually 0x00).
        value: The byte value to write.

    Returns:
        Hex-encoded payload bytes (without ``\\`` prefix or ``\\r`` suffix)
        ready to be framed by :meth:`CbusProtocol._send_frame`.
    """
    raw = bytes([0xA3, parameter, offset, value])
    cs = checksum(raw)
    return b"@" + (raw + bytes([cs])).hex().upper().encode()


class ProtocolState(Enum):
    """Protocol state machine states."""

    DISCONNECTED = auto()
    CONNECTING = auto()
    RESETTING = auto()
    INITIALISING = auto()
    READY = auto()


# Type alias for SAL event callbacks.
# Callbacks receive the raw hex-decoded bytes of the SAL event.
SalEventCallback = Callable[[bytes], None]


class CbusProtocol:
    """C-Bus PCI/CNI protocol handler.

    Sits on top of a :class:`CbusTransport` and implements:
    - PCI reset and initialisation sequence
    - SAL command framing and confirmation
    - Monitor event parsing and callback dispatch
    - Connection lifecycle with state tracking

    Args:
        transport: Any object satisfying :class:`CbusTransport` protocol.
        max_retries: Maximum number of init sequence retries.
    """

    def __init__(
        self,
        transport: CbusTransport,
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        self._transport = transport
        self._max_retries = max_retries
        self._state = ProtocolState.DISCONNECTED
        self._event_callbacks: list[SalEventCallback] = []
        self._read_task: asyncio.Task[None] | None = None
        self._command_lock = asyncio.Lock()
        self._confirmation_event = asyncio.Event()
        self._last_confirmation: bytes = b""

    @property
    def state(self) -> ProtocolState:
        """Current protocol state."""
        return self._state

    @property
    def connected(self) -> bool:
        """``True`` when the protocol is in READY state."""
        return self._state == ProtocolState.READY

    def on_event(self, callback: SalEventCallback) -> Callable[[], None]:
        """Register a callback for incoming SAL monitor events.

        Args:
            callback: Called with raw SAL bytes for each monitor event.

        Returns:
            An unsubscribe function that removes the callback.
        """
        self._event_callbacks.append(callback)

        def _unsubscribe() -> None:
            self._event_callbacks.remove(callback)

        return _unsubscribe

    async def connect(self) -> None:
        """Connect to the PCI/CNI, reset, and run the init sequence.

        On success, ``self.state`` transitions to ``READY`` and the
        background read loop is started.

        Raises:
            CbusConnectionError: If the transport cannot connect or
                the init sequence fails after exhausting retries.
            CbusTimeoutError: If any step times out.
        """
        if self._state == ProtocolState.READY:
            _LOGGER.debug("Already connected and ready")
            return

        self._state = ProtocolState.CONNECTING
        _LOGGER.info("Connecting to C-Bus interface...")
        await self._transport.connect()

        for attempt in range(1, self._max_retries + 1):
            try:
                await self._reset()
                await self._initialise()
                self._state = ProtocolState.READY
                self._start_read_loop()
                _LOGGER.info("Protocol READY (attempt %d)", attempt)
                return
            except (CbusConnectionError, CbusTimeoutError) as exc:
                _LOGGER.warning(
                    "Init attempt %d/%d failed: %s",
                    attempt,
                    self._max_retries,
                    exc,
                )
                if attempt == self._max_retries:
                    self._state = ProtocolState.DISCONNECTED
                    await self._transport.disconnect()
                    raise CbusConnectionError(
                        f"Init failed after {self._max_retries} attempts"
                    ) from exc

    async def disconnect(self) -> None:
        """Gracefully disconnect from the PCI/CNI.

        Stops the background read loop and closes the transport.
        """
        _LOGGER.info("Disconnecting from C-Bus interface")
        self._stop_read_loop()
        self._state = ProtocolState.DISCONNECTED
        await self._transport.disconnect()

    async def send_command(self, payload_hex: bytes) -> bool:
        """Send an SAL command and wait for PCI confirmation.

        The payload should be the hex-encoded command bytes (e.g.
        ``b"0538007901FF50"``).  This method wraps it with the ``\\``
        prefix and ``\\r`` suffix, sends it, and waits for the PCI's
        confirmation character.

        Args:
            payload_hex: Hex-encoded SAL payload including checksum.

        Returns:
            ``True`` if the PCI responded with POSITIVE (``g``),
            ``False`` if NEGATIVE (``!``).

        Raises:
            CbusConnectionError: If not in READY state.
            CbusTimeoutError: If no confirmation arrives in time.
        """
        if self._state != ProtocolState.READY:
            raise CbusConnectionError(f"Cannot send: protocol is {self._state.name}")

        async with self._command_lock:
            self._confirmation_event.clear()
            await self._send_frame(payload_hex)

            try:
                await asyncio.wait_for(
                    self._confirmation_event.wait(),
                    timeout=_CONFIRMATION_TIMEOUT,
                )
            except TimeoutError as exc:
                raise CbusTimeoutError("Timeout waiting for PCI confirmation") from exc

            confirmed = _POSITIVE in self._last_confirmation
            if not confirmed:
                _LOGGER.warning("Command rejected: %s", self._last_confirmation)
            return confirmed

    # ------------------------------------------------------------------
    # Internal: init sequence
    # ------------------------------------------------------------------

    async def _reset(self) -> None:
        """Send reset (~~~) and drain until we see a ready prompt."""
        self._state = ProtocolState.RESETTING
        _LOGGER.debug("Sending PCI reset")
        await self._transport.write(_RESET_CMD)

        # Drain lines until we see one that ends with or contains
        # a ready prompt (#) or the PCI's power-on '=' sign.
        for _ in range(20):  # safety limit
            line = await self._transport.read_line()
            _LOGGER.debug("RESET RX: %r", line)
            if _READY in line or b"=" in line:
                _LOGGER.debug("PCI reset acknowledged")
                return

        raise CbusTimeoutError("PCI did not acknowledge reset")

    async def _initialise(self) -> None:
        """Run the PCI init sequence: set interface options."""
        self._state = ProtocolState.INITIALISING
        _LOGGER.debug("Running PCI init sequence")

        # Step 1: Interface Options #3 — LOCAL_SAL + EXSTAT = 0x0A
        opt3 = InterfaceOption3.LOCAL_SAL | InterfaceOption3.EXSTAT
        await self._send_cal_and_confirm(0x42, 0x00, opt3)

        # Step 2: Interface Options #1 — CONNECT+SRCHK+SMART+MONITOR+IDMON = 0x79
        opt1 = (
            InterfaceOption1.CONNECT
            | InterfaceOption1.SRCHK
            | InterfaceOption1.SMART
            | InterfaceOption1.MONITOR
            | InterfaceOption1.IDMON
        )
        await self._send_cal_and_confirm(0x30, 0x00, opt1)

        _LOGGER.debug("PCI init sequence complete")

    async def _send_cal_and_confirm(
        self, parameter: int, offset: int, value: int
    ) -> None:
        """Send a CAL command and wait for positive confirmation.

        Raises:
            CbusConnectionError: On negative response.
            CbusTimeoutError: On timeout.
        """
        cmd = _build_cal_command(parameter, offset, value)
        _LOGGER.debug("INIT TX: %s", cmd.decode())

        await self._send_frame(cmd)

        # Read lines looking for confirmation.
        for _ in range(10):  # safety limit
            line = await self._transport.read_line()
            _LOGGER.debug("INIT RX: %r", line)

            if _POSITIVE in line:
                _LOGGER.debug("CAL command confirmed")
                return
            if _NEGATIVE in line:
                raise CbusConnectionError(f"CAL command rejected: {cmd!r}")

        raise CbusTimeoutError("No confirmation for CAL command")

    # ------------------------------------------------------------------
    # Internal: framing
    # ------------------------------------------------------------------

    async def _send_frame(self, payload: bytes) -> None:
        """Frame and send a command to the PCI.

        Adds ``\\`` prefix and ``\\r`` suffix to the payload.
        """
        frame = b"\\" + payload + b"\r"
        _LOGGER.debug("TX frame: %r", frame)
        await self._transport.write(frame)

    # ------------------------------------------------------------------
    # Internal: background read loop
    # ------------------------------------------------------------------

    def _start_read_loop(self) -> None:
        """Start the background task that reads monitor events."""
        if self._read_task is not None:
            return
        self._read_task = asyncio.create_task(self._read_loop(), name="cbus-read-loop")

    def _stop_read_loop(self) -> None:
        """Cancel the background read task."""
        if self._read_task is not None:
            self._read_task.cancel()
            self._read_task = None

    async def _read_loop(self) -> None:
        """Continuously read lines from the transport and dispatch.

        Lines are classified as:
        - Confirmation codes (g, !, #, .) -> signal the waiting sender
        - Hex-encoded SAL events -> decode and dispatch to callbacks

        Runs until cancelled or the transport drops.
        """
        try:
            while self._state == ProtocolState.READY:
                try:
                    line = await self._transport.read_line()
                except (CbusConnectionError, CbusTimeoutError):
                    _LOGGER.warning("Transport error in read loop")
                    break

                if not line:
                    continue

                self._handle_line(line)
        except asyncio.CancelledError:
            _LOGGER.debug("Read loop cancelled")
        finally:
            if self._state == ProtocolState.READY:
                self._state = ProtocolState.DISCONNECTED
                _LOGGER.warning("Read loop exited unexpectedly, state -> DISCONNECTED")

    def _handle_line(self, line: bytes) -> None:
        """Classify and handle a single line from the PCI.

        Args:
            line: Raw bytes from transport (CR already stripped).
        """
        # Check for confirmation codes anywhere in the line.
        if _POSITIVE in line or _NEGATIVE in line:
            self._last_confirmation = line
            self._confirmation_event.set()
            # Don't return — a confirmation line may also contain data.
            if len(line) <= 2:
                return

        if _READY in line and len(line) <= 2:
            # Bare '#' or 'g#' — just a status prompt.
            return

        # Everything else is a potential SAL monitor event.
        # SAL events arrive as hex-encoded bytes from the PCI.
        self._dispatch_event(line)

    def _dispatch_event(self, line: bytes) -> None:
        """Attempt to decode a hex line as an SAL event and dispatch.

        Args:
            line: Raw ASCII hex bytes from the PCI.
        """
        try:
            # Lines from PCI in SMART+SRCHK mode are hex-encoded.
            decoded = bytes.fromhex(line.decode("ascii"))
        except (ValueError, UnicodeDecodeError):
            _LOGGER.debug("Non-hex line ignored: %r", line)
            return

        # With SRCHK enabled, the last byte is a checksum.
        if len(decoded) > 1 and not verify(decoded):
            _LOGGER.debug("Checksum mismatch, ignoring: %s", line.hex())
            return

        _LOGGER.debug("SAL event: %s", decoded.hex())
        for callback in self._event_callbacks:
            try:
                callback(decoded)
            except Exception:
                _LOGGER.exception("Error in SAL event callback")
