"""Tests for pycbus protocol state machine.

Tests use a MockTransport to simulate PCI conversations without real
hardware or network access.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from pycbus.exceptions import CbusConnectionError, CbusTimeoutError
from pycbus.protocol import (
    CbusProtocol,
    ProtocolState,
    _build_cal_command,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


# ---------------------------------------------------------------------------
# Mock transport — simulates a PCI sending back scripted responses
# ---------------------------------------------------------------------------


class MockTransport:
    """A fake transport that replays scripted lines and records writes."""

    def __init__(self, lines: Sequence[bytes] = ()) -> None:
        self._lines: list[bytes] = list(lines)
        self._line_idx = 0
        self._connected = False
        self.written: list[bytes] = []

    @property
    def connected(self) -> bool:
        return self._connected

    def add_lines(self, *lines: bytes) -> None:
        """Append additional response lines."""
        self._lines.extend(lines)

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def read_line(self) -> bytes:
        if self._line_idx < len(self._lines):
            line = self._lines[self._line_idx]
            self._line_idx += 1
            return line
        # No more scripted lines — simulate a timeout.
        raise CbusTimeoutError("No more scripted lines")

    async def write(self, data: bytes) -> None:
        self.written.append(data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_init_responses() -> list[bytes]:
    """Standard PCI init conversation: reset ack + 4 CAL confirmations."""
    return [
        b"#",  # reset ack (ready prompt)
        b"g#",  # CAL App Address 1 = 0xFF confirmed
        b"g#",  # CAL App Address 2 = 0xFF confirmed
        b"g#",  # CAL Options #3 confirmed
        b"g#",  # CAL Options #1 confirmed
    ]


# ===========================================================================
# _build_cal_command
# ===========================================================================


class TestBuildCalCommand:
    """Test the CAL command builder."""

    def test_cal_options3(self) -> None:
        """CAL for Interface Options #3: param=0x42, offset=0x00, value=0x0E."""
        cmd = _build_cal_command(0x42, 0x00, 0x0E)
        # No '@' prefix, no checksum — just hex-encoded bytes.
        raw = bytes.fromhex(cmd.decode())
        assert raw == bytes([0xA3, 0x42, 0x00, 0x0E])

    def test_cal_options1(self) -> None:
        """CAL for Interface Options #1: param=0x30, offset=0x00, value=0x59."""
        cmd = _build_cal_command(0x30, 0x00, 0x59)
        raw = bytes.fromhex(cmd.decode())
        assert raw == bytes([0xA3, 0x30, 0x00, 0x59])

    def test_cal_app_address(self) -> None:
        """CAL for Application Address 1: param=0x21, offset=0x00, value=0x38."""
        cmd = _build_cal_command(0x21, 0x00, 0x38)
        raw = bytes.fromhex(cmd.decode())
        assert raw == bytes([0xA3, 0x21, 0x00, 0x38])


# ===========================================================================
# ProtocolState
# ===========================================================================


class TestProtocolState:
    """Test initial state and properties."""

    def test_initial_state(self) -> None:
        t = MockTransport()
        p = CbusProtocol(t)
        assert p.state == ProtocolState.DISCONNECTED
        assert p.connected is False


# ===========================================================================
# connect() — full init sequence
# ===========================================================================


