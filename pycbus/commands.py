"""SAL command builders and status-request builders for C-Bus.

This module constructs the raw byte sequences for *Short Application Layer*
(SAL) commands that are sent to the C-Bus PCI/CNI.  Each builder returns
the complete payload **including** the trailing checksum byte, ready to be
hex-encoded and framed for transmission.

It also provides a **status request** builder for querying the current
level of all group addresses in a given application.  The PCI responds
with a binary (or extended-binary) status reply — see
:func:`parse_status_reply` for decoding.

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

Status request (short form, point-to-multipoint)::

    Byte 0:  0xFF     — short-form PM header
    Byte 1:  <app>    — Application ID
    Byte 2:  0x73     — binary status request opcode
    Byte 3:  0x00     — block number (0, 1, or 2)
    Byte 4:  <chk>    — checksum

References:
    - *C-Bus Serial Interface User Guide*, §4.3.3 — Point-to-Multipoint
    - *C-Bus Serial Interface User Guide*, §4.3.3.2 — Status Requests
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

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from .checksum import checksum
from .constants import (
    ApplicationId,
    EnableCommand,
    LightingCommand,
    PointToMultipointDAT,
    TriggerCommand,
)

_LOGGER = logging.getLogger(__name__)


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


# ------------------------------------------------------------------
# Status Requests — query current group levels
# ------------------------------------------------------------------

# Binary status request opcode ($7A) — reports ON/OFF/ERROR per group.
_BINARY_STATUS_OPCODE = 0x7A

# Status requests are SAL commands sent to the STATUS_REQUEST
# pseudo-application (0xFF).  The PCI replies with 3+ CAL reply lines
# covering all 256 groups.  One request is sufficient.
#
# Reference: C-Bus Serial Interface User Guide, s4.3.3.2


def status_request(app_id: int) -> bytes:
    """Build a binary status request for an application.

    Sends a point-to-multipoint SAL command to the STATUS_REQUEST
    pseudo-application (``0xFF``).  The PCI responds with multiple
    CAL reply lines covering all 256 group addresses.

    Wire format (example for Lighting app 0x38)::

        \\05FF007A38004A\\r

    Byte layout::

        05   — DAT (broadcast, point-to-multipoint)
        FF   — Application = STATUS_REQUEST pseudo-app
        00   — Network (default)
        7A   — Binary status request opcode
        <app> — Target application to query
        00   — Starting group address (0 = all groups)
        <chk> — Checksum

    Reference: C-Bus Serial Interface User Guide, page 22-23.

    Args:
        app_id: Application ID to query (e.g. ``ApplicationId.LIGHTING``).

    Returns:
        7-byte command: DAT + 0xFF + net + 0x7A + app + 0x00 + checksum.
    """
    return _build_pm_command(
        PointToMultipointDAT.BROADCAST,
        0xFF,  # STATUS_REQUEST pseudo-application
        0x00,  # network
        _BINARY_STATUS_OPCODE,
        app_id,
        0x00,  # starting group address
    )


# ------------------------------------------------------------------
# Status Reply Parsing
# ------------------------------------------------------------------

# Long-form CAL reply header byte.
# In SMART + EXSTAT mode, the PCI wraps status replies in a
# point-to-point long-form frame:
#   86 <unit_addr> <SI_addr> 00 <CAL_data...> <outer_checksum>
# Reference: C-Bus Serial Interface User Guide, s4.3.3.1.
_LONG_FORM_HEADER = 0x86


def is_status_reply(data: bytes) -> bool:
    """Return True if *data* looks like a CAL status reply.

    Handles both short-form (CAL header as first byte) and long-form
    (``0x86`` wrapper with CAL header at offset 4).
    """
    if len(data) < 4:
        return False
    # Long-form: 86 <addr> <addr> 00 <CAL header...>
    if data[0] == _LONG_FORM_HEADER:
        return len(data) >= 8 and (data[4] & 0xC0) == 0xC0
    # Short-form: CAL header directly.
    return (data[0] & 0xC0) == 0xC0


def parse_status_reply(
    data: bytes,
) -> tuple[int, dict[int, int]]:
    """Parse a binary status reply into (app_id, {group: state}).

    Accepts both **short-form** and **long-form** CAL reply data
    (the ``data`` should include the checksum as the last byte,
    already verified by the caller).

    **Short-form** (BASIC mode or non-IDMON)::

        [C0|cnt] [app] [block_start] [data...] [checksum]
        [E0|cnt] [coding] [app] [block_start] [data...] [checksum]

    **Long-form** (SMART + EXSTAT)::

        86 <addr> <addr> 00 [E0|cnt] [coding] [app] [block] [data...] [chk]

    The extended format coding byte indicates the data type:
        - 0x00 / 0x40 = binary (2-bit per group)
        - 0x07 / 0x47 = level (nibble-pair, not yet implemented)

    Binary 2-bit encoding per group (LSB first in each byte):
        - 00 = does not exist (skipped)
        - 01 = ON  (mapped to level 255)
        - 10 = OFF (mapped to level 0)
        - 11 = ERROR (skipped)

    Reference: C-Bus Serial Interface User Guide, s7.3-7.4.

    Args:
        data: Raw decoded bytes of the status reply (with checksum
              as the last byte, already verified).

    Returns:
        Tuple of (app_id, group_levels) where group_levels maps
        absolute group address to level (0 or 255 for binary).
        Returns (0, {}) if the data cannot be parsed.
    """
    if len(data) < 4:
        return 0, {}

    # Strip long-form PP2P header if present.
    if data[0] == _LONG_FORM_HEADER:
        if len(data) < 8:
            return 0, {}
        # Inner CAL = data[4:-1] (skip header + outer checksum).
        cal = data[4:-1]
    elif (data[0] & 0xC0) == 0xC0:
        # Short-form: strip trailing checksum only.
        cal = data[:-1]
    else:
        return 0, {}

    if len(cal) < 3:
        return 0, {}

    header = cal[0]

    if (header & 0xE0) == 0xE0:
        # Extended: [E0|cnt] [coding] [app] [block_start] [data...]
        if len(cal) < 4:
            return 0, {}
        coding = cal[1]
        app_id = cal[2]
        block_start = cal[3]
        payload = cal[4:]

        if coding in (0x07, 0x47):
            _LOGGER.debug(
                "Level status reply (coding=0x%02X) not supported",
                coding,
            )
            return app_id, {}

        # Binary status (coding 0x00, 0x40, or others).
        levels = _parse_binary_status(payload, block_start)
        return app_id, levels

    if (header & 0xE0) == 0xC0:
        # Standard: [C0|cnt] [app] [block_start] [data...]
        app_id = cal[1]
        block_start = cal[2]
        payload = cal[3:]
        levels = _parse_binary_status(payload, block_start)
        return app_id, levels

    return 0, {}


def _parse_binary_status(payload: bytes, block_start: int) -> dict[int, int]:
    """Parse binary 2-bit-per-group status data.

    Each byte encodes 4 groups (2 bits each), from LSB to MSB:
        bits [1:0] = group N
        bits [3:2] = group N+1
        bits [5:4] = group N+2
        bits [7:6] = group N+3

    Code: 00=missing, 01=ON(255), 10=OFF(0), 11=ERROR(skip).

    Reference: C-Bus Serial Interface User Guide, s7.3 page 45-46.
    """
    levels: dict[int, int] = {}
    group = block_start
    for byte_val in payload:
        for shift in (0, 2, 4, 6):
            state = (byte_val >> shift) & 0x03
            if state == 0x01:  # ON
                levels[group] = 255
            elif state == 0x02:  # OFF
                levels[group] = 0
            # 0x00 = missing, 0x03 = error — skip both
            group += 1
            if group >= 256:
                break
    return levels


# ------------------------------------------------------------------
# SAL Monitor Event Parsing
# ------------------------------------------------------------------
#
# When the PCI is in MONITOR mode, it emits point-to-multipoint SAL
# events for every command on the bus.  The format (after hex-decode
# and checksum verification) is:
#
#     data[0]    DAT byte (0x05 = broadcast)
#     data[1]    source unit address (who sent the command)
#     data[2]    application ID (0x38 = lighting, 0xCA = trigger, ...)
#     data[3]    routing byte (usually 0x00)
#     data[4:-1] SAL command data (one or more commands)
#     data[-1]   checksum
#
# A single event may contain **multiple** SAL commands (e.g., a scene
# recall from a PACA controller ramps several groups in one packet).
# Command sizes vary by application and opcode — this is based on the
# micolous/libcbus reference implementation and C-Bus specification.
#
# References:
#     - micolous/cbus: protocol/application/lighting.py — decode_sals()
#     - *Chapter 02 — C-Bus Lighting Application*, §2.6
#     - *Chapter 07 — Trigger Control Application*
#     - *Chapter 08 — Enable Control Application*


@dataclass(frozen=True, slots=True)
class SalCommand:
    """A single SAL command parsed from a monitor event.

    Attributes:
        opcode: Raw SAL opcode byte.
        group:  Target group address (0-255) — a physical lighting circuit.
        data:   Optional data byte (level for ramp, action for trigger).
                ``None`` for commands that carry no extra byte (OFF,
                ON, TERMINATE_RAMP, Enable OFF).
    """

    opcode: int
    group: int
    data: int | None = None


@dataclass(frozen=True, slots=True)
class SalEvent:
    """A fully parsed SAL monitor event from the PCI.

    Represents a single point-to-multipoint SAL packet received in
    MONITOR mode.  May contain multiple :class:`SalCommand` entries
    (e.g., a PACA scene recall that ramps several circuits at once).

    Attributes:
        source:   Source unit address on the C-Bus network (0-255).
        app_id:   Application ID (e.g. 0x38 = Lighting).
        routing:  Routing byte (usually 0x00 for the local network).
        commands: Tuple of parsed SAL commands, in wire order.
    """

    source: int
    app_id: int
    routing: int
    commands: tuple[SalCommand, ...]


# -- Application-specific command size functions --
#
# Each function takes an opcode and returns the total number of bytes
# that SAL command consumes (including the opcode byte itself).
# Modelled after micolous/cbus _SAL_HANDLERS approach.


def _lighting_sal_size(opcode: int) -> int:
    """Size of a lighting SAL command.

    Ramp opcodes (low 3 bits == 0b010) consume 3 bytes: opcode + group
    + level.  All other opcodes (ON, OFF, TERMINATE_RAMP) consume 2
    bytes: opcode + group.

    Reference: micolous/cbus common.py LIGHT_RAMP_COMMANDS set.
    """
    if opcode & 0x07 == 0x02:
        return 3  # ramp: opcode + group + level
    return 2  # ON / OFF / TERMINATE_RAMP: opcode + group


def _trigger_sal_size(_opcode: int) -> int:
    """Trigger commands are always 3 bytes: opcode + group + action."""
    return 3


def _enable_sal_size(_opcode: int) -> int:
    """Enable commands are always 2 bytes: opcode + group."""
    return 2


# Registry mapping application IDs to their SAL size function.
# Unknown applications fall back to the lighting pattern (most common).
_APP_SAL_SIZE: dict[int, Callable[[int], int]] = {
    ApplicationId.LIGHTING: _lighting_sal_size,
    ApplicationId.TRIGGER: _trigger_sal_size,
    ApplicationId.ENABLE: _enable_sal_size,
}


def _get_sal_command_size(app_id: int, opcode: int) -> int:
    """Determine the byte count for a SAL command in a given application.

    Falls back to the lighting pattern for unknown applications, which
    is safe because the ramp-detection heuristic (low 3 bits == 0b010)
    is used across most C-Bus applications that support dimming.
    """
    size_fn = _APP_SAL_SIZE.get(app_id, _lighting_sal_size)
    return size_fn(opcode)


def parse_sal_event(data: bytes) -> SalEvent | None:
    """Parse a hex-decoded SAL monitor event into a :class:`SalEvent`.

    The input should be the raw decoded bytes from a point-to-multipoint
    SAL monitor event.  The checksum must already be verified by the
    protocol layer.

    Expected format::

        data[0]    = DAT (0x05)
        data[1]    = source address
        data[2]    = application ID
        data[3]    = routing (0x00)
        data[4:-1] = SAL command data
        data[-1]   = checksum

    Returns ``None`` if the data is too short or contains no parseable
    commands.  Partial results are returned if a multi-command packet
    is truncated — the successfully parsed prefix is kept.

    Args:
        data: Raw decoded bytes of the SAL event.

    Returns:
        Parsed :class:`SalEvent`, or ``None`` on failure.
    """
    # Minimum: DAT + source + app + routing + 1 opcode + 1 group + checksum = 7
    if len(data) < 7:
        _LOGGER.debug(
            "SAL event too short (%d bytes): %s", len(data), data.hex().upper()
        )
        return None

    source = data[1]
    app_id = data[2]
    routing = data[3]
    sal_data = data[4:-1]  # strip header (4 bytes) and checksum (1 byte)

    _LOGGER.debug(
        "Parsing SAL: source=%d app=0x%02X routing=0x%02X sal_bytes=%s",
        source,
        app_id,
        routing,
        sal_data.hex().upper(),
    )

    commands: list[SalCommand] = []
    pos = 0

    while pos < len(sal_data):
        opcode = sal_data[pos]
        size = _get_sal_command_size(app_id, opcode)

        if pos + size > len(sal_data):
            _LOGGER.warning(
                "SAL truncated at offset %d: need %d bytes, %d remain "
                "(app=0x%02X opcode=0x%02X raw=%s)",
                pos,
                size,
                len(sal_data) - pos,
                app_id,
                opcode,
                sal_data.hex().upper(),
            )
            break

        group = sal_data[pos + 1] if pos + 1 < len(sal_data) else 0
        cmd_data = sal_data[pos + 2] if size == 3 else None
        commands.append(SalCommand(opcode=opcode, group=group, data=cmd_data))

        _LOGGER.debug(
            "  command: opcode=0x%02X group=%d%s",
            opcode,
            group,
            f" data={cmd_data}" if cmd_data is not None else "",
        )

        pos += size

    if not commands:
        _LOGGER.debug("No SAL commands parsed from: %s", data.hex().upper())
        return None

    event = SalEvent(
        source=source,
        app_id=app_id,
        routing=routing,
        commands=tuple(commands),
    )

    _LOGGER.debug(
        "Parsed SAL event: source=%d app=0x%02X commands=%d",
        source,
        app_id,
        len(commands),
    )

    return event
