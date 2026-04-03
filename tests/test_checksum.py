"""Tests for pycbus checksum module."""

from __future__ import annotations

from pycbus.checksum import checksum, verify


def test_checksum_known_value() -> None:
    """Verify checksum against a known C-Bus command."""
    # Lighting ON: 05 38 00 79 01 FF → checksum should make sum ≡ 0 mod 256
    data = bytes([0x05, 0x38, 0x00, 0x79, 0x01, 0xFF])
    cs = checksum(data)
    assert 0 <= cs <= 0xFF
    assert (sum(data) + cs) & 0xFF == 0x00


def test_verify_valid() -> None:
    """Verify returns True when checksum is appended."""
    data = bytes([0x05, 0x38, 0x00, 0x79, 0x01, 0xFF])
    cs = checksum(data)
    assert verify(data + bytes([cs]))


def test_verify_invalid() -> None:
    """Verify returns False for corrupted data."""
    data = bytes([0x05, 0x38, 0x00, 0x79, 0x01, 0xFF, 0x00])
    assert not verify(data)


def test_checksum_zero_data() -> None:
    """Checksum of all-zero bytes."""
    data = bytes([0x00, 0x00, 0x00])
    cs = checksum(data)
    assert cs == 0x00
    assert verify(data + bytes([cs]))