class TestConnect:
    """Test the full connect → reset → init → READY sequence."""

    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        t = MockTransport(_make_init_responses())
        p = CbusProtocol(t)

        await p.connect()

        assert p.state == ProtocolState.READY
        assert p.connected is True
        assert t.connected is True
        # Should have sent: 3 reset tildes + 4 CAL commands (7 writes)
        assert len(t.written) == 7
        # First three writes are reset tildes
        for i in range(3):
            assert t.written[i] == b"~\r"
        # Next four are basic-mode CAL commands (no \, with conf code)
        for frame in t.written[3:]:
            assert not frame.startswith(b"\\")
            assert frame.endswith(b"\r")

    @pytest.mark.asyncio
    async def test_connect_already_ready(self) -> None:
        """Calling connect() twice is a no-op when already READY."""
        t = MockTransport(_make_init_responses())
        p = CbusProtocol(t)

        await p.connect()
        written_count = len(t.written)
        await p.connect()  # no-op
        assert len(t.written) == written_count

    @pytest.mark.asyncio
    async def test_connect_reset_timeout(self) -> None:
        """If PCI never sends ready prompt after reset, raise timeout."""
        # 20 lines of garbage, no '#' or '='
        t = MockTransport([b"junk"] * 20)
        p = CbusProtocol(t, max_retries=1)

        with pytest.raises(CbusConnectionError, match="Init failed"):
            await p.connect()

        assert p.state == ProtocolState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_connect_cal_rejected(self) -> None:
        """If PCI returns NEGATIVE for a CAL command, retry and fail."""
        # Reset succeeds, but CAL gets rejected
        t = MockTransport(
            [
                b"#",  # reset ack
                b"!",  # CAL rejected
                # Retry 2
                b"#",  # reset ack
                b"!",  # CAL rejected again
                # Retry 3
                b"#",  # reset ack
                b"!",  # CAL rejected again
            ]
        )
        p = CbusProtocol(t, max_retries=3)

        with pytest.raises(CbusConnectionError, match="Init failed"):
            await p.connect()

    @pytest.mark.asyncio
    async def test_connect_retry_then_success(self) -> None:
        """Init fails on first attempt but succeeds on retry."""
        t = MockTransport(
            [
                b"#",  # retry 1: reset ack
                b"!",  # retry 1: CAL rejected -> fail
                # retry 2: full success
                b"#",  # reset ack
                b"g#",  # CAL App Address 1 confirmed
                b"g#",  # CAL App Address 2 confirmed
                b"g#",  # CAL Options #3 confirmed
                b"g#",  # CAL Options #1 confirmed
            ]
        )
        p = CbusProtocol(t, max_retries=3)

        await p.connect()
        assert p.state == ProtocolState.READY

    @pytest.mark.asyncio
    async def test_connect_with_equals_prompt(self) -> None:
        """PCI may send '=' instead of '#' after reset."""
        t = MockTransport(
            [
                b"=",  # alternate reset ack
                b"g#",  # CAL App Address 1
                b"g#",  # CAL App Address 2
                b"g#",  # CAL Options #3
                b"g#",  # CAL Options #1
            ]
        )
        p = CbusProtocol(t)

        await p.connect()
        assert p.state == ProtocolState.READY


# ===========================================================================
# disconnect()
# ===========================================================================


class TestDisconnect:
    """Test disconnect behaviour."""

    @pytest.mark.asyncio
    async def test_disconnect(self) -> None:
        t = MockTransport(_make_init_responses())
        p = CbusProtocol(t)

        await p.connect()
        await p.disconnect()

        assert p.state == ProtocolState.DISCONNECTED
        assert t.connected is False

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self) -> None:
        """Disconnecting when not connected doesn't raise."""
        t = MockTransport()
        p = CbusProtocol(t)
        await p.disconnect()
        assert p.state == ProtocolState.DISCONNECTED


# ===========================================================================
# send_command()
# ===========================================================================


