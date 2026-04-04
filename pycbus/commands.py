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

# Number of groups per status block.  With EXSTAT each group gets 2 bytes
# in the reply; block 0 covers groups 0-87, block 1 covers 88-175,
# block 2 covers 176-255.
GROUPS_PER_BLOCK = 88

# Status request opcode (binary status request).
_STATUS_REQUEST_OPCODE = 0x73

# Number of blocks needed to cover all 256 groups.
STATUS_BLOCK_COUNT = 3


def status_request(app_id: int, block: int = 0) -> bytes:
    """Build a binary status request for an application.

    Asks the PCI for the current levels of all groups in the specified
    block.  Three blocks cover all 256 group addresses:

    - Block 0: groups 0-87
    - Block 1: groups 88-175
    - Block 2: groups 176-255

    The PCI will reply with a binary (or extended-binary, if EXSTAT is
    enabled) status reply containing the level for each group.

    Wire format::

        \\FF <app> 73 <block> <checksum> \\r

    Args:
        app_id: Application ID to query (e.g. ``ApplicationId.LIGHTING``).
        block:  Block number (0, 1, or 2).

    Returns:
        5-byte command: 0xFF + app + 0x73 + block + checksum.

    Raises:
        ValueError: If block is not 0, 1, or 2.
    """
    if block not in (0, 1, 2):
        msg = f"Block must be 0, 1, or 2, got {block}"
        raise ValueError(msg)

    return _build_pm_command(0xFF, app_id, _STATUS_REQUEST_OPCODE, block)


# ------------------------------------------------------------------
# Status Reply Parsing
# ------------------------------------------------------------------

# Reply coding bytes — indicate the type of status reply.
# The coding byte appears after the PM header in the response.
_BINARY_STATUS_CODING = 0xC0  # standard binary (1 byte per group)
_EXTENDED_BINARY_CODING = 0xE0  # extended binary (2 bytes per group, EXSTAT)


def parse_status_reply(data: bytes) -> dict[int, int]:
    """Parse a binary status reply into a {group: level} dict.

    The PCI sends status replies as hex-encoded binary data.  After
    hex-decoding and checksum verification (done by the protocol layer),
    the raw bytes have this structure::

        Standard binary (no EXSTAT):
            D8 <app> 00 C0 <levels...> <checksum>
            Each byte in <levels> is the level for one group.
            Bit 7 is stripped (0x00=off, 0x7F=max=255 mapped).

        Extended binary (EXSTAT enabled — our default):
            D8 <app> 00 E0 <levels...> <checksum>
            Pairs of bytes: high-nibble, low-nibble per group.
            Each pair gives 0-255 level.

    This function handles both formats.  It strips the header and
    checksum and returns a dict mapping group addresses to levels.

    The base group address is derived from the block number encoded
    in the reply header.  However, many PCI implementations omit
    the block number from the reply header.  We solve this by accepting
    an opaque bytes blob and returning *relative* group offsets starting
    from 0.  The caller (protocol/coordinator) tracks which block was
    requested and adds the appropriate offset.

    Args:
        data: Raw decoded bytes of the status reply (checksum already
              verified and included).

    Returns:
        Dict mapping relative group offset (0-based) to level (0-255).
        Empty dict if the data cannot be parsed.
    """
    # Minimum: header(3) + coding(1) + at least 1 level + checksum(1) = 6
    if len(data) < 6:
        return {}

    coding = data[3]

    # Strip header (3 bytes) + coding (1 byte) and checksum (last byte).
    payload = data[4:-1]

    if coding & 0xE0 == 0xE0:
        # Extended binary: two bytes per group.
        return _parse_extended_status(payload)
    if coding & 0xC0 == 0xC0:
        # Standard binary: one byte per group, 7-bit levels.
        return _parse_standard_status(payload)

    # Unknown coding — return empty.
    return {}


def _parse_extended_status(payload: bytes) -> dict[int, int]:
    """Parse extended binary status (EXSTAT) payload.

    Each group is represented by 2 bytes.  The first byte is the
    level (0-255), the second byte is padding (0x00).
    """
    levels: dict[int, int] = {}
    for group, i in enumerate(range(0, len(payload) - 1, 2)):
        levels[group] = payload[i]
    return levels


def _parse_standard_status(payload: bytes) -> dict[int, int]:
    """Parse standard binary status payload (no EXSTAT).

    Each byte represents one group.  Level range is 0x00-0xFF
    (the PCI uses the full byte range in standard mode too,
    despite the docs suggesting 7-bit — real PCIs send 0-255).
    """
    return dict(enumerate(payload))


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
_APP_SAL_SIZE = {
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
