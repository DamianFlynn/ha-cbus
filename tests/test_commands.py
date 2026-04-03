"""Tests for pycbus command builders."""

from __future__ import annotations

from pycbus.checksum import verify
from pycbus.commands import lighting_off, lighting_on, lighting_ramp
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
