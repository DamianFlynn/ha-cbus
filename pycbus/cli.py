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
import asyncio
import logging
import re
import signal
import sys

from .checksum import checksum, verify
from .commands import (
    lighting_off,
    lighting_on,
    lighting_ramp,
    lighting_terminate_ramp,
    parse_measurement_data,
    parse_sal_event,
)
from .constants import (
    RAMP_DURATIONS,
    ApplicationId,
    LightingCommand,
)

_LOGGER = logging.getLogger(__name__)

# Human-readable application names for monitor display.
_APP_NAMES: dict[int, str] = {
    int(ApplicationId.LIGHTING): "LIGHTING",
    int(ApplicationId.TRIGGER): "TRIGGER",
    int(ApplicationId.ENABLE): "ENABLE",
    int(ApplicationId.SECURITY): "SECURITY",
    int(ApplicationId.METERING): "METERING",
    int(ApplicationId.TEMPERATURE_BROADCAST): "TEMPERATURE",
    int(ApplicationId.AIR_CONDITIONING): "AIRCON",
    int(ApplicationId.MEASUREMENT): "MEASUREMENT",
    int(ApplicationId.CLOCK): "CLOCK",
}

# Opcode names for known lighting commands.
_LIGHTING_OPCODE_NAMES: dict[int, str] = {
    int(LightingCommand.ON): "ON",
    int(LightingCommand.OFF): "OFF",
    int(LightingCommand.TERMINATE_RAMP): "TERMINATE",
}

# Matches digits/decimal with an optional 's'/'S' suffix (no sign — rates are positive).
_RATE_RE = re.compile(r"^\d+(?:\.\d+)?[sS]?$")


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


def _parse_rate_seconds(rate_str: str) -> float:
    """Parse a rate string such as ``"4s"`` or ``"30.5"`` into seconds.

    Args:
        rate_str: A string of the form ``"<number>[sS]"``, e.g. ``"4s"``,
                  ``"30S"``, or ``"120"``.

    Returns:
        The numeric duration in seconds as a float.

    Raises:
        ValueError: If *rate_str* does not match the expected format.

    Example::

        >>> _parse_rate_seconds("4s")
        4.0
        >>> _parse_rate_seconds("30")
        30.0
    """
    if not _RATE_RE.match(rate_str):
        raise ValueError(
            f"Invalid rate '{rate_str}': expected a positive number with an "
            "optional 's' suffix, e.g. '4s', '30', '120s'."
        )
    return float(rate_str.rstrip("sS"))


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
            try:
                rate_seconds = _parse_rate_seconds(args.rate)
            except ValueError as exc:
                print(f"--rate: {exc}", file=sys.stderr)
                return 1
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


def cmd_send(args: argparse.Namespace) -> int:
    """Execute the ``send`` sub-command -- connect and transmit a command.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Exit code (0 = confirmed, 2 = connection error, 3 = rejected).
    """
    from .protocol import CbusProtocol
    from .transport import TcpTransport

    group = args.group
    network = getattr(args, "network", 0)

    if args.action == "on":
        cmd = lighting_on(group=group, network=network)
        desc = f"Lighting ON -- group {group}"
    elif args.action == "off":
        cmd = lighting_off(group=group, network=network)
        desc = f"Lighting OFF -- group {group}"
    elif args.action == "ramp":
        level = args.level
        if args.rate:
            try:
                rate_seconds = _parse_rate_seconds(args.rate)
            except ValueError as exc:
                print(f"--rate: {exc}", file=sys.stderr)
                return 1
            rate = _find_closest_ramp(rate_seconds)
        else:
            rate = LightingCommand.RAMP_INSTANT
        cmd = lighting_ramp(group=group, level=level, rate=rate, network=network)
        desc = f"Lighting RAMP -- group {group} -> {level} ({rate.name})"
    elif args.action == "terminate":
        cmd = lighting_terminate_ramp(group=group, network=network)
        desc = f"Lighting TERMINATE RAMP -- group {group}"
    else:
        print(f"Unknown action: {args.action}", file=sys.stderr)
        return 1

    async def _run() -> int:
        transport = TcpTransport(host=args.host, port=args.port)
        protocol = CbusProtocol(transport)

        print(f"Connecting to {args.host}:{args.port}...")
        try:
            await protocol.connect()
        except Exception as exc:
            print(f"Connection failed: {exc}", file=sys.stderr)
            return 2

        print(f"Connected. State: {protocol.state.name}")
        print(f"Sending:  {desc}")
        print(f"Bytes:    {_format_hex(cmd)}")
        print(f"Wire:     {_format_wire(cmd)}")

        hex_payload = cmd.hex().upper().encode()
        confirmed = await protocol.send_command(hex_payload)

        if confirmed:
            print("Result:   CONFIRMED (g)")
        else:
            print("Result:   REJECTED (!)")

        await protocol.disconnect()
        print("Disconnected.")
        return 0 if confirmed else 3

    return asyncio.run(_run())


