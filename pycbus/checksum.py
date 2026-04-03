"""C-Bus checksum calculation.

Every C-Bus serial frame includes a single-byte checksum as its last byte
before the carriage-return terminator.  The algorithm is the *two's
complement* of the sum of all preceding bytes, masked to 8 bits.

Reference: *C-Bus Serial Interface User Guide*, §4.2.2 — Checksum
    "The checksum is the two's complement of the sum of all bytes
     in the message excluding the leading backslash and trailing
     carriage return."

Example for a Lighting ON command (group 1, level 0xFF)::

    Payload bytes:  05 38 00 79 01 FF
    Sum:            0x05 + 0x38 + 0x00 + 0x79 + 0x01 + 0xFF = 0x1B0
    Low byte:       0xB0
    Complement:     ~0xB0 & 0xFF = 0x4F
    +1:             0x4F + 1 = 0x50
    Transmitted:    \\05380079 01FF50\\r

When the receiver sums *all* bytes (including the checksum), the result
is 0x00 — this is how :func:`verify` works.
"""

from __future__ import annotations


def checksum(data: bytes) -> int:
    """Compute the C-Bus two's-complement checksum for *data*.

    Args:
        data: The raw payload bytes *without* the checksum byte.

    Returns:
        A single byte (0x00-0xFF) to append as the checksum.

    Example::

        >>> from pycbus.checksum import checksum
        >>> hex(checksum(bytes([0x05, 0x38, 0x00, 0x79, 0x01, 0xFF])))
        '0x50'
    """
    return ((~sum(data) & 0xFF) + 1) & 0xFF


def verify(data: bytes) -> bool:
    """Verify a checksummed frame.

    Args:
        data: The full frame bytes *including* the trailing checksum byte.

    Returns:
        ``True`` if the frame's checksum is valid (byte-sum ≡ 0 mod 256).

    Example::

        >>> from pycbus.checksum import verify
        >>> verify(bytes([0x05, 0x38, 0x00, 0x79, 0x01, 0xFF, 0x50]))
        True
    """
    return sum(data) & 0xFF == 0x00
