"""Tests for pycbus SAL command builders.

Each command builder (lighting_on, lighting_off, lighting_ramp,
lighting_terminate_ramp) produces a checksummed byte sequence ready
for hex-encoding and wire framing.  These tests verify:

- Checksum validity for every command type.
- Correct byte layout (DAT, app ID, network, opcode, group, level).
- Expected payload length (ON/RAMP = 7 bytes, OFF = 6 bytes).

Reference: *Chapter 02 — C-Bus Lighting Application*, §2.6.
"""

from __future__ import annotations

from pycbus.checksum import verify
from pycbus.commands import (
    enable_off,
    enable_on,
    lighting_off,
    lighting_on,
    lighting_ramp,
    parse_sal_event,
    parse_status_reply,
    status_request,
    trigger_event,
)
from pycbus.constants import ApplicationId, LightingCommand


def test_lighting_on_checksum_valid() -> None:
    """ON command should have a valid checksum."""
    cmd = lighting_on(group=1)
    assert verify(cmd)


def test_lighting_off_checksum_valid() -> None:
    """OFF command should have a valid checksum."""
    cmd = lighting_off(group=1)
    assert verify(cmd)


def test_lighting_ramp_checksum_valid() -> None:
    """RAMP command should have a valid checksum."""
    cmd = lighting_ramp(group=10, level=128, rate=LightingCommand.RAMP_4S)
    assert verify(cmd)


def test_lighting_on_structure() -> None:
    """ON command should match expected structure (before checksum)."""
    cmd = lighting_on(group=5)
    # 05 38 00 79 05 FF <checksum>
    assert cmd[0] == 0x05  # DAT
    assert cmd[1] == 0x38  # app 56
    assert cmd[2] == 0x00  # network
    assert cmd[3] == 0x79  # ON opcode
    assert cmd[4] == 0x05  # group
    assert cmd[5] == 0xFF  # level
    assert len(cmd) == 7  # 6 payload + 1 checksum


# ===========================================================================
# Enable Control (app 203 / 0xCB)
# ===========================================================================


def test_enable_on_checksum_valid() -> None:
    """Enable ON command should have a valid checksum."""
    cmd = enable_on(group=10)
    assert verify(cmd)


def test_enable_off_checksum_valid() -> None:
    """Enable OFF command should have a valid checksum."""
    cmd = enable_off(group=10)
    assert verify(cmd)


def test_enable_on_structure() -> None:
    """Enable ON command should match expected structure."""
    cmd = enable_on(group=10)
    # 05 CB 00 79 0A FF <checksum>
    assert cmd[0] == 0x05  # DAT
    assert cmd[1] == 0xCB  # app 203
    assert cmd[2] == 0x00  # network
    assert cmd[3] == 0x79  # ON opcode
    assert cmd[4] == 10  # group
    assert cmd[5] == 0xFF  # level
    assert len(cmd) == 7


def test_enable_off_structure() -> None:
    """Enable OFF command should match expected structure."""
    cmd = enable_off(group=10)
    # 05 CB 00 01 0A <checksum>
    assert cmd[0] == 0x05  # DAT
    assert cmd[1] == 0xCB  # app 203
    assert cmd[2] == 0x00  # network
    assert cmd[3] == 0x01  # OFF opcode
    assert cmd[4] == 10  # group
    assert len(cmd) == 6  # no level byte for OFF


# ===========================================================================
# Trigger Control (app 202 / 0xCA)
# ===========================================================================


def test_trigger_event_checksum_valid() -> None:
    """Trigger event command should have a valid checksum."""
    cmd = trigger_event(group=5, action=0)
    assert verify(cmd)


def test_trigger_event_structure() -> None:
    """Trigger event command should match expected structure."""
    cmd = trigger_event(group=5, action=42)
    # 05 CA 00 02 05 2A <checksum>
    assert cmd[0] == 0x05  # DAT
    assert cmd[1] == 0xCA  # app 202
    assert cmd[2] == 0x00  # network
    assert cmd[3] == 0x02  # TRIGGER_MIN opcode
    assert cmd[4] == 5  # group
    assert cmd[5] == 42  # action
    assert len(cmd) == 7


def test_trigger_event_default_action() -> None:
    """Trigger with default action should use 0."""
    cmd = trigger_event(group=1)
    assert cmd[5] == 0x00


# ------------------------------------------------------------------
# Status request builder tests
# ------------------------------------------------------------------


