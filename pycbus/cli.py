"""Command-line interface for pycbus — test C-Bus independently of Home Assistant.

This module provides a standalone CLI for interacting with a C-Bus network
directly from the terminal.  It is invaluable for:

- Verifying that the pycbus library can connect to a PCI/CNI.
- Testing lighting commands without deploying the HA integration.
- Debugging protocol issues with verbose hex output.
- Monitoring live C-Bus traffic on the network.

Usage::

    # Show all available commands
    python -m pycbus --help

    # Build and display a Lighting ON command (no connection needed)
    python -m pycbus build on --group 1

    # Build a ramp command with a specific rate
    python -m pycbus build ramp --group 5 --level 128 --rate 4s

    # Connect to a CNI and send a command (requires network access)
    python -m pycbus send --host 192.168.1.50 --port 10001 on --group 1

    # Monitor all C-Bus traffic (requires network access)
    python -m pycbus monitor --host 192.168.1.50 --port 10001

    # Validate a checksum
    python -m pycbus checksum 05380079 01FF

Sub-commands:

    build     Build and display SAL command bytes (offline — no connection).
    checksum  Compute or verify a checksum for arbitrary hex bytes.
    send      Connect to a CNI/PCI and transmit a command.
    monitor   Connect and print all received SAL events.

The ``build`` and ``checksum`` sub-commands work entirely offline and are
useful for verifying command construction in unit tests or documentation.
The ``send`` and ``monitor`` sub-commands require a live C-Bus interface.

Exit codes:
    0 — success
    1 — invalid arguments
    2 — connection failure
    3 — command rejected (NEGATIVE confirmation)
"""

from __future__ import annotations

import argparse
import sys

from .checksum import checksum, verify
from .commands import lighting_off, lighting_on, lighting_ramp, lighting_terminate_ramp
from .constants import RAMP_DURATIONS, LightingCommand


def _find_closest_ramp(seconds: float) -> LightingCommand:
    """Find the ramp-rate opcode closest to the requested duration.

    Args:
        seconds: Desired fade duration in seconds.

    Returns:
        The :class:`LightingCommand` ramp opcode with the closest
        built-in duration.

    Example::

        >>> _find_closest_ramp(5.0)
        <LightingCommand.RAMP_4S: 10>
    """
    best_rate = RAMP_DURATIONS[0][1]
    best_diff = abs(seconds - RAMP_DURATIONS[0][0])
    for duration, rate in RAMP_DURATIONS[1:]:
        diff = abs(seconds - duration)
        if diff < best_diff:
            best_diff = diff
            best_rate = rate
    return best_rate


def _format_hex(data: bytes) -> str:
    """Format bytes as a space-separated hex string for display.

    Args:
        data: Raw bytes to format.

    Returns:
        Human-readable hex string, e.g. ``"05 38 00 79 01 FF 50"``.
    """
    return " ".join(f"{b:02X}" for b in data)


def _format_wire(data: bytes) -> str:
    """Format bytes as they would appear on the wire (backslash-framed).

    Args:
        data: Raw command bytes including checksum.

    Returns:
        Wire-format string, e.g. ``"\\\\0538007901FF50\\r"``.
    """
    return f"\\{data.hex().upper()}\\r"


def cmd_build(args: argparse.Namespace) -> int:
    """Execute the ``build`` sub-command — construct and display a SAL command.

    This works entirely offline (no C-Bus connection required).

    Args:
        args: Parsed CLI arguments from argparse.

    Returns:
        Exit code (0 = success, 1 = invalid arguments).
    """
    group = args.group
    network = getattr(args, "network", 0)

    if args.action == "on":
        cmd = lighting_on(group=group, network=network)
        desc = f"Lighting ON — group {group} → 0xFF"
    elif args.action == "off":
        cmd = lighting_off(group=group, network=network)
        desc = f"Lighting OFF — group {group} → 0x00"
    elif args.action == "ramp":
        level = args.level
        if args.rate:
            # Parse rate string like "4s", "30s", "120s"
            rate_seconds = float(args.rate.rstrip("sS"))
            rate = _find_closest_ramp(rate_seconds)
        else:
            rate = LightingCommand.RAMP_INSTANT
        cmd = lighting_ramp(group=group, level=level, rate=rate, network=network)
        desc = f"Lighting RAMP — group {group} → {level} ({rate.name})"
    elif args.action == "terminate":
        cmd = lighting_terminate_ramp(group=group, network=network)
        desc = f"Lighting TERMINATE RAMP — group {group}"
    else:
        print(f"Unknown action: {args.action}", file=sys.stderr)
        return 1

    print(f"Command:  {desc}")
    print(f"Bytes:    {_format_hex(cmd)}")
    print(f"Wire:     {_format_wire(cmd)}")
    print(f"Length:   {len(cmd)} bytes ({len(cmd) - 1} payload + 1 checksum)")
    print(f"Checksum: 0x{cmd[-1]:02X} ({'valid' if verify(cmd) else 'INVALID'})")
    return 0


