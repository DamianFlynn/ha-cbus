"""Enable Control application (app 0xCB) — Chapter 08.

SAL command builders for enable on/off and the SAL-size function.

Reference: *Chapter 08 — C-Bus Enable Control Application*.
"""

from __future__ import annotations

from ..constants import ApplicationId, EnableCommand, PointToMultipointDAT


def sal_size(_opcode: int) -> int:
    """Enable commands are always 2 bytes: opcode + group."""
    return 2


def on(group: int, network: int = 0) -> bytes:
    """Build an Enable ON command (group -> 0xFF)."""
    from . import build_pm_command

    return build_pm_command(
        PointToMultipointDAT.BROADCAST,
        ApplicationId.ENABLE,
        network,
        EnableCommand.ON,
        group,
        0xFF,
    )


def off(group: int, network: int = 0) -> bytes:
    """Build an Enable OFF command (group -> 0x00)."""
    from . import build_pm_command

    return build_pm_command(
        PointToMultipointDAT.BROADCAST,
        ApplicationId.ENABLE,
        network,
        EnableCommand.OFF,
        group,
    )