class TestSendCommand:
    """Test SAL command sending with confirmation."""

    @pytest.mark.asyncio
    async def test_send_command_positive(self) -> None:
        """Command gets POSITIVE confirmation."""
        t = MockTransport(_make_init_responses())
        p = CbusProtocol(t)
        await p.connect()

        # Stop the read loop so we control responses manually
        await p._stop_read_loop()

        # After init (h,i,j,k used), next confirmation code is 'l'.
        expected_conf = b"l"

        # Prepare the confirmation — PCI echoes our code + '.'
        async def _simulate_confirm() -> None:
            await asyncio.sleep(0.01)
            p._handle_line(expected_conf + b".")

        task = asyncio.create_task(_simulate_confirm())
        result = await p.send_command(b"0538007901FF50")
        await task

        assert result is True
        # The written frame should include the confirmation code.
        assert t.written[-1] == b"\\0538007901FF50l\r"

    @pytest.mark.asyncio
    async def test_send_command_negative(self) -> None:
        """Command gets NEGATIVE confirmation."""
        t = MockTransport(_make_init_responses())
        p = CbusProtocol(t)
        await p.connect()

        await p._stop_read_loop()

        # After init (h,i,j,k), next code is 'l'.
        async def _simulate_reject() -> None:
            await asyncio.sleep(0.01)
            p._handle_line(b"l!")

        task = asyncio.create_task(_simulate_reject())
        result = await p.send_command(b"0538007901FF50")
        await task

        assert result is False

    @pytest.mark.asyncio
    async def test_send_command_not_ready(self) -> None:
        """Sending when not READY raises CbusConnectionError."""
        t = MockTransport()
        p = CbusProtocol(t)

        with pytest.raises(CbusConnectionError, match="Cannot send"):
            await p.send_command(b"0538007901FF50")


# ===========================================================================
# Event callbacks
# ===========================================================================


class TestEventCallbacks:
    """Test SAL event dispatch to registered callbacks."""

    def test_register_and_unregister(self) -> None:
        t = MockTransport()
        p = CbusProtocol(t)
        events: list[bytes] = []

        unsub = p.on_event(events.append)
        assert len(p._event_callbacks) == 1

        unsub()
        assert len(p._event_callbacks) == 0

    def test_dispatch_valid_hex(self) -> None:
        """Valid hex SAL event with correct checksum is dispatched."""
        t = MockTransport()
        p = CbusProtocol(t)
        events: list[bytes] = []
        p.on_event(events.append)

        # Build a valid checksummed SAL frame in hex
        from pycbus.checksum import checksum

        sal_bytes = bytes([0x05, 0x38, 0x00, 0x79, 0x01, 0xFF])
        cs = checksum(sal_bytes)
        full = sal_bytes + bytes([cs])
        hex_line = full.hex().upper().encode()

        p._dispatch_event(hex_line)

        assert len(events) == 1
        assert events[0] == full

    def test_dispatch_invalid_hex_ignored(self) -> None:
        """Non-hex data is silently ignored."""
        t = MockTransport()
        p = CbusProtocol(t)
        events: list[bytes] = []
        p.on_event(events.append)

        p._dispatch_event(b"not-hex-data!!!")

        assert len(events) == 0

    def test_dispatch_bad_checksum_ignored(self) -> None:
        """Hex data with bad checksum is ignored."""
        t = MockTransport()
        p = CbusProtocol(t)
        events: list[bytes] = []
        p.on_event(events.append)

        # Valid hex but bad checksum
        p._dispatch_event(b"0538007901FF00")

        assert len(events) == 0


# ===========================================================================
# _handle_line — line classification
# ===========================================================================


class TestHandleLine:
    """Test the line classification logic."""

    def test_bare_ready_prompt(self) -> None:
        """A bare '#' is recognised as a status prompt."""
        t = MockTransport()
        p = CbusProtocol(t)
        events: list[bytes] = []
        p.on_event(events.append)

        p._handle_line(b"#")
        assert len(events) == 0

    def test_confirmation_sets_event(self) -> None:
        """A 'g' line sets the confirmation event."""
        t = MockTransport()
        p = CbusProtocol(t)

        p._handle_line(b"g#")

        assert p._confirmation_event.is_set()
        assert b"g" in p._last_confirmation

    def test_negative_sets_event(self) -> None:
        """A '!' line sets the confirmation event."""
        t = MockTransport()
        p = CbusProtocol(t)

        p._handle_line(b"!")

        assert p._confirmation_event.is_set()
        assert b"!" in p._last_confirmation
