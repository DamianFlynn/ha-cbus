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

import pytest

from pycbus.checksum import verify
from pycbus.commands import (
    MeasurementData,
    enable_off,
    enable_on,
    lighting_off,
    lighting_on,
    lighting_ramp,
    parse_measurement_data,
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
        cmd = status_request(ApplicationId.LIGHTING)
        assert verify(cmd)

    def test_status_request_structure(self) -> None:
        """Status request: 05 FF 00 7A <app> 00 <checksum>."""
        cmd = status_request(ApplicationId.LIGHTING)
        assert len(cmd) == 7
        assert cmd[0] == 0x05  # DAT broadcast
        assert cmd[1] == 0xFF  # STATUS_REQUEST pseudo-app
        assert cmd[2] == 0x00  # network
        assert cmd[3] == 0x7A  # binary status opcode
        assert cmd[4] == ApplicationId.LIGHTING  # target app
        assert cmd[5] == 0x00  # starting group

    def test_status_request_matches_spec_example(self) -> None:
        """Must match the example from C-Bus Serial Interface Guide p23.

        The spec example: \\05FF007A38004A
        """
        cmd = status_request(ApplicationId.LIGHTING)
        assert cmd.hex().upper() == "05FF007A38004A"

    def test_status_request_enable_app(self) -> None:
        """Status request for Enable app should use correct app ID."""
        cmd = status_request(ApplicationId.ENABLE)
        assert cmd[4] == ApplicationId.ENABLE


# ------------------------------------------------------------------
# Status reply parser tests
# ------------------------------------------------------------------


class TestParseStatusReply:
    """Tests for parse_status_reply.

    Status replies use CAL header format:
    - Standard: [C0|cnt] [app] [block_start] [2-bit data...] [chk]
    - Extended: [E0|cnt] [coding] [app] [block_start] [2-bit data...] [chk]

    Binary 2-bit encoding: 00=missing, 01=ON(255), 10=OFF(0), 11=error.
    """

    def test_standard_binary_reply(self) -> None:
        """Standard format binary status reply — groups 0-3."""
        from pycbus.checksum import checksum as cs

        # Standard: [C0|cnt] [app] [block_start] [data] [checksum]
        # 0x06 = 0b00000110: bits[1:0]=10(OFF), bits[3:2]=01(ON)
        payload = bytes([0xC4, 0x38, 0x00, 0x06])
        chk = cs(payload)
        data = payload + bytes([chk])
        app_id, result = parse_status_reply(data)
        assert app_id == 0x38
        assert result[0] == 0  # OFF
        assert result[1] == 255  # ON
        assert 2 not in result  # missing = skipped
        assert 3 not in result  # missing = skipped

    def test_extended_binary_reply(self) -> None:
        """Extended format binary status reply — coding=0x00."""
        from pycbus.checksum import checksum as cs

        # Extended: [E0|cnt] [coding] [app] [block_start] [data] [chk]
        # 0x05 = 0b00000101: bits[1:0]=01(ON), bits[3:2]=01(ON)
        payload = bytes([0xE5, 0x00, 0x38, 0x00, 0x05])
        chk = cs(payload)
        data = payload + bytes([chk])
        app_id, result = parse_status_reply(data)
        assert app_id == 0x38
        assert result[0] == 255  # ON
        assert result[1] == 255  # ON
        assert 2 not in result  # missing
        assert 3 not in result  # missing

    def test_extended_binary_elsewhere(self) -> None:
        """Extended format with coding=0x40 (binary, elsewhere)."""
        from pycbus.checksum import checksum as cs

        # 0x09 = 0b00001001: bits[1:0]=01(ON), bits[3:2]=10(OFF)
        payload = bytes([0xE5, 0x40, 0x38, 0x00, 0x09])
        chk = cs(payload)
        data = payload + bytes([chk])
        app_id, result = parse_status_reply(data)
        assert app_id == 0x38
        assert result[0] == 255  # ON
        assert result[1] == 0  # OFF
        assert 2 not in result  # missing
        assert 3 not in result  # missing

    def test_block_start_offset(self) -> None:
        """Groups should be offset by block_start."""
        from pycbus.checksum import checksum as cs

        # block_start=0x58 (88), data has grp88=ON
        payload = bytes([0xC4, 0x38, 0x58, 0x01])
        chk = cs(payload)
        data = payload + bytes([chk])
        app_id, result = parse_status_reply(data)
        assert app_id == 0x38
        assert result[88] == 255  # ON at group 88

    def test_spec_example_first_line(self) -> None:
        """Verify against the example from Serial Interface Guide p46.

        First line: D8380068AA01...
        D8=header(std, 24 bytes), 38=app, 00=block_start
        68: grp0=miss, grp1=OFF, grp2=OFF, grp3=ON  (0b01101000)
        AA: grp4=OFF, grp5=OFF, grp6=OFF, grp7=OFF  (0b10101010)
        01: grp8=ON, grp9=miss, grp10=miss, grp11=miss (0b00000001)
        """
        from pycbus.checksum import checksum as cs

        # Just the first 3 data bytes from the example
        payload = bytes([0xC6, 0x38, 0x00, 0x68, 0xAA, 0x01])
        chk = cs(payload)
        data = payload + bytes([chk])
        app_id, result = parse_status_reply(data)
        assert app_id == 0x38
        assert 0 not in result  # missing
        assert result[1] == 0  # OFF
        assert result[2] == 0  # OFF
        assert result[3] == 255  # ON
        assert result[4] == 0  # OFF
        assert result[5] == 0  # OFF
        assert result[8] == 255  # ON

    def test_long_form_extended_reply(self) -> None:
        """Long-form reply (SMART+EXSTAT): 86 <addrs> <CAL data>."""
        from pycbus.checksum import checksum as cs

        # Long-form: 86 01 01 00 <extended CAL> <checksum>
        # Inner CAL: F9(ext,25 bytes) 00(binary,this SI) 38(app) 00(block)
        # Then 1 data byte: 0x05 = bits[1:0]=01(ON), bits[3:2]=01(ON)
        inner_cal = bytes([0xE5, 0x00, 0x38, 0x00, 0x05])
        long_form = bytes([0x86, 0x01, 0x01, 0x00]) + inner_cal
        chk = cs(long_form)
        data = long_form + bytes([chk])
        app_id, result = parse_status_reply(data)
        assert app_id == 0x38
        assert result[0] == 255  # ON
        assert result[1] == 255  # ON

    def test_long_form_real_capture(self) -> None:
        """Parse a real captured long-form reply from live hardware.

        Line: 86010100F9003800A8AAAAA6AAA6A6AAAAA6AAAA6AA9AAAA68A99A00AA02A3
        """
        data = bytes.fromhex(
            "86010100F9003800A8AAAAA6AAA6A6AAAAA6AAAA6AA9AAAA68A99A00AA02A3"
        )
        app_id, result = parse_status_reply(data)
        assert app_id == 0x38
        # Should have parsed some groups.
        assert len(result) > 0
        # Verify some known states from the capture.
        # Data starts at block 0: A8 = 0b10101000
        # bits[1:0]=00(miss), bits[3:2]=10(OFF), bits[5:4]=10(OFF), bits[7:6]=10(OFF)
        assert 0 not in result  # missing
        assert result[1] == 0  # OFF
        assert result[2] == 0  # OFF
        assert result[3] == 0  # OFF

    def test_empty_reply_returns_empty(self) -> None:
        """Too-short data should return empty dict."""
        assert parse_status_reply(b"\xd8\x38\x00") == (0, {})

    def test_unknown_header_returns_empty(self) -> None:
        """Non-status header should return empty dict."""
        from pycbus.checksum import checksum as cs

        payload = bytes([0x05, 0x38, 0x00, 0x10, 0xFF])
        chk = cs(payload)
        data = payload + bytes([chk])
        assert parse_status_reply(data) == (0, {})


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
            (0x12, 49, 0),  # group 49 -> off
            (0x12, 74, 127),  # group 74 -> 50%
            (0x12, 52, 51),  # group 52 -> 20%
            (0x12, 37, 255),  # group 37 -> 100%
            (0x12, 50, 0),  # group 50 -> off
        ]
        for cmd, (opcode, group, level) in zip(event.commands, expected, strict=True):
            assert cmd.opcode == opcode
            assert cmd.group == group
            assert cmd.data == level

    def test_too_short_returns_none(self) -> None:
        """Data shorter than minimum (7 bytes) returns None."""
        assert parse_sal_event(b"\x05\x0d\x38\x00\x79") is None
        assert parse_sal_event(b"\x05\x0d") is None
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


