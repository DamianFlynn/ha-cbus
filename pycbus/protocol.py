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
        |  1. Set Application Address 1 = 0xFF (all apps)
        |  2. Set Application Address 2 = 0xFF (all apps)
        |  3. Set Interface Options #3 (LOCAL_SAL + PUN + EXSTAT)
        |  4. Set Interface Options #1 (CONNECT + SRCHK + SMART + MONITOR)
        v  all confirmed with matching confirmation codes
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
import contextlib
import logging
import time
from collections.abc import Callable
from enum import Enum, auto
from typing import TYPE_CHECKING

from .checksum import verify
from .commands import (
    is_status_reply,
    parse_status_reply,
    status_request,
)
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

# Single tilde + CR used by the reset sequence (sent three times).
_RESET_TILDE = b"~\r"

# Confirmation characters we look for in PCI responses.
_POSITIVE = bytes([ConfirmationCode.POSITIVE])
_NEGATIVE = bytes([ConfirmationCode.NEGATIVE])
_READY = bytes([ConfirmationCode.READY])

# Confirmation codes cycled through when sending commands.
# Matches the C-Bus protocol spec and micolous/cbus implementation.
_CONFIRMATION_CODES = b"hijklmnopqrstuvwxyzg"


def _build_cal_command(parameter: int, offset: int, value: int) -> bytes:
    """Build a CAL (Configuration Adaptation Layer) write command.

    CAL commands are Device Management packets.  The first byte (0xA3)
    is the **flags** byte encoding DAT=POINT_TO_POINT_TO_MULTIPOINT (0x03),
    dp=True (0x20), priority=CLASS_2 (0x80).  The wire format in basic
    mode (before SMART is enabled) is::

        A3 <param> <offset> <value> <confirmation_code> \r

    No ``\\`` prefix and no checksum.  The confirmation code is appended
    by the caller.

    Reference: *C-Bus Serial Interface User Guide*, §10.2.

    Args:
        parameter: The PCI parameter number (e.g. 0x30 for options #1).
        offset: Sub-offset within the parameter (usually 0x00).
        value: The byte value to write.

    Returns:
        Hex-encoded Device Management payload (no checksum, no
        confirmation code) ready for :meth:`_send_cal_and_confirm`.
    """
    raw = bytes([0xA3, parameter, offset, value])
    return raw.hex().upper().encode()


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

