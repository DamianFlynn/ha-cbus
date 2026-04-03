"""C-Bus protocol constants and enumerations.

This module defines every protocol-level constant needed to build and parse
C-Bus serial frames.  Values are taken directly from the Schneider Electric
reference documents:

- *C-Bus Serial Interface User Guide*  — framing, checksum, interface options
- *Chapter 00 — C-Bus Applications Intro*  — application ID allocation table
- *Chapter 02 — Lighting*  — SAL opcodes and ramp-rate encoding
- *Chapter 07 — Trigger Control*  — trigger group/action model
- *Chapter 08 — Enable Control*  — binary enable/disable model

Note on application IDs:
    C-Bus reserves IDs 0-255.  Each application gets a unique ID that appears
    as the second byte of every point-to-multipoint SAL command.  The full
    allocation table is in *Chapter 00*, Table 2.

Usage::

    >>> from pycbus.constants import ApplicationId, LightingCommand
    >>> hex(ApplicationId.LIGHTING)
    '0x38'
    >>> LightingCommand.ON
    <LightingCommand.ON: 121>
"""

from __future__ import annotations

from enum import IntEnum


class ApplicationId(IntEnum):
    """Well-known C-Bus application identifiers.

    Each value is the 8-bit application ID that appears in SAL headers.
    Mapped from *Chapter 00 — C-Bus Applications Intro*, Table 2.

    Phase 1 (MVP): LIGHTING, TRIGGER, ENABLE
    Phase 2+: SECURITY, TELEPHONY, and application-specific chapters.
    """

    LIGHTING = 56  # 0x38 — Chapter 02
    TRIGGER = 202  # 0xCA — Chapter 07
    ENABLE = 203  # 0xCB — Chapter 08
    SECURITY = 208  # 0xD0 — Chapter 05
    METERING = 228  # 0xE4 — Chapter 06
    TEMPERATURE_BROADCAST = 25  # 0x19 — Chapter 09
    VENTILATION = 112  # 0x70 — Chapter 10
    ACCESS_CONTROL = 209  # 0xD1 — Chapter 11
    MEDIA_TRANSPORT = 199  # 0xC7 — Chapter 21
    CLOCK = 223  # 0xDF — Chapter 23
    TELEPHONY = 224  # 0xE0 — Chapter 24
    AIR_CONDITIONING = 172  # 0xAC — Chapter 25
    IRRIGATION = 203  # 0xCB — Chapter 26 (shares enable block)
    MEASUREMENT = 232  # 0xE8 — Chapter 28
    POOLS_SPAS = 200  # 0xC8 — Chapter 31
    ERROR_REPORTING = 206  # 0xCE — Chapter 34
    HVAC_ACTUATOR = 105  # 0x69 — Chapter 36
    HEATING_LEGACY = 136  # 0x88 — from HOME.xml (pre-standard)


class PointToMultipointDAT(IntEnum):
    """Data Address Type (DAT) byte for point-to-multipoint commands.

    The DAT is the first byte of every point-to-multipoint SAL frame.
    It tells the PCI how to interpret the rest of the command:

    - ``0x05`` (BROADCAST): the command targets *all* units listening on
      the specified application.  This is by far the most common mode
      because C-Bus groups are inherently multicast.

    Reference: *C-Bus Serial Interface User Guide*, §4.3.3.
    """

    BROADCAST = 0x05


class LightingCommand(IntEnum):
    """SAL opcodes for the Lighting application (app 56 / 0x38).

    Each opcode encodes *both* the action and (for ramp commands) the
    transition duration.  The ramp time is baked into the opcode itself
    — there is no separate duration field.

    Frame structure for a ramp command::

        05 38 00 <opcode> <group> <level> <checksum>
              ^^           ^^^^^^
              app 56       target group address (0-255)

    - ``OFF``  (0x01): sets the group to 0x00 immediately.
    - ``ON``   (0x79): sets the group to 0xFF immediately.
    - ``RAMP_*``:       fades to <level> over the encoded duration.
    - ``TERMINATE_RAMP`` (0x09): halts any running fade at current level.

    Reference: *Chapter 02 — C-Bus Lighting Application*, Table 2-2.
    """

    OFF = 0x01
    RAMP_INSTANT = 0x02
    RAMP_4S = 0x0A
    RAMP_8S = 0x12
    RAMP_12S = 0x1A
    RAMP_20S = 0x22
    RAMP_30S = 0x2A
    RAMP_40S = 0x32
    RAMP_60S = 0x3A
    RAMP_90S = 0x42
    RAMP_120S = 0x4A
    RAMP_180S = 0x52
    RAMP_300S = 0x5A
    RAMP_420S = 0x62
    RAMP_600S = 0x6A
    RAMP_900S = 0x72
    RAMP_1020S = 0x7A
    ON = 0x79
    TERMINATE_RAMP = 0x09


