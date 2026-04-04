"""Command-line interface for testing pycbus against real C-Bus hardware.

This CLI is a *standalone consumer* of the ``pycbus`` library — it sits
outside the library package and uses the exact same public API that the
Home Assistant integration uses.  If the CLI works, the library works.

Command hierarchy::

    cli light on        --host H --group G [--network N]
    cli light off       --host H --group G [--network N]
    cli light ramp      --host H --group G --level L [--rate Rs] [--network N]
    cli light terminate --host H --group G [--network N]

    cli switch on       --host H --group G [--network N]
    cli switch off      --host H --group G [--network N]

    cli trigger fire    --host H --group G [--action A] [--network N]

    cli monitor         --host H [--port P]

    cli build on        --group G [--network N]              (offline)
    cli build off       --group G [--network N]              (offline)
    cli build ramp      --group G --level L [--rate]         (offline)
    cli build terminate --group G [--network N]              (offline)
    cli build enable-on --group G [--network N]              (offline)
    cli build enable-off --group G [--network N]             (offline)
    cli build trigger   --group G [--action-selector A]      (offline)

    cli checksum        HEX... [--verify]                    (offline)

Every live command (light, switch, trigger, monitor) connects to a
C-Bus PCI/CNI via TCP, runs the protocol init sequence, executes the
requested action, and disconnects cleanly.

Exit codes::

    0 -- success
    1 -- invalid arguments or usage error
    2 -- connection / transport failure
    3 -- command rejected by PCI (NEGATIVE confirmation)

Environment:
    CBUS_HOST  -- default host (overridden by --host)
    CBUS_PORT  -- default port (overridden by --port, default 10001)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import signal
import sys

from pycbus.checksum import checksum, verify
from pycbus.commands import (
    enable_off,
    enable_on,
    lighting_off,
    lighting_on,
    lighting_ramp,
    lighting_terminate_ramp,
    parse_sal_event,
    trigger_event,
)
from pycbus.constants import RAMP_DURATIONS, ApplicationId, LightingCommand

_LOGGER = logging.getLogger("cbus_cli")

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_RATE_RE = re.compile(r"^\d+(?:\.\d+)?[sS]?$")

_APP_NAMES: dict[int, str] = {
    ApplicationId.LIGHTING: "LIGHTING",
    ApplicationId.TRIGGER: "TRIGGER",
    ApplicationId.ENABLE: "ENABLE",
    ApplicationId.SECURITY: "SECURITY",
    ApplicationId.METERING: "METERING",
    ApplicationId.TEMPERATURE_BROADCAST: "TEMPERATURE",
    ApplicationId.AIR_CONDITIONING: "AIRCON",
    ApplicationId.CLOCK: "CLOCK",
}

# Opcode names for known lighting commands.
_LIGHTING_OPCODE_NAMES: dict[int, str] = {
    int(LightingCommand.ON): "ON",
    int(LightingCommand.OFF): "OFF",
    int(LightingCommand.TERMINATE_RAMP): "TERMINATE",
}


def _env_host() -> str | None:
    """Return CBUS_HOST from environment, or None."""
    return os.environ.get("CBUS_HOST")


def _env_port() -> int:
    """Return CBUS_PORT from environment, or 10001."""
    return int(os.environ.get("CBUS_PORT", "10001"))


def _find_closest_ramp(seconds: float) -> LightingCommand:
    """Find the ramp-rate opcode closest to *seconds*.

    Uses linear scan of the pre-sorted :data:`RAMP_DURATIONS` table.

    Args:
        seconds: Desired fade duration in seconds.

    Returns:
        The ``LightingCommand`` ramp opcode whose built-in duration
        is closest to the requested value.
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
    """Parse a rate string like ``'4s'`` or ``'30'`` into seconds.

    Accepts an optional trailing ``s`` / ``S`` suffix.

    Args:
        rate_str: Duration string, e.g. ``'4s'``, ``'30S'``, ``'120'``.

    Returns:
        Duration as a float.

    Raises:
        ValueError: If the string does not match ``<number>[s]``.
    """
    if not _RATE_RE.match(rate_str):
        msg = (
            f"Invalid rate '{rate_str}': expected a positive number "
            "with optional 's' suffix (e.g. '4s', '30', '120s')."
        )
        raise ValueError(msg)
    return float(rate_str.rstrip("sS"))