# ===========================================================================
# Measurement Application (app 228 / 0xE4)
# ===========================================================================
#
# Wire format: 0x0E <device_id> <channel> <units> <multiplier> <msb> <lsb>
# Reference: Chapter 28 — C-Bus Measurement Application.


class TestMeasurementParser:
    """Tests for parse_measurement_data and MeasurementData."""

    def test_basic_lux_reading(self) -> None:
        """Simple positive Lux reading: 500 lx (raw=500, mult=0)."""
        # opcode=0x0E, dev=1, ch=0, unit=0x10(Lux), mult=0, value=500
        sal = bytes([0x0E, 0x01, 0x00, 0x10, 0x00, 0x01, 0xF4])
        results = parse_measurement_data(sal)
        assert len(results) == 1
        m = results[0]
        assert m.device_id == 1
        assert m.channel == 0
        assert m.unit_code == 0x10
        assert m.multiplier == 0
        assert m.raw_value == 500
        assert m.value == 500.0
        assert m.unit_label == "lx"

    def test_negative_multiplier(self) -> None:
        """Multiplier -2: raw=1234 x 10^-2 = 12.34."""
        # mult=0xFE = -2 in two's complement
        sal = bytes([0x0E, 0x05, 0x01, 0x10, 0xFE, 0x04, 0xD2])
        results = parse_measurement_data(sal)
        assert len(results) == 1
        m = results[0]
        assert m.multiplier == -2
        assert m.raw_value == 1234
        assert m.value == pytest.approx(12.34)

    def test_positive_multiplier(self) -> None:
        """Multiplier +2: raw=15 x 10^2 = 1500."""
        sal = bytes([0x0E, 0x02, 0x00, 0x10, 0x02, 0x00, 0x0F])
        results = parse_measurement_data(sal)
        assert len(results) == 1
        assert results[0].value == 1500.0

    def test_negative_raw_value(self) -> None:
        """Signed 16-bit: raw=-10 (0xFFF6), mult=0 → value=-10."""
        sal = bytes([0x0E, 0x03, 0x00, 0x11, 0x00, 0xFF, 0xF6])
        results = parse_measurement_data(sal)
        assert len(results) == 1
        m = results[0]
        assert m.raw_value == -10
        assert m.value == -10.0

    def test_zero_value(self) -> None:
        """Zero reading."""
        sal = bytes([0x0E, 0x01, 0x00, 0x10, 0x00, 0x00, 0x00])
        results = parse_measurement_data(sal)
        assert len(results) == 1
        assert results[0].raw_value == 0
        assert results[0].value == 0.0

    def test_max_positive_value(self) -> None:
        """Maximum positive 16-bit: raw=32767 (0x7FFF)."""
        sal = bytes([0x0E, 0x01, 0x00, 0x10, 0x00, 0x7F, 0xFF])
        results = parse_measurement_data(sal)
        assert len(results) == 1
        assert results[0].raw_value == 32767

    def test_min_negative_value(self) -> None:
        """Minimum negative 16-bit: raw=-32768 (0x8000)."""
        sal = bytes([0x0E, 0x01, 0x00, 0x10, 0x00, 0x80, 0x00])
        results = parse_measurement_data(sal)
        assert len(results) == 1
        assert results[0].raw_value == -32768

    def test_concatenated_commands(self) -> None:
        """Two measurement events concatenated in one SAL packet."""
        cmd1 = bytes([0x0E, 0x01, 0x00, 0x10, 0x00, 0x01, 0xF4])  # 500 lx
        cmd2 = bytes([0x0E, 0x01, 0x01, 0x00, 0x00, 0x00, 0x19])  # 25 °C
        sal = cmd1 + cmd2
        results = parse_measurement_data(sal)
        assert len(results) == 2
        assert results[0].channel == 0
        assert results[0].unit_code == 0x10  # Lux
        assert results[0].raw_value == 500
        assert results[1].channel == 1
        assert results[1].unit_code == 0x00  # °C
        assert results[1].raw_value == 25

    def test_truncated_data_returns_partial(self) -> None:
        """Truncated command at end should return what was parsed so far."""
        complete = bytes([0x0E, 0x01, 0x00, 0x10, 0x00, 0x01, 0xF4])
        truncated = bytes([0x0E, 0x01, 0x00])  # incomplete
        sal = complete + truncated
        results = parse_measurement_data(sal)
        assert len(results) == 1  # only the complete one
        assert results[0].raw_value == 500

    def test_empty_data(self) -> None:
        """Empty input returns empty list."""
        assert parse_measurement_data(b"") == []

    def test_unknown_command_skipped(self) -> None:
        """Non-MEASUREMENT_EVENT command code is skipped."""
        # opcode 0x06: command_code=0 (not 1), arg_count=6
        sal = bytes([0x06, 0x01, 0x00, 0x10, 0x00, 0x01, 0xF4])
        results = parse_measurement_data(sal)
        assert len(results) == 0

    def test_unknown_unit_code_label(self) -> None:
        """Unknown unit code falls back to hex label."""
        sal = bytes([0x0E, 0x01, 0x00, 0xEE, 0x00, 0x00, 0x01])
        results = parse_measurement_data(sal)
        assert len(results) == 1
        assert results[0].unit_label == "unit_0xEE"

    def test_temperature_celsius_unit(self) -> None:
        """Unit 0x00 = degrees Celsius."""
        sal = bytes([0x0E, 0x01, 0x00, 0x00, 0xFE, 0x09, 0xC4])
        results = parse_measurement_data(sal)
        assert len(results) == 1
        m = results[0]
        assert m.unit_code == 0x00
        assert m.unit_label == "°C"
        # raw=2500, mult=-2 → 25.00
        assert m.value == pytest.approx(25.0)

    def test_measurement_data_frozen(self) -> None:
        """MeasurementData should be immutable."""
        m = MeasurementData(
            device_id=1, channel=0, unit_code=0x10, multiplier=0, raw_value=100
        )
        with pytest.raises(AttributeError):
            m.device_id = 2  # type: ignore[misc]


