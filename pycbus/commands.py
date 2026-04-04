"""SAL and CAL command builders for C-Bus.

This module constructs the raw byte sequences for *Short Application Layer*
(SAL) commands that are sent to the C-Bus PCI/CNI.  Each builder returns
the complete payload **including** the trailing checksum byte, ready to be
hex-encoded and framed for transmission.

Framing (done by the transport / protocol layer, not here)::

    Wire format:   \\<hex-encoded payload>\\r
    Example ON:    \\0538007901FF50\\r

Command structure (point-to-multipoint, broadcast)::

    Byte 0:  0x05     — DAT (broadcast)
    Byte 1:  <app>    — Application ID (e.g. 0x38 = Lighting)
    Byte 2:  <net>    — Network number (0x00 = default)
    Byte 3:  <opcode> — SAL opcode (ON / OFF / RAMP_* / TERMINATE_RAMP)
    Byte 4:  <group>  — Target group address (0-255)
    Byte 5:  [level]  — Optional target level (0x00-0xFF), present for ON/RAMP
    Byte 6:  <chk>    — Two's-complement checksum

References:
    - *C-Bus Serial Interface User Guide*, §4.3.3 — Point-to-Multipoint
    - *Chapter 02 — C-Bus Lighting Application*, §2.6 — SAL Commands

Usage::

    >>> from pycbus.commands import lighting_on, lighting_ramp
    >>> from pycbus.constants import LightingCommand
    >>> lighting_on(group=1).hex()
    '0538007901ff50'
    >>> lighting_ramp(group=5, level=128, rate=LightingCommand.RAMP_4S).hex()
    '0538000a058034'
"""

from __future__ import annotations

from .checksum import checksum
from .constants import (
    ApplicationId,
    EnableCommand,
    LightingCommand,
    PointToMultipointDAT,
    TriggerCommand,
)


def _build_pm_command(*payload_bytes: int) -> bytes:
    """Build a point-to-multipoint command with checksum.

    This is the shared low-level builder.  It concatenates the payload
    bytes, computes the two's-complement checksum, and appends it.

    The caller is responsible for hex-encoding the result and wrapping it
    with ``\\`` prefix and ``\\r`` suffix before writing to the transport.

    Args:
        *payload_bytes: Individual byte values (0-255) forming the
            command payload *without* the checksum.

    Returns:
        The complete command bytes including the trailing checksum.
    """
    raw = bytes(payload_bytes)
    cs = checksum(raw)
    return raw + bytes([cs])


def lighting_on(group: int, network: int = 0) -> bytes:
    """Build a Lighting ON command (group → 0xFF).

    Immediately sets the target group to full brightness (level 0xFF).

    Args:
        group:   Target group address (0-255).
        network: C-Bus network number (default 0 = the connected network).

    Returns:
        7-byte command: DAT + app + net + ON + group + 0xFF + checksum.
    """
    return _build_pm_command(
        PointToMultipointDAT.BROADCAST,
        ApplicationId.LIGHTING,
        network,
        LightingCommand.ON,
        group,
        0xFF,
    )


def lighting_off(group: int, network: int = 0) -> bytes:
    """Build a Lighting OFF command (group → 0x00).

    Immediately sets the target group to zero (off).  Unlike a ramp-to-zero,
    this is instantaneous with no fade.

    Args:
        group:   Target group address (0-255).
        network: C-Bus network number (default 0).

    Returns:
        6-byte command: DAT + app + net + OFF + group + checksum.
        (OFF does not include a level byte.)
    """
    return _build_pm_command(
        PointToMultipointDAT.BROADCAST,
        ApplicationId.LIGHTING,
        network,
        LightingCommand.OFF,
        group,
    )


def lighting_ramp(
    group: int,
    level: int,
    rate: LightingCommand = LightingCommand.RAMP_INSTANT,
    network: int = 0,
) -> bytes:
    """Build a Lighting RAMP command (group → level at rate).

    Fades the target group to *level* (0-255) over the duration encoded
    in *rate*.  Use :data:`pycbus.constants.RAMP_DURATIONS` to find the
    closest ramp opcode for an arbitrary duration in seconds.

    Args:
        group:   Target group address (0-255).
        level:   Target brightness (0x00 = off, 0xFF = full).
        rate:    Ramp-rate opcode (default: RAMP_INSTANT = 0s fade).
        network: C-Bus network number (default 0).

    Returns:
        7-byte command: DAT + app + net + RAMP_* + group + level + checksum.
    """
    return _build_pm_command(
        PointToMultipointDAT.BROADCAST,
        ApplicationId.LIGHTING,
        network,
        rate,
        group,
        level & 0xFF,
    )


def lighting_terminate_ramp(group: int, network: int = 0) -> bytes:
    """Build a TERMINATE RAMP command for a group.

    Stops any running fade and holds the group at its current level.
    Useful for implementing a "stop" button during long fades.

    Args:
        group:   Target group address (0-255).
        network: C-Bus network number (default 0).

    Returns:
        6-byte command: DAT + app + net + TERMINATE_RAMP + group + checksum.
    """
    return _build_pm_command(
        PointToMultipointDAT.BROADCAST,
        ApplicationId.LIGHTING,
        network,
        LightingCommand.TERMINATE_RAMP,
        group,
    )


# ------------------------------------------------------------------
# Enable Control (app 203 / 0xCB)
# ------------------------------------------------------------------


def enable_on(group: int, network: int = 0) -> bytes:
    """Build an Enable ON command (group -> 0xFF).

    Immediately enables the target group.

    Args:
        group:   Target group address (0-255).
        network: C-Bus network number (default 0).

    Returns:
        7-byte command: DAT + app + net + ON + group + 0xFF + checksum.
    """
    return _build_pm_command(
        PointToMultipointDAT.BROADCAST,
        ApplicationId.ENABLE,
        network,
        EnableCommand.ON,
        group,
        0xFF,
    )


def enable_off(group: int, network: int = 0) -> bytes:
    """Build an Enable OFF command (group -> 0x00).

    Immediately disables the target group.

    Args:
        group:   Target group address (0-255).
        network: C-Bus network number (default 0).

    Returns:
        6-byte command: DAT + app + net + OFF + group + checksum.
    """
    return _build_pm_command(
        PointToMultipointDAT.BROADCAST,
        ApplicationId.ENABLE,
        network,
        EnableCommand.OFF,
        group,
    )


# ------------------------------------------------------------------
# Trigger Control (app 202 / 0xCA)
# ------------------------------------------------------------------


def trigger_event(group: int, action: int = 0, network: int = 0) -> bytes:
    """Build a Trigger event command.

    Fires a trigger on the specified group with the given action selector.

    Args:
        group:   Target trigger group (0-255).
        action:  Action selector byte (0-255, default 0).
        network: C-Bus network number (default 0).

    Returns:
        7-byte command: DAT + app + net + opcode + group + action + checksum.
    """
    return _build_pm_command(
        PointToMultipointDAT.BROADCAST,
        ApplicationId.TRIGGER,
        network,
        TriggerCommand.TRIGGER_MIN,
        group,
        action & 0xFF,
    )