def _format_hex(data: bytes) -> str:
    """Format bytes as space-separated uppercase hex."""
    return " ".join(f"{b:02X}" for b in data)


def _format_wire(data: bytes) -> str:
    """Format bytes as wire representation: ``\\HEX\\r``."""
    return f"\\{data.hex().upper()}\\r"


async def _connect(host: str, port: int):
    """Create transport + protocol and connect.

    Returns:
        A connected ``CbusProtocol`` instance.

    Raises:
        SystemExit(2) on connection failure.
    """
    from pycbus.protocol import CbusProtocol
    from pycbus.transport import TcpTransport

    transport = TcpTransport(host=host, port=port)
    protocol = CbusProtocol(transport)

    print(f"Connecting to {host}:{port} ...")
    try:
        await protocol.connect()
    except Exception as exc:
        print(f"Connection failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    print(f"Connected.  Protocol state: {protocol.state.name}")
    return protocol


async def _send_and_report(
    protocol,
    cmd: bytes,
    description: str,
) -> int:
    """Hex-encode *cmd*, send via *protocol*, print result.

    Returns:
        0 if confirmed, 3 if rejected.
    """
    print(f"Action:   {description}")
    print(f"Bytes:    {_format_hex(cmd)}")
    print(f"Wire:     {_format_wire(cmd)}")

    hex_payload = cmd.hex().upper().encode()
    confirmed = await protocol.send_command(hex_payload)

    if confirmed:
        print("Result:   CONFIRMED (g)")
    else:
        print("Result:   REJECTED (!)")
    return 0 if confirmed else 3


# ===================================================================
# light sub-commands — Lighting application (app 56 / 0x38)
# ===================================================================


def cmd_light(args: argparse.Namespace) -> int:
    """Execute a lighting command against a live C-Bus interface.

    Supported actions: on, off, ramp, terminate.

    Connects, sends the SAL command, waits for PCI confirmation, and
    disconnects.

    Returns:
        0 on success, 2 on connection error, 3 if PCI rejects.
    """
    group = args.group
    network = args.network

    if args.action == "on":
        cmd = lighting_on(group=group, network=network)
        desc = f"Light ON — group {group} -> 0xFF"
    elif args.action == "off":
        cmd = lighting_off(group=group, network=network)
        desc = f"Light OFF — group {group} -> 0x00"
    elif args.action == "ramp":
        level = args.level
        if args.rate:
            try:
                secs = _parse_rate_seconds(args.rate)
            except ValueError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            rate = _find_closest_ramp(secs)
        else:
            rate = LightingCommand.RAMP_INSTANT
        cmd = lighting_ramp(group=group, level=level, rate=rate, network=network)
        desc = f"Light RAMP — group {group} -> level {level} ({rate.name})"
    elif args.action == "terminate":
        cmd = lighting_terminate_ramp(group=group, network=network)
        desc = f"Light TERMINATE RAMP — group {group}"
    else:
        print(f"Unknown action: {args.action}", file=sys.stderr)
        return 1

    async def _run() -> int:
        protocol = await _connect(args.host, args.port)
        try:
            return await _send_and_report(protocol, cmd, desc)
        finally:
            await protocol.disconnect()
            print("Disconnected.")

    return asyncio.run(_run())


# ===================================================================
# switch sub-commands — Enable Control application (app 203 / 0xCB)
# ===================================================================


def cmd_switch(args: argparse.Namespace) -> int:
    """Execute an enable/disable command against a live C-Bus interface.

    Supported actions: on, off.

    Returns:
        0 on success, 2 on connection error, 3 if PCI rejects.
    """
    group = args.group
    network = args.network

    if args.action == "on":
        cmd = enable_on(group=group, network=network)
        desc = f"Switch ON (enable) — group {group}"
    elif args.action == "off":
        cmd = enable_off(group=group, network=network)
        desc = f"Switch OFF (disable) — group {group}"
    else:
        print(f"Unknown action: {args.action}", file=sys.stderr)
        return 1

    async def _run() -> int:
        protocol = await _connect(args.host, args.port)
        try:
            return await _send_and_report(protocol, cmd, desc)
        finally:
            await protocol.disconnect()
            print("Disconnected.")

    return asyncio.run(_run())


# ===================================================================
# trigger sub-commands — Trigger Control application (app 202 / 0xCA)
# ===================================================================


def cmd_trigger(args: argparse.Namespace) -> int:
    """Fire a trigger event on a live C-Bus interface.

    Triggers are fire-and-forget.  The PCI will confirm receipt but
    there is no persistent state change.

    Returns:
        0 on success, 2 on connection error, 3 if PCI rejects.
    """
    group = args.group
    action = args.action_selector
    network = args.network

    cmd = trigger_event(group=group, action=action, network=network)
    desc = f"Trigger FIRE — group {group}, action {action}"

    async def _run() -> int:
        protocol = await _connect(args.host, args.port)
        try:
            return await _send_and_report(protocol, cmd, desc)
        finally:
            await protocol.disconnect()
            print("Disconnected.")

    return asyncio.run(_run())


# ===================================================================
# monitor — listen for all SAL events
# ===================================================================


def cmd_monitor(args: argparse.Namespace) -> int:
    """Connect and stream all SAL events until Ctrl+C.

    Prints each event with its application name, opcode, group,
    and level (if present).  Useful for observing wall-switch presses,
    scene triggers, and relay state changes in real time.

    Returns:
        0 on clean exit, 2 on connection error.
    """

    def _format_opcode(app_id: int, opcode: int) -> str:
        """Return a human-readable name for a SAL opcode."""
        if app_id == ApplicationId.LIGHTING:
            name = _LIGHTING_OPCODE_NAMES.get(opcode)
            if name:
                return name
            if opcode & 0x07 == 0x02:
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

        _LOGGER.debug("Raw: %s", raw_hex)

    async def _run() -> int:
        protocol = await _connect(args.host, args.port)
        print("Monitoring C-Bus traffic (Ctrl+C to stop) ...\n")

        protocol.on_event(_on_event)

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)

        await stop.wait()

        print("\nDisconnecting ...")
        await protocol.disconnect()
        print("Done.")
        return 0

    return asyncio.run(_run())


