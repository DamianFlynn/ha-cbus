"""SAL and CAL command builders for C-Bus."""

from __future__ import annotations

from .checksum import checksum
from .constants import ApplicationId, LightingCommand, PointToMultipointDAT


def _build_pm_command(*payload_bytes: int) -> bytes:
    """Build a point-to-multipoint command with checksum.

    Returns the raw bytes to be hex-encoded and framed with ``\\`` prefix
    and ``\\r`` suffix before transmission.
    """
    raw = bytes(payload_bytes)
    cs = checksum(raw)
    return raw + bytes([cs])


def lighting_on(group: int, network: int = 0) -> bytes:
    """Build a Lighting ON command (group → 0xFF)."""
    return _build_pm_command(
        PointToMultipointDAT.BROADCAST,
        ApplicationId.LIGHTING,
        network,
        LightingCommand.ON,
        group,
        0xFF,
    )


def lighting_off(group: int, network: int = 0) -> bytes:
    """Build a Lighting OFF command (group → 0x00)."""
    return _build_pm_command(
        PointToMultipointDAT.BROADCAST,
        ApplicationId.LIGHTING,
        network,
        LightingCommand.OFF,
        group,
    )


def lighting_ramp(
    group: int, level: int, rate: LightingCommand = LightingCommand.RAMP_INSTANT, network: int = 0
) -> bytes:
    """Build a Lighting RAMP command (group → level at rate)."""
    return _build_pm_command(
        PointToMultipointDAT.BROADCAST,
        ApplicationId.LIGHTING,
        network,
        rate,
        group,
        level & 0xFF,
    )


def lighting_terminate_ramp(group: int, network: int = 0) -> bytes:
    """Build a TERMINATE RAMP command for a group."""
    return _build_pm_command(
        PointToMultipointDAT.BROADCAST,
        ApplicationId.LIGHTING,
        network,
        LightingCommand.TERMINATE_RAMP,
        group,
    )
