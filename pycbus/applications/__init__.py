"""Per-application SAL command definitions and registry.

C-Bus supports dozens of applications, each with its own SAL command set.
Rather than encoding every application into a single monolithic module,
pycbus uses an *application registry* pattern:

Architecture::

    pycbus/applications/
    ├── __init__.py          ← this file, registry + shared builder
    ├── lighting.py          ← Lighting (app 0x38)
    ├── trigger.py           ← Trigger (app 0xCA)
    ├── enable.py            ← Enable (app 0xCB)
    ├── measurement.py       ← Measurement (app 0xE4)
    └── ...                  ← one file per application chapter

Adding a new application:
    1. Create ``pycbus/applications/<name>.py``.
    2. Define command builders and a ``sal_size(opcode) -> int`` function.
    3. Register the sal_size function in ``APP_SAL_SIZE`` here.

The protocol layer uses the registry to dispatch incoming SAL events
to the correct parser.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..checksum import checksum
from ..constants import ApplicationId

if TYPE_CHECKING:
    from collections.abc import Callable

from . import enable, lighting, measurement, trigger

__all__ = [
    "APP_SAL_SIZE",
    "build_pm_command",
    "enable",
    "get_sal_command_size",
    "lighting",
    "measurement",
    "trigger",
]

# Shared low-level builder used by all application command modules.


def build_pm_command(*payload_bytes: int) -> bytes:
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


# Registry mapping application IDs to their SAL size function.
# Unknown applications fall back to the lighting pattern (most common).
APP_SAL_SIZE: dict[int, Callable[[int], int]] = {
    ApplicationId.LIGHTING: lighting.sal_size,
    ApplicationId.TRIGGER: trigger.sal_size,
    ApplicationId.ENABLE: enable.sal_size,
    ApplicationId.MEASUREMENT: measurement.sal_size,
}


def get_sal_command_size(app_id: int, opcode: int) -> int:
    """Determine the byte count for a SAL command in a given application.

    Falls back to the lighting pattern for unknown applications, which
    is safe because the ramp-detection heuristic (low 3 bits == 0b010)
    is used across most C-Bus applications that support dimming.
    """
    size_fn = APP_SAL_SIZE.get(app_id, lighting.sal_size)
    return size_fn(opcode)
