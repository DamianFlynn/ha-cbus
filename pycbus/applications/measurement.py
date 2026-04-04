"""Measurement application (app 0xE4) — Chapter 28.

Parses broadcast measurement events from sensors (light level, temperature,
etc.).  Measurement devices cannot be polled — they broadcast periodically
or on value change.

Wire format for MEASUREMENT_EVENT::

    0x0E  <device_id> <channel> <units> <multiplier> <msb> <lsb>

The 16-bit value (msb, lsb) is signed two's complement.
The multiplier is a signed byte (power of ten).
Actual measurement = raw_value x 10^multiplier in the given units.

Reference: *Chapter 28 — C-Bus Measurement Application*.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..constants import MEASUREMENT_UNIT_LABELS, MeasurementCommand

_LOGGER = logging.getLogger(__name__)


def sal_size(opcode: int) -> int:
    """Measurement commands: command byte encodes the argument count.

    The low 3 bits of the command byte give the number of argument
    bytes following the command.  For MEASUREMENT_EVENT (0x0E) this
    is 6, giving a total of 7 bytes (command + 6 args).

    Reference: *Chapter 28 — Measurement Application*, s28.4.
    """
    arg_count = opcode & 0x07
    return 1 + arg_count  # command byte + arguments


@dataclass(frozen=True, slots=True)
class MeasurementData:
    """Decoded Measurement Application event.

    The SNEL light-level sensor (and similar devices) broadcast
    measurement data on app ``0xE4``.  The value is computed as::

        value = raw_value x 10^multiplier

    in the unit identified by :attr:`unit_code`.

    Attributes:
        device_id:  Source measurement device ID (0-255).
        channel:    Input channel number on the device.
        unit_code:  Physical unit code (e.g. 0x10 = Lux).
        multiplier: Signed power-of-ten exponent.
        raw_value:  Signed 16-bit measurement value before scaling.
    """

    device_id: int
    channel: int
    unit_code: int
    multiplier: int
    raw_value: int

    @property
    def value(self) -> float:
        """Scaled measurement value (``raw_value x 10^multiplier``)."""
        return self.raw_value * (10.0 ** self.multiplier)

    @property
    def unit_label(self) -> str:
        """Human-readable unit string (e.g. ``'lx'``, ``'°C'``)."""
        return MEASUREMENT_UNIT_LABELS.get(
            self.unit_code, f"unit_0x{self.unit_code:02X}"
        )


def parse_measurement_data(sal_data: bytes) -> list[MeasurementData]:
    """Parse measurement readings from raw SAL command bytes.

    This operates on the SAL command portion of a point-to-multipoint
    packet (after stripping the 4-byte header and 1-byte checksum).

    Concatenated commands are supported per s28.8.1.

    Args:
        sal_data: Raw SAL command bytes (excluding PM header and checksum).

    Returns:
        List of decoded :class:`MeasurementData` readings.
    """
    results: list[MeasurementData] = []
    pos = 0

    while pos < len(sal_data):
        opcode = sal_data[pos]
        arg_count = opcode & 0x07

        if pos + 1 + arg_count > len(sal_data):
            _LOGGER.debug(
                "Measurement: truncated at offset %d (need %d bytes, %d remain)",
                pos,
                1 + arg_count,
                len(sal_data) - pos,
            )
            break

        command_code = (opcode >> 3) & 0x0F

        expected = MeasurementCommand.MEASUREMENT_EVENT >> 3
        if command_code != expected or arg_count != 6:
            _LOGGER.debug(
                "Measurement: unknown command 0x%02X (code=%d, args=%d), skipping",
                opcode,
                command_code,
                arg_count,
            )
            pos += 1 + arg_count
            continue

        device_id = sal_data[pos + 1]
        channel = sal_data[pos + 2]
        unit_code = sal_data[pos + 3]
        # Multiplier is signed 8-bit two's complement.
        mult_raw = sal_data[pos + 4]
        multiplier = mult_raw if mult_raw < 128 else mult_raw - 256
        # Value is signed 16-bit two's complement (big-endian).
        raw_unsigned = (sal_data[pos + 5] << 8) | sal_data[pos + 6]
        raw_value = raw_unsigned if raw_unsigned < 32768 else raw_unsigned - 65536

        m = MeasurementData(
            device_id=device_id,
            channel=channel,
            unit_code=unit_code,
            multiplier=multiplier,
            raw_value=raw_value,
        )

        _LOGGER.debug(
            "Measurement: dev=%d ch=%d unit=0x%02X mult=%d raw=%d -> %.2f %s",
            device_id,
            channel,
            unit_code,
            multiplier,
            raw_value,
            m.value,
            m.unit_label,
        )

        results.append(m)
        pos += 7  # 1 command byte + 6 args

    return results