# ===================================================================
# status — query current group levels
# ===================================================================

_APP_ID_MAP: dict[str, int] = {
    "lighting": ApplicationId.LIGHTING,
    "enable": ApplicationId.ENABLE,
}


def cmd_status(args: argparse.Namespace) -> int:
    """Query current group status for an application.

    Connects to the PCI, sends a binary status request covering all
    256 groups, and prints the state of every group that is ON.
    Use ``--all`` to include groups that are OFF.

    Returns:
        0 on success, 2 on connection error.
    """
    app_name = args.app
    app_id = _APP_ID_MAP[app_name]
    show_all = args.all

    async def _run() -> int:
        protocol = await _connect(args.host, args.port)
        try:
            print(f"Requesting status for {app_name.upper()} (app 0x{app_id:02X}) ...")
            levels = await protocol.request_status(app_id)
        except Exception as exc:
            print(f"Status request failed: {exc}", file=sys.stderr)
            return 2
        finally:
            await protocol.disconnect()
            print("Disconnected.")

        if not levels:
            print("No group levels returned.")
            return 0

        # Sort by group address.
        sorted_levels = sorted(levels.items(), key=lambda x: x[0])
        printed = 0
        for (_, group), level in sorted_levels:
            if level > 0 or show_all:
                pct = round(level / 255 * 100)
                bar = "#" * (level // 5) if level > 0 else ""
                state = "ON " if level > 0 else "OFF"
                print(
                    f"  Group {group:>3d}: {state} "
                    f"level={level:>3d}/255 ({pct:>3d}%) {bar}"
                )
                printed += 1

        on_count = sum(1 for v in levels.values() if v > 0)
        print(
            f"\nSummary: {on_count} groups on, "
            f"{len(levels) - on_count} groups off, "
            f"{len(levels)} total"
        )
        return 0

    return asyncio.run(_run())


# ===================================================================
# build — offline command construction (no connection)
# ===================================================================


def cmd_build(args: argparse.Namespace) -> int:
    """Build and display a SAL command without connecting.

    Useful for inspecting byte layout, verifying checksums offline,
    or generating the hex payload for other tools.

    Supports lighting, enable, and trigger commands.

    Returns:
        0 on success, 1 on bad arguments.
    """
    group = args.group
    network = getattr(args, "network", 0)

    if args.action == "on":
        cmd = lighting_on(group=group, network=network)
        desc = f"Lighting ON — group {group} -> 0xFF"
    elif args.action == "off":
        cmd = lighting_off(group=group, network=network)
        desc = f"Lighting OFF — group {group} -> 0x00"
    elif args.action == "ramp":
        level = args.level
        if args.rate:
            try:
                secs = _parse_rate_seconds(args.rate)
            except ValueError as exc:
                print(f"--rate: {exc}", file=sys.stderr)
                return 1
            rate = _find_closest_ramp(secs)
        else:
            rate = LightingCommand.RAMP_INSTANT
        cmd = lighting_ramp(group=group, level=level, rate=rate, network=network)
        desc = f"Lighting RAMP — group {group} -> {level} ({rate.name})"
    elif args.action == "terminate":
        cmd = lighting_terminate_ramp(group=group, network=network)
        desc = f"Lighting TERMINATE RAMP — group {group}"
    elif args.action == "enable-on":
        cmd = enable_on(group=group, network=network)
        desc = f"Enable ON — group {group}"
    elif args.action == "enable-off":
        cmd = enable_off(group=group, network=network)
        desc = f"Enable OFF — group {group}"
    elif args.action == "trigger":
        action_sel = getattr(args, "action_selector", 0)
        cmd = trigger_event(group=group, action=action_sel, network=network)
        desc = f"Trigger — group {group}, action {action_sel}"
    else:
        print(f"Unknown action: {args.action}", file=sys.stderr)
        return 1

    print(f"Command:  {desc}")
    print(f"Bytes:    {_format_hex(cmd)}")
    print(f"Wire:     {_format_wire(cmd)}")
    print(f"Length:   {len(cmd)} bytes ({len(cmd) - 1} payload + 1 checksum)")
    chk_ok = "valid" if verify(cmd) else "INVALID"
    print(f"Checksum: 0x{cmd[-1]:02X} ({chk_ok})")
    return 0


# ===================================================================
# checksum — offline checksum utility
# ===================================================================


def cmd_checksum(args: argparse.Namespace) -> int:
    """Compute or verify a two's-complement C-Bus checksum.

    In compute mode (default), prints the checksum for the given hex
    bytes.  In verify mode (``--verify``), checks whether the last
    byte is a valid checksum of the preceding bytes.

    Returns:
        0 on success / valid, 1 on invalid checksum or bad input.
    """
    try:
        raw = bytes.fromhex("".join(args.hex_bytes))
    except ValueError as exc:
        print(f"Invalid hex input: {exc}", file=sys.stderr)
        return 1

    if args.verify:
        valid = verify(raw)
        print(f"Data:     {_format_hex(raw)}")
        ok_str = "YES" if valid else "NO"
        print(f"Valid:    {ok_str}")
        return 0 if valid else 1

    cs = checksum(raw)
    print(f"Data:     {_format_hex(raw)}")
    print(f"Checksum: 0x{cs:02X}")
    print(f"Full:     {_format_hex(raw + bytes([cs]))}")
    return 0


# ===================================================================
# Shared argparse helpers
# ===================================================================


def _add_connection_args(parser: argparse.ArgumentParser) -> None:
    """Add --host, --port, --network to a subparser."""
    parser.add_argument(
        "--host",
        type=str,
        default=_env_host(),
        required=_env_host() is None,
        help=(
            "CNI/PCI hostname or IP address.  "
            "Can also be set via CBUS_HOST env var.  "
            "Example: 192.168.1.50"
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=_env_port(),
        help=(
            "TCP port of the C-Bus interface (default: 10001).  "
            "Can also be set via CBUS_PORT env var."
        ),
    )
    parser.add_argument(
        "--network",
        "-n",
        type=int,
        default=0,
        help=(
            "C-Bus network number (default: 0).  Multi-network installations use 1-255."
        ),
    )


def _add_group_arg(parser: argparse.ArgumentParser) -> None:
    """Add the required --group argument."""
    parser.add_argument(
        "--group",
        "-g",
        type=int,
        required=True,
        help="Target group address (0-255).",
    )


# ===================================================================
# Parser construction
# ===================================================================


def build_parser() -> argparse.ArgumentParser:
    """Build the full argparse tree for the CLI.

    Returns:
        Configured ``ArgumentParser`` with all sub-commands and options.
    """
    parser = argparse.ArgumentParser(
        prog="cbus-cli",
        description=(
            "C-Bus CLI — control and monitor a C-Bus network "
            "directly from the terminal.  This tool exercises the "
            "pycbus library independently of Home Assistant."
        ),
        epilog=(
            "Examples:\n"
            "  python -m cli light on --host 192.168.1.50 --group 1\n"
            "  python -m cli light ramp --host 192.168.1.50 -g 5 "
            "-l 128 -r 4s\n"
            "  python -m cli switch off --host 192.168.1.50 -g 10\n"
            "  python -m cli trigger fire --host 192.168.1.50 -g 5 "
            "--action 0\n"
            "  python -m cli status lighting --host 192.168.1.50\n"
            "  python -m cli monitor --host 192.168.1.50\n"
            "  python -m cli build on --group 1\n"
            "  python -m cli checksum 05 38 00 79 01 FF\n"
            "\n"
            "Set CBUS_HOST / CBUS_PORT env vars to avoid "
            "repeating --host.\n\n"
            "Documentation: "
            "https://github.com/DamianFlynn/ha-cbus"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help=(
            "Increase logging verbosity. "
            "-v = INFO (state changes), "
            "-vv = DEBUG (hex frames + parse detail)."
        ),
    )
    sub = parser.add_subparsers(
        dest="command",
        help="Command group.  Use '<command> -h' for details.",
    )

    # ---------------------------------------------------------------
    # light — Lighting application (app 56)
    # ---------------------------------------------------------------
    light_p = sub.add_parser(
        "light",
        help=("Control lighting groups (app 56).  Actions: on, off, ramp, terminate."),
        description=(
            "Send lighting commands to C-Bus groups.  "
            "Brightness is 0-255, ramp rates use the closest "
            "built-in PCI duration (0s to 17min)."
        ),
    )
    light_p.add_argument(
        "action",
        choices=["on", "off", "ramp", "terminate"],
        help=(
            "on: set group to full brightness (0xFF).  "
            "off: set group to zero immediately.  "
            "ramp: fade to --level over --rate duration.  "
            "terminate: stop a running fade at current level."
        ),
    )
    _add_connection_args(light_p)
    _add_group_arg(light_p)
    light_p.add_argument(
        "--level",
        "-l",
        type=int,
        default=255,
        help=(
            "Target brightness for ramp (0-255, default: 255).  "
            "Ignored for on/off/terminate."
        ),
    )
    light_p.add_argument(
        "--rate",
        "-r",
        type=str,
        default=None,
        help=(
            "Ramp duration in seconds (e.g. '4s', '30', '120s').  "
            "The nearest built-in PCI rate is selected.  "
            "Available: 0, 4, 8, 12, 20, 30, 40, 60, 90, 120, "
            "180, 300, 420, 600, 900, 1020 seconds.  "
            "Defaults to instant (0s) if omitted."
        ),
    )

    # ---------------------------------------------------------------
    # switch — Enable Control application (app 203)
    # ---------------------------------------------------------------
    switch_p = sub.add_parser(
        "switch",
        help="Control enable groups (app 203).  Actions: on, off.",
        description=(
            "Send enable/disable commands to C-Bus Enable Control "
            "groups.  These are simple binary on/off with no "
            "dimming or ramp rates."
        ),
    )
    switch_p.add_argument(
        "action",
        choices=["on", "off"],
        help=(
            "on: enable the group (set to 0xFF).  off: disable the group (set to 0x00)."
        ),
    )
    _add_connection_args(switch_p)
    _add_group_arg(switch_p)

    # ---------------------------------------------------------------
    # trigger — Trigger Control application (app 202)
    # ---------------------------------------------------------------
    trigger_p = sub.add_parser(
        "trigger",
        help="Fire trigger events (app 202).  Action: fire.",
        description=(
            "Fire a trigger event on a C-Bus trigger group.  "
            "Triggers are fire-and-forget — they carry a group "
            "address and an action selector (0-255) but have no "
            "persistent state."
        ),
    )
    trigger_p.add_argument(
        "action",
        choices=["fire"],
        help="fire: send a trigger event to the group.",
    )
    _add_connection_args(trigger_p)
    _add_group_arg(trigger_p)
    trigger_p.add_argument(
        "--action-selector",
        "-a",
        type=int,
        default=0,
        dest="action_selector",
        help=(
            "Action selector byte (0-255, default: 0).  "
            "Identifies which action within the trigger group."
        ),
    )

    # ---------------------------------------------------------------
    # monitor — live event stream
    # ---------------------------------------------------------------
    monitor_p = sub.add_parser(
        "monitor",
        help="Stream all SAL events from the C-Bus network.",
        description=(
            "Connect to a PCI/CNI and print every SAL event "
            "as it arrives.  Shows lighting level changes, "
            "trigger events, enable state changes, and any "
            "other application traffic.  Press Ctrl+C to stop."
        ),
    )
    _add_connection_args(monitor_p)

    # ---------------------------------------------------------------
    # status — query current group levels
    # ---------------------------------------------------------------
    status_p = sub.add_parser(
        "status",
        help="Query current group levels (connects to PCI).",
        description=(
            "Connect to a PCI/CNI and request the current level "
            "of all 256 groups for a given application.  Prints a "
            "table of group addresses and their brightness/state.  "
            "By default only non-zero groups are shown; use --all "
            "to include zeros."
        ),
    )
    status_p.add_argument(
        "app",
        choices=["lighting", "enable"],
        help=(
            "Application to query.  "
            "lighting: dimmer/relay levels (app 56).  "
            "enable: binary on/off state (app 203)."
        ),
    )
    _add_connection_args(status_p)
    status_p.add_argument(
        "--all",
        action="store_true",
        help="Show all groups including those at level 0 (off).",
    )

    # ---------------------------------------------------------------
    # build — offline command construction
    # ---------------------------------------------------------------
    build_p = sub.add_parser(
        "build",
        help=("Build and display SAL command bytes (offline, no connection)."),
        description=(
            "Construct a SAL command and print its hex bytes, "
            "wire format, length, and checksum.  No C-Bus "
            "connection is required.  Useful for verifying "
            "command construction and generating payloads "
            "for other tools."
        ),
    )
    build_p.add_argument(
        "action",
        choices=[
            "on",
            "off",
            "ramp",
            "terminate",
            "enable-on",
            "enable-off",
            "trigger",
        ],
        help=(
            "on/off/ramp/terminate: lighting commands.  "
            "enable-on/enable-off: enable control.  "
            "trigger: trigger event."
        ),
    )
    _add_group_arg(build_p)
    build_p.add_argument(
        "--level",
        "-l",
        type=int,
        default=255,
        help="Brightness level for ramp (0-255, default: 255).",
    )
    build_p.add_argument(
        "--rate",
        "-r",
        type=str,
        default=None,
        help="Ramp duration (e.g. '4s', '30s').  See 'light -h'.",
    )
    build_p.add_argument(
        "--network",
        "-n",
        type=int,
        default=0,
        help="C-Bus network number (default: 0).",
    )
    build_p.add_argument(
        "--action-selector",
        "-a",
        type=int,
        default=0,
        dest="action_selector",
        help="Action selector for trigger build (0-255).",
    )

    # ---------------------------------------------------------------
    # checksum — offline checksum utility
    # ---------------------------------------------------------------
    cs_p = sub.add_parser(
        "checksum",
        help="Compute or verify a C-Bus checksum (offline).",
        description=(
            "Compute the two's-complement checksum for arbitrary "
            "hex bytes, or verify that a byte sequence already "
            "contains a valid trailing checksum."
        ),
    )
    cs_p.add_argument(
        "hex_bytes",
        nargs="+",
        help=(
            "Hex byte strings, space-separated or joined.  "
            "Example: '05 38 00 79 01 FF' or '0538007901FF'."
        ),
    )
    cs_p.add_argument(
        "--verify",
        action="store_true",
        help=(
            "Verify mode: check whether the last byte is a "
            "valid checksum of the preceding bytes."
        ),
    )

    return parser


# ===================================================================
# Entry point
# ===================================================================


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Command-line arguments.  Defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    verbose = getattr(args, "verbose", 0)
    if verbose >= 2:
        log_level = logging.DEBUG
    elif verbose >= 1:
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

    dispatch = {
        "light": cmd_light,
        "switch": cmd_switch,
        "trigger": cmd_trigger,
        "monitor": cmd_monitor,
        "status": cmd_status,
        "build": cmd_build,
        "checksum": cmd_checksum,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
