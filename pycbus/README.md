# pycbus — Pure-Python Async C-Bus Protocol Library

[![CI](https://github.com/DamianFlynn/ha-cbus/actions/workflows/ci-library.yml/badge.svg)](https://github.com/DamianFlynn/ha-cbus/actions/workflows/ci-library.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green)](../LICENSE)

A pure-Python, fully async protocol library for communicating with
Clipsal C-Bus PCI (serial) and CNI (TCP/IP) interfaces. No C-Gate
middleware required.

## Status

| | |
|---|---|
| **Maturity** | Alpha — functional for lighting, enable, trigger, and measurement applications |
| **Version** | `0.1.0` ([SemVer](https://semver.org/)) |
| **Python** | >= 3.12 (tested on 3.12 and 3.13) |
| **Distribution** | PyPI: `pycbus` (pending first publish) |
| **Source** | [pycbus/](https://github.com/DamianFlynn/ha-cbus/tree/main/pycbus) in the ha-cbus monorepo |

> **Publishing note:** This library must be published to PyPI before the
> Home Assistant integration can be installed, because `manifest.json`
> declares `"requirements": ["pycbus==0.1.0"]`. Home Assistant resolves
> this at runtime via pip.

## Connectivity — direct to hardware, no C-Gate

Unlike the existing `cgate-mqtt` bridge (and many other C-Bus
integrations), pycbus talks **directly** to the PCI or CNI interface
using the native C-Bus serial protocol. The Clipsal C-Gate middleware
is not used and does not need to be installed.

### Connection methods

| Method | Interface | Transport | Typical setup |
|---|---|---|---|
| **TCP** | CNI (5500CN) | `TcpTransport` — async socket to port 10001 | CNI has a built-in Ethernet port |
| **TCP via ser2sock** | PCI (5500PC) | `TcpTransport` — async socket to port 10001 | PCI serial → USB → [ser2sock](https://github.com/nutechsoftware/ser2sock) container exposes TCP |
| **Serial** | PCI (5500PC) | `SerialTransport` — async 9600 8N1 | PCI connected directly via RS-232 / USB-serial adapter |

The most common deployment uses a **PCI + ser2sock**: the PCI is
connected via USB to a machine running a `ser2sock` Docker container
that bridges the serial port to a TCP socket. pycbus then connects to
that socket exactly as it would to a native CNI.

```
┌──────────┐ RS-232/USB  ┌──────────┐  TCP :10001  ┌──────────┐
│  C-Bus   │────────────▶│ ser2sock │◀────────────│  pycbus  │
│  PCI     │             │ container│              │  library │
└──────────┘             └──────────┘              └──────────┘
```

## Architecture

```
┌──────────────┐
│  Consumer     │  HA integration / CLI / your code
└──────┬───────┘
       │  async calls
┌──────▼───────┐
│  Protocol     │  PCI init sequence, SAL framing, state machine
│  protocol.py  │  SMART + MONITOR + IDMON mode (0x79)
└──────┬───────┘
       │
┌──────▼───────┐
│  Transport    │  TcpTransport (CNI :10001) / SerialTransport (PCI 9600 8N1)
│  transport.py │  async read_line / write with CRLF framing
└──────────────┘
```

## Module reference

| Module | Role |
|---|---|
| `__init__.py` | Package metadata, public API exports, `__version__` |
| `checksum.py` | Two's-complement checksum calculation and verification |
| `constants.py` | Protocol enumerations: `ApplicationId` (16+ apps), `LightingCommand`, `EnableCommand`, `TriggerCommand`, `MeasurementCommand`, `MeasurementUnit`, `InterfaceOption1/3`, `RAMP_DURATIONS` |
| `model.py` | Data model: `CbusProject` → `CbusNetwork` → `CbusApplication` → `CbusGroup` |
| `commands.py` | Shared SAL infrastructure: `SalCommand`, `SalEvent`, `parse_sal_event`, status request/reply, backward-compat re-exports |
| `transport.py` | `CbusTransport` protocol + `TcpTransport` (TCP :10001) and `SerialTransport` (9600 8N1) |
| `protocol.py` | `CbusProtocol` state machine — init (SMART+MONITOR+IDMON), SAL send with cycling confirmation codes, monitor event parsing, binary status request/reply |
| `exceptions.py` | `CbusError`, `CbusConnectionError`, `CbusTimeoutError` |
| `cli.py` | Package-level CLI: `build`, `checksum`, `send`, `monitor` sub-commands |
| `applications/__init__.py` | Application registry + shared `build_pm_command` builder |
| `applications/lighting.py` | Lighting (app 0x38): `lighting_on`, `lighting_off`, `lighting_ramp`, `lighting_terminate_ramp` |
| `applications/enable.py` | Enable Control (app 0xCB): `enable_on`, `enable_off` |
| `applications/trigger.py` | Trigger Control (app 0xCA): `trigger_event` |
| `applications/measurement.py` | Measurement (app 0xE4): `MeasurementData`, `parse_measurement_data` (broadcast-only SNEL sensor) |

## Quick start

### Install (once published)

```bash
pip install pycbus
```

### Install from source

```bash
git clone https://github.com/DamianFlynn/ha-cbus.git
cd ha-cbus
pip install -e ".[dev]"
```

### Basic usage

```python
import asyncio
from pycbus import CbusProtocol, TcpTransport

async def main():
    transport = TcpTransport(host="192.168.1.50", port=10001)
    protocol = CbusProtocol(transport)

    await protocol.connect()       # opens socket, runs PCI init
    await protocol.lighting_on(group=1)
    await protocol.lighting_ramp(group=3, level=128, rate=4)
    await protocol.disconnect()

asyncio.run(main())
```

### Offline command building

```python
from pycbus.applications.lighting import lighting_on, lighting_ramp

# Returns the hex SAL frame (no hardware needed)
frame = lighting_on(group=1)
frame = lighting_ramp(group=3, level=128, rate=4)
```

## Testing

150 library tests (no Home Assistant dependency):

```bash
python -m pytest tests/lib/ -v
```

Test coverage by module:
- `test_checksum.py` — 4 tests (algorithm correctness)
- `test_commands.py` — 49 tests (SAL builders, parsers, measurement)
- `test_constants.py` — 28 tests (enums, bitmasks, spec compliance)
- `test_model.py` — 14 tests (dataclass validation)
- `test_protocol.py` — 23 tests (protocol state machine, init sequence)
- `test_transport.py` — 32 tests (TCP, serial, CRLF edge cases)

## CI pipeline (`ci-library.yml`)

Triggered when `pycbus/`, `tests/lib/`, or `pyproject.toml` change.

| Job | Steps |
|---|---|
| **Lint & type-check** | `ruff check` → `ruff format --check` → `mypy --strict` |
| **Test (3.12)** | `pytest tests/lib/ --cov` + upload coverage artifact |
| **Test (3.13)** | `pytest tests/lib/` |

## Versioning and release

| | |
|---|---|
| **Scheme** | [SemVer](https://semver.org/) — `MAJOR.MINOR.PATCH` |
| **Current** | `0.1.0` |
| **Source of truth** | `pyproject.toml` `version` field + `pycbus/__init__.py` `__version__` |

The Home Assistant integration pins `pycbus==<version>` in its
`manifest.json`. Any library release must be published to PyPI before
the corresponding integration version can be installed.

### Publishing to PyPI

```bash
# Build
python -m build

# Upload (requires PyPI credentials)
python -m twine upload dist/*
```

## Dependencies

| Package | Why |
|---|---|
| `pyserial-asyncio` >= 0.6 | Async serial transport for PCI hardware |

No other runtime dependencies. The library is pure Python.

## Protocol reference

The implementation follows these Schneider Electric / Clipsal documents
(available in `docs/references/`):

- *C-Bus Serial Interface User Guide* — transport framing, PCI init, interface options
- *C-Bus Lighting Application* (Chapter 1) — app 0x38 SAL commands
- *C-Bus Trigger Control Application* — app 0xCA SAL commands
- *C-Bus Enable Control Application* — app 0xCB SAL commands
- *C-Bus Measurement Application* — app 0xE4 broadcast format
