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

    LIGHTING = 0x38  # 56 — Chapter 02
    TRIGGER = 0xCA  # 202 — Chapter 07
    ENABLE = 0xCB  # 203 — Chapter 08
    SECURITY = 0xD0  # 208 — Chapter 05
    METERING = 0xD1  # 209 — Chapter 06
    TEMPERATURE_BROADCAST = 0x19  # 25 — Chapter 09
    VENTILATION = 0x70  # 112 — Chapter 10
    ACCESS_CONTROL = 0xD5  # 213 — Chapter 11
    MEDIA_TRANSPORT = 0xC0  # 192 — Chapter 21
    CLOCK = 0xDF  # 223 — Chapter 23
    TELEPHONY = 0xE0  # 224 — Chapter 24
    AIR_CONDITIONING = 0xAC  # 172 — Chapter 25
    IRRIGATION = 0x71  # 113 — Chapter 26
    MEASUREMENT = 0xE4  # 228 — Chapter 28
    POOLS_SPAS = 0x72  # 114 — Chapter 31
    ERROR_REPORTING = 0xCE  # 206 — Chapter 34
    HVAC_ACTUATOR = 0x73  # 115 — Chapter 36
    HEATING_LEGACY = 0x88  # 136 — from HOME.xml (pre-standard)


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


class EnableCommand(IntEnum):
    """SAL opcodes for the Enable Control application (app 203 / 0xCB).

    Enable Control is a simple binary on/off application with no dimming.
    Only two opcodes are used:

    - ``OFF`` (0x01): Disable the group.
    - ``ON``  (0x79): Enable the group.

    Frame structure::

        05 CB 00 <opcode> <group> [FF] <checksum>

    Reference: *Chapter 08 -- Enable Control Application*.
    """

    OFF = 0x01
    ON = 0x79


class TriggerCommand(IntEnum):
    """SAL opcodes for the Trigger Control application (app 202 / 0xCA).

    Trigger groups are fire-and-forget: they carry a group address and an
    action selector byte (0-255) but have no persistent level state.

    - ``TRIGGER_MIN`` (0x02): Trigger with action selector = 0x00.
    - ``TRIGGER_MAX`` (0x79): Trigger with action selector = 0xFF.

    For arbitrary action selectors, use ``TRIGGER_MIN`` with an explicit
    action byte.

    Frame structure::

        05 CA 00 <opcode> <group> <action> <checksum>

    Reference: *Chapter 07 -- Trigger Control Application*.
    """

    TRIGGER_MIN = 0x02
    TRIGGER_MAX = 0x79


class MeasurementCommand(IntEnum):
    """SAL command codes for the Measurement application (app 0xE4).

    The command byte encodes both the command code (bits 4-7) and
    the argument count (bits 0-2).  Only one command is defined.

    Reference: *Chapter 28 — C-Bus Measurement Application*, §28.4.
    """

    MEASUREMENT_EVENT = 0x0E  # %0 0001 110 — 6 argument bytes


class MeasurementUnit(IntEnum):
    """Unit codes for Measurement Application data.

    Each code identifies the physical quantity being measured.

    Reference: *Chapter 28 — C-Bus Measurement Application*, §28.5.1.2.
    """

    CELSIUS = 0x00
    AMPS = 0x01
    ANGLE_DEGREES = 0x02
    COULOMB = 0x03
    BOOLEAN = 0x04
    FARADS = 0x05
    HENRYS = 0x06
    HERTZ = 0x07
    JOULES = 0x08
    KATAL = 0x09
    KG_PER_M3 = 0x0A
    KILOGRAMS = 0x0B
    LITRES = 0x0C
    LITRES_PER_HOUR = 0x0D
    LITRES_PER_MINUTE = 0x0E
    LITRES_PER_SECOND = 0x0F
    LUX = 0x10
    METRES = 0x11
    METRES_PER_MINUTE = 0x12
    METRES_PER_SECOND = 0x13
    METRES_PER_SECOND2 = 0x14
    MOLE = 0x15
    NEWTON_METRE = 0x16
    NEWTONS = 0x17
    OHMS = 0x18
    PASCAL = 0x19
    PERCENT = 0x1A
    DECIBELS = 0x1B
    PPM = 0x1C
    RPM = 0x1D
    SECONDS = 0x1E
    MINUTES = 0x1F
    HOURS = 0x20
    SIEVERTS = 0x21
    STERADIAN = 0x22
    TESLA = 0x23
    VOLTS = 0x24
    WATT_HOURS = 0x25
    WATTS = 0x26
    WEBERS = 0x27
    NO_UNITS = 0xFE
    CUSTOM = 0xFF


# Human-readable labels for measurement units.
MEASUREMENT_UNIT_LABELS: dict[int, str] = {
    MeasurementUnit.CELSIUS: "°C",
    MeasurementUnit.AMPS: "A",
    MeasurementUnit.ANGLE_DEGREES: "°",
    MeasurementUnit.HERTZ: "Hz",
    MeasurementUnit.JOULES: "J",
    MeasurementUnit.KG_PER_M3: "kg/m³",
    MeasurementUnit.KILOGRAMS: "kg",
    MeasurementUnit.LITRES: "L",
    MeasurementUnit.LITRES_PER_HOUR: "L/h",
    MeasurementUnit.LITRES_PER_MINUTE: "L/min",
    MeasurementUnit.LITRES_PER_SECOND: "L/s",
    MeasurementUnit.LUX: "lx",
    MeasurementUnit.METRES: "m",
    MeasurementUnit.METRES_PER_MINUTE: "m/min",
    MeasurementUnit.METRES_PER_SECOND: "m/s",
    MeasurementUnit.METRES_PER_SECOND2: "m/s²",
    MeasurementUnit.NEWTONS: "N",
    MeasurementUnit.NEWTON_METRE: "N·m",
    MeasurementUnit.OHMS: "Ω",
    MeasurementUnit.PASCAL: "Pa",
    MeasurementUnit.PERCENT: "%",
    MeasurementUnit.DECIBELS: "dB",
    MeasurementUnit.PPM: "ppm",
    MeasurementUnit.RPM: "rpm",
    MeasurementUnit.SECONDS: "s",
    MeasurementUnit.MINUTES: "min",
    MeasurementUnit.HOURS: "h",
    MeasurementUnit.TESLA: "T",
    MeasurementUnit.VOLTS: "V",
    MeasurementUnit.WATT_HOURS: "Wh",
    MeasurementUnit.WATTS: "W",
    MeasurementUnit.WEBERS: "Wb",
    MeasurementUnit.NO_UNITS: "",
    MeasurementUnit.CUSTOM: "custom",
}


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
    Our init sequence sets:
    CONNECT | SRCHK | SMART | MONITOR | IDMON = 0x79.

    Flags:
        CONNECT  — maintain a connection to the C-Bus network.
        SRCHK    — enable source-address checking on replies.
        SMART    — enable "smart mode" (structured replies, not raw echo).
        MONITOR  — relay all Status Reports for matched applications (bit 5).
        IDMON    — long-form CAL replies for self-initiated commands (bit 6).

    Reference: *C-Bus Serial Interface User Guide*, §10, Table p58.
    """

    CONNECT = 0x01
    SRCHK = 0x08
    SMART = 0x10
    MONITOR = 0x20
    IDMON = 0x40


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