def cmd_monitor(args: argparse.Namespace) -> int:
    """Execute the ``monitor`` sub-command -- connect and print SAL events.

    Runs until interrupted with Ctrl+C.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Exit code (0 = clean exit, 2 = connection error).
    """
    from .protocol import CbusProtocol
    from .transport import TcpTransport

    def _format_opcode(app_id: int, opcode: int) -> str:
        """Return a human-readable name for a SAL opcode."""
        if app_id == ApplicationId.LIGHTING:
            name = _LIGHTING_OPCODE_NAMES.get(opcode)
            if name:
                return name
            if opcode & 0x07 == 0x02:
                # Ramp opcode — look up duration from RAMP_DURATIONS.
                for duration, rate in RAMP_DURATIONS:
                    if int(rate) == opcode:
                        return f"RAMP_{duration}S"
                return f"RAMP_0x{opcode:02X}"
        elif app_id == ApplicationId.TRIGGER:
            return "TRIGGER"
        elif app_id == ApplicationId.ENABLE:
            if opcode == 0x79:
                return "ON"
            if opcode == 0x01:
                return "OFF"
        return f"0x{opcode:02X}"

    def _on_event(sal_bytes: bytes) -> None:
        """Parse and display a SAL monitor event."""
        raw_hex = sal_bytes.hex().upper()
        event = parse_sal_event(sal_bytes)

        if event is None:
            print(f"  [RAW] {raw_hex}")
            return

        app_name = _APP_NAMES.get(event.app_id, f"APP_0x{event.app_id:02X}")

        for cmd in event.commands:
            op_name = _format_opcode(event.app_id, cmd.opcode)
            parts = [
                f"[{app_name}]",
                f"src={event.source}",
                op_name,
                f"group={cmd.group}",
            ]
            if cmd.data is not None:
                if event.app_id == ApplicationId.LIGHTING:
                    parts.append(f"level={cmd.data}")
                elif event.app_id == ApplicationId.TRIGGER:
                    parts.append(f"action={cmd.data}")
                else:
                    parts.append(f"data={cmd.data}")
            print(f"  {' '.join(parts)}")

        # Measurement events carry sensor data — decode and display.
        if event.app_id == ApplicationId.MEASUREMENT:
            sal_data = sal_bytes[4:-1]  # strip 4-byte header + checksum
            for m in parse_measurement_data(sal_data):
                print(
                    f"    -> dev={m.device_id} ch={m.channel}"
                    f" {m.value:.2f} {m.unit_label}"
                )

        _LOGGER.debug("Raw: %s", raw_hex)

    async def _run() -> int:
        transport = TcpTransport(host=args.host, port=args.port)
        protocol = CbusProtocol(transport)

        print(f"Connecting to {args.host}:{args.port}...")
        try:
            await protocol.connect()
        except Exception as exc:
            print(f"Connection failed: {exc}", file=sys.stderr)
            return 2

        print(f"Connected. State: {protocol.state.name}")
        print("Monitoring C-Bus traffic (Ctrl+C to stop)...\n")

        protocol.on_event(_on_event)

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)

        await stop.wait()

        print("\nDisconnecting...")
        await protocol.disconnect()
        print("Done.")
        return 0

    return asyncio.run(_run())


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

    # -- Global verbose flag --
    parser.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
        help=(
            "Increase logging verbosity. "
            "-v = INFO (state changes), "
            "-vv = DEBUG (hex frames + parse detail)."
        ),
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
        "--group",
        "-g",
        type=int,
        required=True,
        help="Target group address (0-255).",
    )
    build_parser.add_argument(
        "--level",
        "-l",
        type=int,
        default=255,
        help="Target brightness level for ramp commands (0-255, default: 255).",
    )
    build_parser.add_argument(
        "--rate",
        "-r",
        type=str,
        default=None,
        help="Ramp duration (e.g. '4s', '30s', '120s'). Nearest rate is chosen.",
    )
    build_parser.add_argument(
        "--network",
        "-n",
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
        "--verify",
        "-v",
        action="store_true",
        help="Verify the checksum instead of computing it.",
    )

    # --- send sub-command ---
    send_parser = sub.add_parser(
        "send",
        help="Connect to a CNI/PCI and send a command (requires live interface).",
    )
    send_parser.add_argument(
        "--host", type=str, required=True, help="CNI hostname or IP."
    )
    send_parser.add_argument("--port", type=int, default=10001, help="CNI port.")
    send_parser.add_argument(
        "action",
        choices=["on", "off", "ramp", "terminate"],
        help="Lighting action.",
    )
    send_parser.add_argument("--group", "-g", type=int, required=True)
    send_parser.add_argument("--level", "-l", type=int, default=255)
    send_parser.add_argument("--rate", "-r", type=str, default=None)

    # --- monitor sub-command ---
    mon_parser = sub.add_parser(
        "monitor",
        help="Connect and print all received SAL events (requires live interface).",
    )
    mon_parser.add_argument(
        "--host", type=str, required=True, help="CNI hostname or IP."
    )
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

    # Configure logging based on verbosity level.
    # -v  → INFO  (protocol state changes, event summaries)
    # -vv → DEBUG (hex frames, parse detail, transport bytes)
    if args.verbose >= 2:
        log_level = logging.DEBUG
    elif args.verbose == 1:
        log_level = logging.INFO
    else:
        log_level = logging.WARNING

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "build":
        return cmd_build(args)
    elif args.command == "checksum":
        return cmd_checksum(args)
    elif args.command == "send":
        return cmd_send(args)
    elif args.command == "monitor":
        return cmd_monitor(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
