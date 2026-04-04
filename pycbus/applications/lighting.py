"""Lighting application (app 0x38) — Chapter 02.

SAL command builders for on/off/ramp/terminate and the SAL-size
function used by the generic parser.

Reference: *Chapter 02 — C-Bus Lighting Application*.
"""

from __future__ import annotations

from ..constants import ApplicationId, LightingCommand, PointToMultipointDAT


def sal_size(opcode: int) -> int:
    """Size of a lighting SAL command.

    Ramp opcodes (low 3 bits == 0b010) consume 3 bytes: opcode + group
    + level.  All other opcodes (ON, OFF, TERMINATE_RAMP) consume 2
    bytes: opcode + group.

    Reference: micolous/cbus common.py LIGHT_RAMP_COMMANDS set.
    """
    if opcode & 0x07 == 0x02:
        return 3  # ramp: opcode + group + level
    return 2  # ON / OFF / TERMINATE_RAMP: opcode + group


def on(group: int, network: int = 0) -> bytes:
    """Build a Lighting ON command (group -> 0xFF)."""
    from . import build_pm_command

    return build_pm_command(
        PointToMultipointDAT.BROADCAST,
        ApplicationId.LIGHTING,
        network,
        LightingCommand.ON,
        group,
        0xFF,
    )


def off(group: int, network: int = 0) -> bytes:
    """Build a Lighting OFF command (group -> 0x00)."""
    from . import build_pm_command

    return build_pm_command(
        PointToMultipointDAT.BROADCAST,
        ApplicationId.LIGHTING,
        network,
        LightingCommand.OFF,
        group,
    )


def ramp(
    group: int,
    level: int,
    rate: LightingCommand = LightingCommand.RAMP_INSTANT,
    network: int = 0,
) -> bytes:
    """Build a Lighting RAMP command (group -> level at rate)."""
    from . import build_pm_command

    return build_pm_command(
        PointToMultipointDAT.BROADCAST,
        ApplicationId.LIGHTING,
        network,
        rate,
        group,
        level & 0xFF,
    )


def terminate_ramp(group: int, network: int = 0) -> bytes:
    """Build a TERMINATE RAMP command for a group."""
    from . import build_pm_command

    return build_pm_command(
        PointToMultipointDAT.BROADCAST,
        ApplicationId.LIGHTING,
        network,
        LightingCommand.TERMINATE_RAMP,
        group,
    )
