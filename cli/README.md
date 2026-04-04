# cli — Standalone C-Bus CLI Tool

A command-line interface for controlling and monitoring a live C-Bus
network. This tool is a *consumer* of the `pycbus` library — it uses
the exact same public API that the Home Assistant integration uses.

## Status

| | |
|---|---|
| **Maturity** | Alpha — functional, used for development testing |
| **Distribution** | Not published; run from source only |
| **Source** | [cli/](https://github.com/DamianFlynn/ha-cbus/tree/main/cli) in the ha-cbus monorepo |

This CLI is a development and debugging tool. It is not packaged or
distributed separately — it lives alongside the library and integration
in the monorepo.

## Connection

The CLI connects **directly** to C-Bus hardware — no C-Gate middleware
required. The most common setup is a PCI connected via USB with a
[ser2sock](https://github.com/nutechsoftware/ser2sock) container
exposing TCP on port 10001:

```
C-Bus PCI ──USB──▶ ser2sock ◀──TCP :10001── python -m cli
```

A native CNI (5500CN) works the same way — just point `--host` at its
IP address.

## Usage

```bash
python -m cli --help
```

### Live commands (require a C-Bus PCI/CNI)

```bash
# Lighting
python -m cli light on        --host 192.168.1.50 --group 1
python -m cli light off       --host 192.168.1.50 --group 1
python -m cli light ramp      --host 192.168.1.50 --group 3 --level 128 --rate 4
python -m cli light terminate --host 192.168.1.50 --group 3

# Enable Control (switches)
python -m cli switch on  --host 192.168.1.50 --group 10
python -m cli switch off --host 192.168.1.50 --group 10

# Trigger Control (scenes/events)
python -m cli trigger fire --host 192.168.1.50 --group 1 --action 0

# Monitor all C-Bus traffic
python -m cli monitor --host 192.168.1.50

# Query group status
python -m cli status --host 192.168.1.50
```

### Offline commands (no hardware needed)

```bash
# Build a Lighting ON frame
python -m cli build on --group 1

# Build a ramp command
python -m cli build ramp --group 3 --level 128

# Build Enable/Trigger commands
python -m cli build enable-on --group 10
python -m cli build trigger --group 1 --action-selector 0

# Compute/verify checksum
python -m cli checksum 05 38 00 79 01 FF
python -m cli checksum 05 38 00 79 01 FF --verify
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Invalid arguments or usage error |
| `2` | Connection / transport failure |
| `3` | Command rejected by PCI (negative confirmation) |

## Architecture

```
cli/
├── __init__.py      # Package docstring
├── __main__.py      # python -m cli entry point
└── cbus_cli.py      # Argument parsing, command dispatch, async I/O
```

The CLI imports exclusively from the `pycbus` public API:

```python
from pycbus import CbusProtocol, TcpTransport
from pycbus.applications.lighting import lighting_on, lighting_ramp, ...
from pycbus.applications.enable import enable_on, enable_off
from pycbus.applications.trigger import trigger_event
from pycbus.commands import parse_sal_event
```

## Testing

21 CLI tests in `tests/cli/`:

```bash
python -m pytest tests/cli/ -v
```

Tests cover the `build` and `checksum` sub-commands using mocked
argparse namespaces — no hardware or network required.

## Relationship to other components

```
┌─────────────┐     ┌──────────────────────┐
│   cli/      │     │ custom_components/    │
│  (this)     │     │   cbus/              │
│             │     │  (HA integration)    │
└──────┬──────┘     └──────────┬───────────┘
       │                       │
       │   import pycbus       │   import pycbus
       │                       │
       └───────────┬───────────┘
                   │
            ┌──────▼───────┐
            │    pycbus/    │
            │  (library)    │
            └──────────────┘
```

Both the CLI and the HA integration are independent consumers of the
`pycbus` library. The CLI serves as a validation tool: if the CLI
works against real hardware, the library API is correct.