# ===================================================================
# Label (eDLT) command builders
# ===================================================================


class TestLightingLabel:
    """Tests for lighting label (eDLT) command builders.

    Reference: *Chapter 02 — C-Bus Lighting Application*, s2.6.5.
    The Label command is a long-form SAL command: %101LLLLL where
    LLLLL = argument byte count (group + options + language + text).
    """

    def test_label_checksum_valid(self) -> None:
        """Label command should have a valid checksum."""
        from pycbus.commands import lighting_label

        cmd = lighting_label(group=129, text="Hello")
        assert verify(cmd)

    def test_label_structure_basic(self) -> None:
        """Label command byte layout: DAT, app, net, opcode, group, opts, lang, text."""
        from pycbus.commands import lighting_label

        cmd = lighting_label(group=10, text="Test")
        assert cmd[0] == 0x05  # DAT BROADCAST
        assert cmd[1] == 0x38  # Lighting app
        assert cmd[2] == 0x00  # network 0
        # opcode: 0xA0 | (3 + len("Test")) = 0xA0 | 7 = 0xA7
        assert cmd[3] == 0xA7
        assert cmd[4] == 10  # group address
        assert cmd[5] == 0x00  # options: text label, flavour 0
        assert cmd[6] == 0x01  # language: English
        assert cmd[7:11] == b"Test"  # text bytes

    def test_label_opcode_encodes_length(self) -> None:
        """The opcode's low 5 bits should be 3 + len(text)."""
        from pycbus.commands import lighting_label

        for text in ["", "A", "Hello World!1234"]:
            cmd = lighting_label(group=1, text=text)
            expected = 0xA0 | (3 + len(text))
            assert cmd[3] == expected, f"text={text!r}: expected 0x{expected:02X}"

    def test_label_flavour_encoding(self) -> None:
        """Flavour (0-3) should be encoded in bits 6:5 of the options byte."""
        from pycbus.commands import lighting_label

        for flavour in range(4):
            cmd = lighting_label(group=1, text="Hi", flavour=flavour)
            assert cmd[5] == (flavour << 5)

    def test_label_language_byte(self) -> None:
        """Language code should appear as the third argument byte."""
        from pycbus.commands import lighting_label
        from pycbus.constants import LabelLanguage

        cmd = lighting_label(group=1, text="G'day", language=LabelLanguage.ENGLISH_AU)
        assert cmd[6] == 0x02  # English (Australia)

    def test_label_network_parameter(self) -> None:
        """Network number should be the third byte."""
        from pycbus.commands import lighting_label

        cmd = lighting_label(group=1, text="Hi", network=254)
        assert cmd[2] == 254

    def test_label_max_text_length(self) -> None:
        """16-character text should be accepted."""
        from pycbus.commands import lighting_label

        cmd = lighting_label(group=1, text="1234567890ABCDEF")
        assert verify(cmd)
        # opcode: 0xA0 | (3 + 16) = 0xA0 | 19 = 0xB3
        assert cmd[3] == 0xB3

    def test_label_text_too_long_raises(self) -> None:
        """Text exceeding 16 characters should raise ValueError."""
        from pycbus.commands import lighting_label

        with pytest.raises(ValueError, match="exceeds 16"):
            lighting_label(group=1, text="12345678901234567")

    def test_label_invalid_flavour_raises(self) -> None:
        """Flavour outside 0-3 should raise ValueError."""
        from pycbus.commands import lighting_label

        with pytest.raises(ValueError, match="Flavour must be 0-3"):
            lighting_label(group=1, text="Hi", flavour=4)
        with pytest.raises(ValueError, match="Flavour must be 0-3"):
            lighting_label(group=1, text="Hi", flavour=-1)

    def test_clear_label_is_empty_text(self) -> None:
        """clear_label should produce a label command with zero text bytes."""
        from pycbus.commands import lighting_clear_label

        cmd = lighting_clear_label(group=10, flavour=1)
        assert verify(cmd)
        # opcode: 0xA0 | 3 = 0xA3 (group + options + language, no text)
        assert cmd[3] == 0xA3
        # Options: text label + flavour 1 (bit 5 set)
        assert cmd[5] == (1 << 5)
        # No text bytes — command ends at language + checksum
        assert len(cmd) == 8  # DAT + app + net + opcode + grp + opts + lang + chk

    def test_label_matches_cgate_mqtt_example(self) -> None:
        """Verify a label frame matching the cgate-mqtt 'Hello' example.

        cgate-mqtt sends: lighting label 254/56 1 129 - 0 48656C6C6F
        Which is: group=129, button (flavour)=0, text='Hello', hex-encoded.

        Our SAL frame should contain the same text bytes and target the
        same group on the default network.
        """
        from pycbus.commands import lighting_label

        cmd = lighting_label(group=129, text="Hello")
        assert verify(cmd)
        assert cmd[1] == 0x38  # Lighting app
        assert cmd[4] == 129  # group 129
        assert cmd[5] == 0x00  # flavour 0
        # text starts at byte 7
        assert cmd[7:12] == b"Hello"


