"""C-Bus protocol constants and enumerations."""

from __future__ import annotations

from enum import IntEnum


class ApplicationId(IntEnum):
    """Well-known C-Bus application identifiers."""

    LIGHTING = 56  # 0x38
    TRIGGER = 202  # 0xCA
    ENABLE = 203  # 0xCB
    SECURITY = 208  # 0xD0
    TELEPHONY = 224  # 0xE0  (from HOME.xml)
    HEATING_LEGACY = 136  # 0x88 (from HOME.xml)
    # Additional app IDs will be added as chapters are reviewed.


class PointToMultipointDAT(IntEnum):
    """Data Address Type for point-to-multipoint commands."""

    BROADCAST = 0x05


class LightingCommand(IntEnum):
    """SAL opcodes for the Lighting application (app 56)."""

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


# Sorted durations for picking the closest ramp rate.
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
    """PCI confirmation / status codes."""

    POSITIVE = ord("g")  # command accepted
    NEGATIVE = ord("!")  # checksum error or malformed
    READY = ord("#")  # ready for next command
    BUSY = ord(".")  # wait and retry


class InterfaceOption1(IntEnum):
    """Bitmask values for Interface Options #1 (parameter 0x30)."""

    CONNECT = 0x01
    SRCHK = 0x08
    SMART = 0x10
    MONITOR = 0x40
    IDMON = 0x01  # bit within the high nibble


class InterfaceOption3(IntEnum):
    """Bitmask values for Interface Options #3 (parameter 0x42)."""

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
