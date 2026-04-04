"""Lighting application (app 0x38) — Chapter 02.

SAL command builders for on/off/ramp/terminate/label and the SAL-size
function used by the generic parser.

Reference: *Chapter 02 — C-Bus Lighting Application*.
"""

from __future__ import annotations

from ..constants import (
    LABEL_MAX_TEXT_LENGTH,
    LABEL_MIN_ARG_COUNT,
    LABEL_OPCODE_MASK,
    ApplicationId,
    LabelLanguage,
    LabelOption,
    LightingCommand,
    PointToMultipointDAT,
)


def sal_size(opcode: int) -> int:
    """Size of a lighting SAL command.

    Short-form commands:
      Ramp opcodes (low 3 bits == 0b010) consume 3 bytes: opcode + group
      + level.  All other opcodes (ON, OFF, TERMINATE_RAMP) consume 2
      bytes: opcode + group.

    Long-form commands (label):
      Label opcodes have bit 7 set (%1xxxxxxx).  The low 5 bits encode
      the argument count; total size = 1 (opcode) + arg_count.

    Reference: micolous/cbus common.py LIGHT_RAMP_COMMANDS set;
               Chapter 02, s2.5.2 for label.
    """
    if opcode & 0x80:
        # Long-form: %1CCLLLL — low 5 bits = argument count.
        return 1 + (opcode & 0x1F)
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


def label(
    group: int,
    text: str,
    *,
    flavour: int = 0,
    language: LabelLanguage = LabelLanguage.ENGLISH,
    network: int = 0,
) -> bytes:
    """Build a Lighting Label command for eDLT switches.

    Sets the text displayed on a DLT/eDLT wall switch button.
    The label is associated with a lighting group address and a
    flavour (button index on multi-button units).

    The resulting SAL frame uses the long-form command encoding
    from Chapter 02, s2.6.5::

        05 38 <network> <opcode> <group> <options> <language> <text_bytes...> <checksum>

    Where the opcode byte is ``0xA0 | arg_count`` and arg_count =
    3 (group + options + language) + len(text).

    Args:
        group: Target group address (0-255).
        text: Label text, up to 16 ASCII characters.  Empty string
              clears the label (reverts to unit default).
        flavour: Button flavour (0-3).  Multi-button DLT units use
                 flavours to address individual buttons.  Default 0.
        language: Language code for the label.  Default English.
        network: C-Bus network number (default 0).

    Returns:
        Complete SAL command bytes with checksum.

    Raises:
        ValueError: If text exceeds 16 characters or flavour is out
                    of range (0-3).
    """
    from . import build_pm_command

    if len(text) > LABEL_MAX_TEXT_LENGTH:
        msg = (
            f"Label text exceeds {LABEL_MAX_TEXT_LENGTH} characters: "
            f"{len(text)} given"
        )
        raise ValueError(msg)
    if not 0 <= flavour <= 3:
        msg = f"Flavour must be 0-3, got {flavour}"
        raise ValueError(msg)

    text_bytes = text.encode("ascii")
    arg_count = LABEL_MIN_ARG_COUNT + len(text_bytes)
    opcode = LABEL_OPCODE_MASK | arg_count

    options = LabelOption.TEXT_LABEL | (flavour << 5)

    return build_pm_command(
        PointToMultipointDAT.BROADCAST,
        ApplicationId.LIGHTING,
        network,
        opcode,
        group,
        options,
        language,
        *text_bytes,
    )


def clear_label(
    group: int,
    *,
    flavour: int = 0,
    language: LabelLanguage = LabelLanguage.ENGLISH,
    network: int = 0,
) -> bytes:
    """Build a Label command that clears (deletes) a label.

    Per the spec (s2.9.6.2), sending a label with zero text bytes
    causes the DLT unit to revert to its default label for that
    group/flavour/language combination.

    Args:
        group: Target group address (0-255).
        flavour: Button flavour (0-3).
        language: Language code.
        network: C-Bus network number.

    Returns:
        Complete SAL command bytes with checksum.
    """
    return label(group, "", flavour=flavour, language=language, network=network)
