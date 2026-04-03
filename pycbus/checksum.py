"""C-Bus checksum calculation."""


def checksum(data: bytes) -> int:
    """Compute the C-Bus two's-complement checksum.

    The checksum is computed by summing all bytes, taking the bitwise
    complement, adding 1, and masking to 8 bits.  When appended to the
    data, the sum of all bytes (including the checksum) equals 0x00.
    """
    return ((~sum(data) & 0xFF) + 1) & 0xFF


def verify(data: bytes) -> bool:
    """Verify that *data* (including the trailing checksum byte) is valid."""
    return sum(data) & 0xFF == 0x00