def cmd_checksum(args: argparse.Namespace) -> int:
    """Execute the ``checksum`` sub-command — compute or verify a checksum.

    Args:
        args: Parsed CLI arguments.  ``args.hex_bytes`` is a list of hex
              strings (e.g. ``["05", "38", "00", "79", "01", "FF"]``).

    Returns:
        Exit code (0 = valid/success, 1 = invalid checksum).
    """
    try:
        raw = bytes.fromhex("".join(args.hex_bytes))
    except ValueError as exc:
        print(f"Invalid hex input: {exc}", file=sys.stderr)
        return 1

    if args.verify:
        valid = verify(raw)
        print(f"Data:     {_format_hex(raw)}")
        print(f"Valid:    {'YES ✓' if valid else 'NO ✗'}")
        return 0 if valid else 1
    else:
        cs = checksum(raw)
        print(f"Data:     {_format_hex(raw)}")
        print(f"Checksum: 0x{cs:02X}")
        print(f"Full:     {_format_hex(raw + bytes([cs]))}")
        return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the pycbus CLI.

    Returns:
        Configured :class:`argparse.ArgumentParser` with all sub-commands.
    """
    parser = argparse.ArgumentParser(
        prog="pycbus",
        description="pycbus CLI — test C-Bus commands independently of Home Assistant.",
        epilog="See https://github.com/DamianFlynn/ha-cbus for full documentation.",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # --- build sub-command ---
    build_parser = sub.add_parser(
        "build",
        help="Build and display a SAL command (offline, no connection needed).",
    )
    build_parser.add_argument(
        "action",
        choices=["on", "off", "ramp", "terminate"],
        help="Lighting action to build.",
    )
    build_parser.add_argument(
        "--group", "-g",
        type=int,
        required=True,
        help="Target group address (0–255).",
    )
    build_parser.add_argument(
        "--level", "-l",
        type=int,
        default=255,
        help="Target brightness level for ramp commands (0–255, default: 255).",
    )
    build_parser.add_argument(
        "--rate", "-r",
        type=str,
        default=None,
        help="Ramp duration (e.g. '4s', '30s', '120s'). Nearest rate is chosen.",
    )
    build_parser.add_argument(
        "--network", "-n",
        type=int,
        default=0,
        help="C-Bus network number (default: 0).",
    )

    # --- checksum sub-command ---
    cs_parser = sub.add_parser(
        "checksum",
        help="Compute or verify a checksum for hex bytes.",
    )
    cs_parser.add_argument(
        "hex_bytes",
        nargs="+",
        help="Hex byte strings (e.g. '05 38 00 79 01 FF' or '0538007901FF').",
    )
    cs_parser.add_argument(
        "--verify", "-v",
        action="store_true",
        help="Verify the checksum instead of computing it.",
    )

    # --- send sub-command (placeholder) ---
    send_parser = sub.add_parser(
        "send",
        help="Connect to a CNI/PCI and send a command (requires live interface).",
    )
    send_parser.add_argument("--host", type=str, help="CNI hostname or IP.")
    send_parser.add_argument("--port", type=int, default=10001, help="CNI port.")
    send_parser.add_argument(
        "action",
        choices=["on", "off", "ramp", "terminate"],
        help="Lighting action.",
    )
    send_parser.add_argument("--group", "-g", type=int, required=True)
    send_parser.add_argument("--level", "-l", type=int, default=255)
    send_parser.add_argument("--rate", "-r", type=str, default=None)

    # --- monitor sub-command (placeholder) ---
    mon_parser = sub.add_parser(
        "monitor",
        help="Connect and print all received SAL events (requires live interface).",
    )
    mon_parser.add_argument("--host", type=str, help="CNI hostname or IP.")
    mon_parser.add_argument("--port", type=int, default=10001, help="CNI port.")

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        Exit code for the process.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "build":
        return cmd_build(args)
    elif args.command == "checksum":
        return cmd_checksum(args)
    elif args.command == "send":
        print("send: not yet implemented — transport layer coming soon.", file=sys.stderr)
        return 1
    elif args.command == "monitor":
        print("monitor: not yet implemented — transport layer coming soon.", file=sys.stderr)
        return 1
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