# Type alias for status reply callbacks.
# Callbacks receive a dict mapping (app_id, group) to level (0-255).
StatusCallback = Callable[[dict[tuple[int, int], int]], None]


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
        self._status_callbacks: list[StatusCallback] = []
        self._read_task: asyncio.Task[None] | None = None
        self._command_lock = asyncio.Lock()
        # Pending status request: accumulates reply data.
        self._status_pending_app: int | None = None
        self._status_levels: dict[tuple[int, int], int] = {}
        # Confirmation code index — cycles through _CONFIRMATION_CODES.
        self._next_confirmation_index: int = 0

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

    def on_status(self, callback: StatusCallback) -> Callable[[], None]:
        """Register a callback for status reply data.

        When :meth:`request_status` completes, all registered status
        callbacks receive a dict of ``{(app_id, group): level}``.

        Args:
            callback: Called with the full status dict.

        Returns:
            An unsubscribe function that removes the callback.
        """
        self._status_callbacks.append(callback)

        def _unsubscribe() -> None:
            self._status_callbacks.remove(callback)

        return _unsubscribe

    async def request_status(
        self,
        app_id: int,
        timeout: float = 10.0,
    ) -> dict[tuple[int, int], int]:
        """Request the binary status of all groups for an application.

        Sends a single binary status request (``$7A``) to the
        STATUS_REQUEST pseudo-application (``0xFF``).  The PCI responds
        with multiple CAL reply lines covering all 256 groups.

        In SMART mode the command needs a confirmation code.  The reply
        lines arrive as standard or extended CAL data depending on the
        EXSTAT option.

        Args:
            app_id: Application ID to query
                    (e.g. ``ApplicationId.LIGHTING``).
            timeout: Maximum seconds to wait for all reply lines.

        Returns:
            Dict mapping ``(app_id, group_address)`` to state
            (255 = ON, 0 = OFF).

        Raises:
            CbusConnectionError: If not in READY state.
        """
        if self._state != ProtocolState.READY:
            raise CbusConnectionError(
                f"Cannot request status: protocol is {self._state.name}"
            )

        async with self._command_lock:
            self._status_pending_app = app_id
            self._status_levels = {}

            await self._stop_read_loop()

            try:
                # Send one binary status request with confirmation code.
                cmd = status_request(app_id)
                hex_payload = cmd.hex().upper().encode()
                conf = self._get_confirmation_code()
                await self._send_frame(hex_payload + conf)
                _LOGGER.debug(
                    "Sent binary status request: app=0x%02X conf=%s",
                    app_id,
                    conf.decode(),
                )

                # Read reply lines until the transport times out
                # (indicating no more data).  The PCI sends 3+ lines
                # of CAL data for one binary status request.
                deadline = time.monotonic() + timeout
                for _ in range(20):  # safety limit
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        _LOGGER.info("Status deadline reached")
                        break
                    try:
                        line = await self._transport.read_line()
                    except CbusTimeoutError:
                        _LOGGER.debug(
                            "Status read timeout — end of replies "
                            "(app 0x%02X, %d groups received)",
                            app_id,
                            len(self._status_levels),
                        )
                        break
                    _LOGGER.debug("STATUS RX: %r", line)

                    # Strip a leading confirmation code if present.
                    # The PCI prepends conf+result to the first reply.
                    text = line
                    if conf in text:
                        idx = text.find(conf)
                        # Skip conf + result char (e.g. "l.")
                        text = text[idx + 2 :]
                        if not text:
                            continue  # confirmation-only line

                    self._process_status_line(text, app_id)

            finally:
                result = dict(self._status_levels)
                self._status_pending_app = None
                self._start_read_loop()

        for callback in tuple(self._status_callbacks):
            try:
                callback(result)
            except Exception:
                _LOGGER.exception("Error in status callback")

        return result

    def _process_status_line(self, line: bytes, app_id: int) -> None:
        """Try to parse a line as a status reply and accumulate results."""
        try:
            decoded = bytes.fromhex(line.decode("ascii"))
        except (ValueError, UnicodeDecodeError):
            _LOGGER.debug("Status: non-hex line ignored: %r", line)
            return

        # Verify checksum of the entire decoded blob.
        if len(decoded) > 1 and not verify(decoded):
            _LOGGER.debug("Status: checksum mismatch: %s", decoded.hex())
            return

        if not is_status_reply(decoded):
            _LOGGER.debug("Status: non-status line ignored: %s", decoded.hex())
            return

        reply_app, levels = parse_status_reply(decoded)
        if reply_app != app_id:
            _LOGGER.debug(
                "Status: reply for app 0x%02X (expected 0x%02X), ignoring",
                reply_app,
                app_id,
            )
            return

        _LOGGER.debug(
            "Status reply: app=0x%02X, %d groups in this line",
            reply_app,
            len(levels),
        )
        for group, level in levels.items():
            if group < 256:
                self._status_levels[(app_id, group)] = level

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
        try:
            await self._transport.connect()
        except Exception:
            self._state = ProtocolState.DISCONNECTED
            _LOGGER.exception("Failed to connect to C-Bus interface")
            raise

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
        self._state = ProtocolState.DISCONNECTED
        await self._stop_read_loop()
        await self._transport.disconnect()

    async def send_command(self, payload_hex: bytes) -> bool:
        """Send an SAL command and wait for PCI confirmation.

        The payload should be the hex-encoded command bytes (e.g.
        ``b"0538007901FF50"``).  This method appends a cycling
        confirmation code, wraps with ``\\`` prefix and ``\\r``
        suffix, sends it, and reads the PCI's response directly.

        The read loop is temporarily paused so we can read the
        confirmation inline — the same approach used during init.
        Any SAL monitor events received while reading are dispatched
        to callbacks before returning.

        In SMART mode the PCI responds with
        ``<conf_code><result>`` where result is ``.`` for success
        or ``!`` for error.  For example, sending with code ``l``
        yields ``l.`` on success or ``l!`` on failure.

        Args:
            payload_hex: Hex-encoded SAL payload including checksum.

        Returns:
            ``True`` if the PCI confirmed success or if the command was
            sent but no confirmation arrived (fire-and-forget).
            ``False`` if the PCI explicitly rejected the command (``!``).

        Raises:
            CbusConnectionError: If not in READY state.
        """
        if self._state != ProtocolState.READY:
            raise CbusConnectionError(f"Cannot send: protocol is {self._state.name}")

        async with self._command_lock:
            conf = self._get_confirmation_code()

            # Pause the read loop so we can read the confirmation directly.
            await self._stop_read_loop()

            try:
                await self._send_frame(payload_hex + conf)
                _LOGGER.debug("Sent command with confirmation code=%s", conf.decode())

                # Read lines looking for our confirmation code, same
                # pattern as _send_cal_and_confirm during init.
                #
                # The PCI prepends the confirmation code to the next line
                # it outputs.  If the bus is quiet, the PCI may buffer the
                # confirmation indefinitely until a bus event flushes it.
                # In that case, the transport read_line() times out and we
                # treat the command as sent (fire-and-forget).
                for _ in range(10):  # safety limit
                    try:
                        line = await self._transport.read_line()
                    except CbusTimeoutError:
                        _LOGGER.info(
                            "No confirmation received (code=%s) — "
                            "command was sent but PCI did not respond "
                            "within timeout (normal for quiet bus).",
                            conf.decode(),
                        )
                        return True
                    _LOGGER.debug("CMD RX: %r", line)

                    # Check for our confirmation code in the response.
                    if conf in line:
                        idx = line.find(conf)
                        after = line[idx + 1 : idx + 2]
                        if after == _NEGATIVE:
                            _LOGGER.warning(
                                "Command rejected (code=%s): %r",
                                conf.decode(),
                                line,
                            )
                            return False
                        _LOGGER.debug("Command confirmed (code=%s)", conf.decode())
                        return True

                    # Legacy: bare 'g' or '!' without our conf code.
                    if _NEGATIVE in line:
                        _LOGGER.warning("Command rejected (legacy): %r", line)
                        return False
                    if _POSITIVE in line:
                        _LOGGER.debug("Command confirmed (legacy g)")
                        return True

                    # Not a confirmation — dispatch as SAL event.
                    self._dispatch_event(line)

                _LOGGER.info(
                    "No confirmation after 10 response lines (code=%s) — "
                    "assuming sent.",
                    conf.decode(),
                )
                return True
            finally:
                # Always restart the read loop.
                self._start_read_loop()

    # ------------------------------------------------------------------
    # Internal: init sequence
    # ------------------------------------------------------------------

    async def _reset(self) -> None:
        """Send PCI reset and drain lines until the bus is quiet.

        Sends ``~\r`` three times (three separate reset packets), matching
        the reference implementation (micolous/cbus).  The Serial Interface
        Guide requires "three or more tildes" to reset the PCI.

        After the resets, drain any output.  The PCI *may* send a ready
        prompt (``#``) or a power-on ``=`` sign, but not all firmware
        versions do.  We drain until a read timeout, which indicates
        the PCI has finished its reset output.
        """
        self._state = ProtocolState.RESETTING
        _LOGGER.debug("Sending PCI reset (3 x tilde)")
        for _ in range(3):
            await self._transport.write(_RESET_TILDE)

        # Drain lines — look for a ready prompt but don't require it.
        for _ in range(20):  # safety limit
            try:
                line = await self._transport.read_line()
            except CbusTimeoutError:
                # No more data — PCI has finished its reset output.
                _LOGGER.debug("Reset drain complete (timeout)")
                return
            _LOGGER.debug("RESET RX: %r", line)
            if _READY in line or b"=" in line:
                _LOGGER.debug("PCI reset acknowledged")
                return

        _LOGGER.debug("Reset drain complete (line limit)")

    async def _initialise(self) -> None:
        """Run the PCI init sequence: set application address and options.

        All three CAL commands are sent in **basic mode** (no ``\\``
        prefix, no checksum) because SMART/SRCHK are not yet enabled.
        The PCI echoes each command in basic mode; we look for the
        ``g`` confirmation that follows the echo.

        Steps (from *C-Bus Serial Interface User Guide* §10.2)::

            1. Set Application Address 1 = 0xFF (all applications)
            2. Set Application Address 2 = 0xFF (all applications)
            3. Interface Options #3: LOCAL_SAL + PUN + EXSTAT  (0x0E)
            4. Interface Options #1: CONNECT+SRCHK+SMART+MONITOR+IDMON (0x79)

        Setting both application addresses to 0xFF matches the production
        PCI configuration (HOME.xml: ``Application = "0xff 0xff"``),
        ensuring we receive SAL traffic for **all** applications — lighting,
        triggers, enable, and any future apps.
        """
        self._state = ProtocolState.INITIALISING
        _LOGGER.debug("Running PCI init sequence")

        # Step 1: Application Address 1 = 0xFF (all applications).
        # Tells the PCI to report traffic for every application, not just
        # a single one.  Matches HOME.xml production config.
        await self._send_cal_and_confirm(0x21, 0x00, 0xFF)

        # Step 2: Application Address 2 = 0xFF (all applications).
        # The PCI has two application address slots.  Both set to 0xFF
        # ensures no filtering of any application traffic.
        await self._send_cal_and_confirm(0x22, 0x00, 0xFF)

        # Step 3: Interface Options #3 — LOCAL_SAL + PUN + EXSTAT = 0x0E
        opt3 = (
            InterfaceOption3.LOCAL_SAL | InterfaceOption3.PUN | InterfaceOption3.EXSTAT
        )
        await self._send_cal_and_confirm(0x42, 0x00, opt3)

        # Step 4: Interface Options #1 — CONNECT+SRCHK+SMART+MONITOR+IDMON = 0x79
        # Note: this is the LAST init command because it enables SMART mode,
        # which changes the framing rules for all subsequent commands.
        # IDMON ensures all CAL replies use long-form (consistent with SMART).
        # MONITOR relays Status Reports for applications matching $21/$22.
        opt1 = (
            InterfaceOption1.CONNECT
            | InterfaceOption1.SRCHK
            | InterfaceOption1.SMART
            | InterfaceOption1.MONITOR
            | InterfaceOption1.IDMON
        )
        await self._send_cal_and_confirm(0x30, 0x00, opt1)

        _LOGGER.debug("PCI init sequence complete")

    def _get_confirmation_code(self) -> bytes:
        """Return the next confirmation code and advance the index.

        The PCI uses the confirmation code to match responses to requests.
        We cycle through ``hijklmnopqrstuvwxyzg`` (20 codes).
        """
        code = bytes([_CONFIRMATION_CODES[self._next_confirmation_index]])
        self._next_confirmation_index = (self._next_confirmation_index + 1) % len(
            _CONFIRMATION_CODES
        )
        return code

    async def _send_cal_and_confirm(
        self, parameter: int, offset: int, value: int
    ) -> None:
        """Send a CAL command in basic mode and wait for confirmation.

        Basic mode means no ``\\`` prefix and no checksum — the PCI is
        still in default mode when these are sent (SMART/SRCHK not yet
        active).  A confirmation code is appended so the PCI can match
        the response.

        The PCI responds with the **same confirmation code** we sent,
        followed by ``.`` (success/ready) or ``!`` (error).  For example,
        if we send ``A3210038h\\r``, the PCI replies ``h.`` on success.

        Raises:
            CbusConnectionError: On negative response.
            CbusTimeoutError: On timeout.
        """
        cmd = _build_cal_command(parameter, offset, value)
        conf = self._get_confirmation_code()
        payload = cmd + conf  # e.g. b"A3210038" + b"h"
        _LOGGER.debug("INIT TX (basic): %s", payload.decode())

        await self._send_basic_frame(payload)

        # Read lines looking for our confirmation code.
        # The PCI echoes the command, then responds with <conf><result>.
        # result is '.' or '#' for success, '!' for error.
        for _ in range(10):  # safety limit
            try:
                line = await self._transport.read_line()
            except CbusTimeoutError:
                break
            _LOGGER.debug("INIT RX: %r", line)

            # Look for our confirmation code in the response.
            if conf in line:
                # Check if the character following conf is success or error.
                idx = line.find(conf)
                after = line[idx + 1 : idx + 2]
                if after == _NEGATIVE:
                    raise CbusConnectionError(f"CAL command rejected: {payload!r}")
                # Any other character after conf (., #, or nothing) = success.
                _LOGGER.debug("CAL command confirmed (code=%s)", conf.decode())
                return

            # Also accept bare 'g' (older PCI firmware without conf codes).
            if _POSITIVE in line:
                _LOGGER.debug("CAL command confirmed (legacy g)")
                return

            if _NEGATIVE in line:
                raise CbusConnectionError(f"CAL command rejected: {payload!r}")

        raise CbusTimeoutError("No confirmation for CAL command")

    # ------------------------------------------------------------------
    # Internal: framing
    # ------------------------------------------------------------------

    async def _send_basic_frame(self, payload: bytes) -> None:
        """Send a command in basic (non-SMART) mode.

        No ``\\`` prefix, no checksum — just the payload followed by CR.
        Used during init before SMART mode is enabled.
        """
        frame = payload + b"\r"
        _LOGGER.debug("TX basic: %r", frame)
        await self._transport.write(frame)

    async def _send_frame(self, payload: bytes) -> None:
        """Frame and send a command to the PCI in SMART mode.

        Adds ``\\`` prefix and ``\\r`` suffix to the payload.
        Used after init when SMART + SRCHK are active.
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

    async def _stop_read_loop(self) -> None:
        """Cancel the background read task and await its completion."""
        if self._read_task is not None:
            self._read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._read_task
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
                except CbusTimeoutError:
                    _LOGGER.debug("Read timeout in read loop; continuing")
                    await asyncio.sleep(0)
                    continue
                except CbusConnectionError:
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

        During monitoring the read loop receives SAL events and
        unsolicited status updates.  Short prompt lines (``#``,
        ``g#``) are ignored.

        Args:
            line: Raw bytes from transport (CR already stripped).
        """
        if _READY in line and len(line) <= 2:
            # Bare '#' or 'g#' — just a status prompt.
            return

        # Everything else is a potential SAL monitor event.
        # SAL events arrive as hex-encoded bytes from the PCI.
        self._dispatch_event(line)

    def _dispatch_event(self, line: bytes) -> None:
        """Attempt to decode a hex line as an SAL event and dispatch.

        Lines are classified as either:
        - **Status replies** (header byte & 0xF8 == 0xD8) → routed to
          :meth:`_handle_status_reply`.
        - **SAL monitor events** (everything else) → dispatched to
          registered event callbacks.

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
            _LOGGER.debug("Checksum mismatch, ignoring: %s", decoded.hex())
            return

        # Status replies have a CAL reply header: top 2 bits = 11.
        # Standard: 0xC0-0xDF (top 3 bits = 110)
        # Extended: 0xE0-0xFF (top 3 bits = 111)
        if is_status_reply(decoded):
            self._handle_status_reply(decoded)
            return

        _LOGGER.debug("SAL event: %s", decoded.hex())
        for callback in tuple(self._event_callbacks):
            try:
                callback(decoded)
            except Exception:
                _LOGGER.exception("Error in SAL event callback")

    def _handle_status_reply(self, decoded: bytes) -> None:
        """Handle a binary status reply from the PCI.

        Parses the reply using :func:`parse_status_reply` and either
        accumulates it into the pending status request or dispatches
        it immediately (for unsolicited status updates from MONITOR mode).

        Args:
            decoded: Raw decoded bytes of the status reply
                     (checksum already verified).
        """
        app_id, levels = parse_status_reply(decoded)

        if not levels:
            _LOGGER.debug("Empty or unparseable status reply: %s", decoded.hex())
            return

        _LOGGER.debug(
            "Status reply: app=0x%02X, %d groups, first_levels=%s",
            app_id,
            len(levels),
            dict(list(levels.items())[:5]),
        )

        if self._status_pending_app is not None and self._status_pending_app == app_id:
            # Accumulate into pending status request.
            for group, level in levels.items():
                if group < 256:
                    self._status_levels[(app_id, group)] = level
        else:
            # Unsolicited status update — dispatch to status callbacks.
            result: dict[tuple[int, int], int] = {}
            for group, level in levels.items():
                result[(app_id, group)] = level
            for callback in tuple(self._status_callbacks):
                try:
                    callback(result)
                except Exception:
                    _LOGGER.exception("Error in status callback")