class TestLightingSalSizeLabel:
    """Test sal_size correctly handles label (long-form) opcodes."""

    def test_sal_size_label_short_text(self) -> None:
        """Label opcode with 4-char text: 0xA7 -> 1 + 7 = 8 bytes."""
        from pycbus.applications.lighting import sal_size

        # 0xA7 = 0xA0 | 7, meaning 7 argument bytes follow
        assert sal_size(0xA7) == 8

    def test_sal_size_label_empty_text(self) -> None:
        """Label opcode with no text: 0xA3 -> 1 + 3 = 4 bytes."""
        from pycbus.applications.lighting import sal_size

        assert sal_size(0xA3) == 4

    def test_sal_size_label_max_text(self) -> None:
        """Label opcode with 16-char text: 0xB3 -> 1 + 19 = 20 bytes."""
        from pycbus.applications.lighting import sal_size

        assert sal_size(0xB3) == 20

    def test_sal_size_ramp_still_works(self) -> None:
        """Ramp opcode should still return 3 bytes."""
        from pycbus.applications.lighting import sal_size

        assert sal_size(0x02) == 3  # RAMP_INSTANT

    def test_sal_size_on_off_still_works(self) -> None:
        """ON/OFF should still return 2 bytes."""
        from pycbus.applications.lighting import sal_size

        assert sal_size(0x79) == 2  # ON
        assert sal_size(0x01) == 2  # OFF
