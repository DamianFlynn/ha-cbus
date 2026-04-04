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
    trigger_event,
)
from pycbus.constants import LightingCommand


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