class TestStatusRequest:
    """Tests for the status_request builder."""

    def test_status_request_checksum_valid(self) -> None:
        """Status request should have a valid checksum."""
        cmd = status_request(ApplicationId.LIGHTING, block=0)
        assert verify(cmd)

    def test_status_request_structure(self) -> None:
        """Status request should be: FF <app> 73 <block> <checksum>."""
        cmd = status_request(ApplicationId.LIGHTING, block=0)
        assert len(cmd) == 5
        assert cmd[0] == 0xFF
        assert cmd[1] == ApplicationId.LIGHTING
        assert cmd[2] == 0x73
        assert cmd[3] == 0x00

    def test_status_request_block_1(self) -> None:
        """Block 1 should be encoded in byte 3."""
        cmd = status_request(ApplicationId.LIGHTING, block=1)
        assert cmd[3] == 0x01

    def test_status_request_block_2(self) -> None:
        """Block 2 should be encoded in byte 3."""
        cmd = status_request(ApplicationId.LIGHTING, block=2)
        assert cmd[3] == 0x02

    def test_status_request_enable_app(self) -> None:
        """Status request for Enable app should use correct app ID."""
        cmd = status_request(ApplicationId.ENABLE, block=0)
        assert cmd[1] == ApplicationId.ENABLE

    def test_status_request_invalid_block(self) -> None:
        """Block outside 0-2 should raise ValueError."""
        import pytest

        with pytest.raises(ValueError, match="Block must be"):
            status_request(ApplicationId.LIGHTING, block=3)


# ------------------------------------------------------------------
# Status reply parser tests
# ------------------------------------------------------------------


class TestParseStatusReply:
    """Tests for parse_status_reply."""

    def test_extended_status_reply(self) -> None:
        """Extended binary reply should parse group levels."""
        # Header: D8 38 00, Coding: E0, then pairs of (level, 00)
        # Groups 0,1,2 with levels 0, 128, 255
        from pycbus.checksum import checksum as cs

        payload = bytes([0xD8, 0x38, 0x00, 0xE0, 0x00, 0x00, 0x80, 0x00, 0xFF, 0x00])
        chk = cs(payload)
        data = payload + bytes([chk])
        result = parse_status_reply(data)
        assert result[0] == 0x00
        assert result[1] == 0x80
        assert result[2] == 0xFF

    def test_standard_status_reply(self) -> None:
        """Standard binary reply should parse group levels."""
        from pycbus.checksum import checksum as cs

        # Header: D8 38 00, Coding: C0, then one byte per group
        payload = bytes([0xD8, 0x38, 0x00, 0xC0, 0x00, 0x80, 0xFF])
        chk = cs(payload)
        data = payload + bytes([chk])
        result = parse_status_reply(data)
        assert result[0] == 0x00
        assert result[1] == 0x80
        assert result[2] == 0xFF

    def test_empty_reply_returns_empty(self) -> None:
        """Too-short data should return empty dict."""
        assert parse_status_reply(b"\xd8\x38\x00") == {}

    def test_unknown_coding_returns_empty(self) -> None:
        """Unknown coding byte should return empty dict."""
        from pycbus.checksum import checksum as cs

        payload = bytes([0xD8, 0x38, 0x00, 0x10, 0xFF])
        chk = cs(payload)
        data = payload + bytes([chk])
        assert parse_status_reply(data) == {}


# ===========================================================================
# SAL Monitor Event Parsing
# ===========================================================================
#
# Tests use real captured data from a live PCI in MONITOR mode.
# Packet format: DAT(05) + source + app + routing(00) + SAL data + checksum.


