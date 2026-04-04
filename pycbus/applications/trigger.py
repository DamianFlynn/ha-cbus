"""Trigger Control application (app 0xCA) — Chapter 07.

SAL command builder for trigger events and the SAL-size function.

Reference: *Chapter 07 — C-Bus Trigger Control Application*.
"""

from __future__ import annotations

from ..constants import ApplicationId, PointToMultipointDAT, TriggerCommand


def sal_size(_opcode: int) -> int:
    """Trigger commands are always 3 bytes: opcode + group + action."""
    return 3


def event(group: int, action: int = 0, network: int = 0) -> bytes:
    """Build a Trigger event command."""
    from . import build_pm_command

    return build_pm_command(
        PointToMultipointDAT.BROADCAST,
        ApplicationId.TRIGGER,
        network,
        TriggerCommand.TRIGGER_MIN,
        group,
        action & 0xFF,
    )