# Sorted (seconds, opcode) tuples for picking the closest ramp rate.
#
# When a caller requests "fade over N seconds", we binary-search this list
# to find the opcode whose built-in duration is closest to N.  The list is
# pre-sorted by ascending duration for efficient lookup.
RAMP_DURATIONS: list[tuple[int, LightingCommand]] = sorted(
    [
        (0, LightingCommand.RAMP_INSTANT),
        (4, LightingCommand.RAMP_4S),
        (8, LightingCommand.RAMP_8S),
        (12, LightingCommand.RAMP_12S),
        (20, LightingCommand.RAMP_20S),
        (30, LightingCommand.RAMP_30S),
        (40, LightingCommand.RAMP_40S),
        (60, LightingCommand.RAMP_60S),
        (90, LightingCommand.RAMP_90S),
        (120, LightingCommand.RAMP_120S),
        (180, LightingCommand.RAMP_180S),
        (300, LightingCommand.RAMP_300S),
        (420, LightingCommand.RAMP_420S),
        (600, LightingCommand.RAMP_600S),
        (900, LightingCommand.RAMP_900S),
        (1020, LightingCommand.RAMP_1020S),
    ],
    key=lambda x: x[0],
)


class ConfirmationCode(IntEnum):
    """PCI confirmation / status codes returned after each command.

    After sending a command, the PCI responds with a single ASCII character:

    - ``g``  (0x67) — POSITIVE: command accepted and forwarded to the bus.
    - ``!``  (0x21) — NEGATIVE: checksum error, malformed, or bus fault.
    - ``#``  (0x23) — READY: the PCI is idle and ready for the next command.
    - ``.``  (0x2E) — BUSY: the PCI is processing; wait and retry.

    The protocol state machine uses these to decide whether to advance,
    retry, or flag an error.

    Reference: *C-Bus Serial Interface User Guide*, §4.4.
    """

    POSITIVE = ord("g")  # 0x67 — command accepted
    NEGATIVE = ord("!")  # 0x21 — checksum error or malformed
    READY = ord("#")  # 0x23 — ready for next command
    BUSY = ord(".")  # 0x2E — wait and retry


class InterfaceOption1(IntEnum):
    """Bitmask values for Interface Options #1 (parameter 0x30).

    Written via ``@A3300xx`` where ``xx`` is the hex-encoded option byte.
    Our init sequence sets: CONNECT | SRCHK | SMART | MONITOR = 0x59.

    Flags:
        CONNECT  — maintain a connection to the C-Bus network.
        SRCHK    — enable source-address checking on replies.
        SMART    — enable "smart mode" (structured replies, not raw echo).
        MONITOR  — receive all SAL traffic on the network as monitor events.
        IDMON    — include source unit address in monitor packets.

    Reference: *C-Bus Serial Interface User Guide*, §7.2 Table 7-1.
    """

    CONNECT = 0x01
    SRCHK = 0x08
    SMART = 0x10
    MONITOR = 0x40
    IDMON = 0x01  # bit within the high nibble


class InterfaceOption3(IntEnum):
    """Bitmask values for Interface Options #3 (parameter 0x42).

    Written via ``@A34200xx`` where ``xx`` is the hex-encoded option byte.
    Our init sequence sets: LOCAL_SAL | EXSTAT = 0x0A.

    Flags:
        LOCAL_SAL — echo locally-generated SAL back to the host.
        PUN       — power-up notification on boot.
        EXSTAT    — extended status replies (two bytes per group address
                    instead of one, giving 0-255 resolution).

    Reference: *C-Bus Serial Interface User Guide*, §7.2 Table 7-3.
    """

    LOCAL_SAL = 0x02
    PUN = 0x04
    EXSTAT = 0x08


# Default serial parameters.
SERIAL_BAUD = 9600
SERIAL_BYTESIZE = 8
SERIAL_PARITY = "N"
SERIAL_STOPBITS = 1

# Default TCP port for CNI.
TCP_PORT = 10001