class TestParseSalEvent:
    """Tests for parse_sal_event using real captured monitor events."""

    def test_lighting_on(self) -> None:
        """Single lighting ON command — source=13, group=250."""
        # Captured: 05 0D 38 00 79 FA 43
        data = bytes.fromhex("050D380079FA43")
        event = parse_sal_event(data)
        assert event is not None
        assert event.source == 13
        assert event.app_id == 0x38
        assert event.routing == 0x00
        assert len(event.commands) == 1
        cmd = event.commands[0]
        assert cmd.opcode == 0x79  # ON
        assert cmd.group == 250
        assert cmd.data is None  # ON has no level byte

    def test_lighting_off(self) -> None:
        """Single lighting OFF command — source=13, group=250."""
        # Captured: 05 0D 38 00 01 FA BB
        data = bytes.fromhex("050D380001FABB")
        event = parse_sal_event(data)
        assert event is not None
        assert event.source == 13
        assert event.app_id == 0x38
        assert len(event.commands) == 1
        cmd = event.commands[0]
        assert cmd.opcode == 0x01  # OFF
        assert cmd.group == 250
        assert cmd.data is None

    def test_lighting_ramp_single(self) -> None:
        """Single lighting RAMP_8S command — source=2, group=49, level=0."""
        # Captured: 05 02 38 00 12 31 00 <checksum>
        from pycbus.checksum import checksum as cs

        payload = bytes([0x05, 0x02, 0x38, 0x00, 0x12, 0x31, 0x00])
        data = payload + bytes([cs(payload)])
        event = parse_sal_event(data)
        assert event is not None
        assert event.source == 2
        assert len(event.commands) == 1
        cmd = event.commands[0]
        assert cmd.opcode == 0x12  # RAMP_8S
        assert cmd.group == 49
        assert cmd.data == 0  # level

    def test_multi_command_scene_recall(self) -> None:
        """Multi-command RAMP scene from PACA — 5 ramp commands in one packet."""
        # Captured: 05 02 38 00 12 31 00 12 4A 7F 12 34 33 12 25 FF 12 32 00 B0
        data = bytes.fromhex("05023800123100124A7F1234331225FF123200B0")
        event = parse_sal_event(data)
        assert event is not None
        assert event.source == 2
        assert event.app_id == 0x38
        assert len(event.commands) == 5
        # Verify each ramp command in the scene
        expected = [
            (0x12, 49, 0),    # group 49 -> off
            (0x12, 74, 127),  # group 74 -> 50%
            (0x12, 52, 51),   # group 52 -> 20%
            (0x12, 37, 255),  # group 37 -> 100%
            (0x12, 50, 0),    # group 50 -> off
        ]
        for cmd, (opcode, group, level) in zip(
            event.commands, expected, strict=True
        ):
            assert cmd.opcode == opcode
            assert cmd.group == group
            assert cmd.data == level

    def test_too_short_returns_none(self) -> None:
        """Data shorter than minimum (7 bytes) returns None."""
        assert parse_sal_event(b"\x05\x0D\x38\x00\x79") is None
        assert parse_sal_event(b"\x05\x0D") is None
        assert parse_sal_event(b"") is None

    def test_truncated_ramp_yields_partial(self) -> None:
        """Truncated multi-command packet should return successfully parsed prefix."""
        from pycbus.checksum import checksum as cs

        # One complete OFF + one truncated RAMP (missing level byte)
        payload = bytes([0x05, 0x02, 0x38, 0x00, 0x01, 0x31, 0x12, 0x4A])
        data = payload + bytes([cs(payload)])
        event = parse_sal_event(data)
        assert event is not None
        assert len(event.commands) == 1  # only the OFF parsed
        assert event.commands[0].opcode == 0x01
        assert event.commands[0].group == 49

    def test_trigger_event(self) -> None:
        """Trigger application event — 3 bytes per command."""
        from pycbus.checksum import checksum as cs

        # Trigger: 05 <src=5> CA 00 02 <group=10> <action=42> <checksum>
        payload = bytes([0x05, 0x05, 0xCA, 0x00, 0x02, 0x0A, 0x2A])
        data = payload + bytes([cs(payload)])
        event = parse_sal_event(data)
        assert event is not None
        assert event.app_id == 0xCA
        assert event.source == 5
        assert len(event.commands) == 1
        cmd = event.commands[0]
        assert cmd.opcode == 0x02
        assert cmd.group == 10
        assert cmd.data == 42  # action

    def test_enable_on(self) -> None:
        """Enable application ON — 2 bytes per command, no data byte."""
        from pycbus.checksum import checksum as cs

        # Enable ON: 05 <src=3> CB 00 79 <group=20> <checksum>
        payload = bytes([0x05, 0x03, 0xCB, 0x00, 0x79, 0x14])
        data = payload + bytes([cs(payload)])
        event = parse_sal_event(data)
        assert event is not None
        assert event.app_id == 0xCB
        assert len(event.commands) == 1
        assert event.commands[0].opcode == 0x79
        assert event.commands[0].group == 20
        assert event.commands[0].data is None

    def test_enable_off(self) -> None:
        """Enable application OFF — 2 bytes per command."""
        from pycbus.checksum import checksum as cs

        payload = bytes([0x05, 0x03, 0xCB, 0x00, 0x01, 0x14])
        data = payload + bytes([cs(payload)])
        event = parse_sal_event(data)
        assert event is not None
        assert len(event.commands) == 1
        assert event.commands[0].opcode == 0x01
        assert event.commands[0].group == 20

    def test_unknown_app_falls_back_to_lighting_pattern(self) -> None:
        """Unknown application uses lighting heuristic (ramp = 3 bytes)."""
        from pycbus.checksum import checksum as cs

        # App 0xD0 (SECURITY), opcode 0x01 (non-ramp) -> 2 bytes
        payload = bytes([0x05, 0x01, 0xD0, 0x00, 0x01, 0x05])
        data = payload + bytes([cs(payload)])
        event = parse_sal_event(data)
        assert event is not None
        assert event.app_id == 0xD0
        assert len(event.commands) == 1
        assert event.commands[0].group == 5

    def test_frozen_dataclasses(self) -> None:
        """SalEvent and SalCommand should be immutable."""
        data = bytes.fromhex("050D380079FA43")
        event = parse_sal_event(data)
        assert event is not None
        with __import__("pytest").raises(AttributeError):
            event.source = 99  # type: ignore[misc]
        with __import__("pytest").raises(AttributeError):
            event.commands[0].group = 99  # type: ignore[misc]
