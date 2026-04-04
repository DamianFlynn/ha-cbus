# C-Bus — Home Assistant Custom Integration

[![CI](https://github.com/DamianFlynn/ha-cbus/actions/workflows/ci-integration.yml/badge.svg)](https://github.com/DamianFlynn/ha-cbus/actions/workflows/ci-integration.yml)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange)](https://hacs.xyz)

A native Home Assistant custom integration for Clipsal C-Bus home
automation networks. Communicates directly with PCI (serial) or CNI
(TCP/IP) hardware — no C-Gate middleware required.

## Status

| | |
|---|---|
| **Maturity** | Alpha — config flow, coordinator, and three entity platforms working |
| **Version** | `2026.4.0` ([CalVer](https://calver.org/) `YYYY.M.PATCH`) |
| **Distribution** | [HACS](https://hacs.xyz) custom repository |
| **Source** | [custom_components/cbus/](https://github.com/DamianFlynn/ha-cbus/tree/main/custom_components/cbus) |
| **Domain** | `cbus` |
| **IoT class** | `local_push` |

## How it connects — direct to hardware, no C-Gate

This integration talks **directly** to C-Bus PCI/CNI hardware using
the native serial protocol. The Clipsal C-Gate middleware is not used
and does not need to be installed.

| Connection | Hardware | How |
|---|---|---|
| **TCP** | CNI (5500CN) | Connect to the CNI's built-in Ethernet port |
| **TCP via ser2sock** | PCI (5500PC) | PCI serial → USB → [ser2sock](https://github.com/nutechsoftware/ser2sock) container exposes TCP on port 10001 |
| **Serial** | PCI (5500PC) | Direct RS-232 or USB-serial adapter |

The most common setup is a **PCI + ser2sock** container: the PCI is
attached via USB and `ser2sock` bridges the serial port to a TCP
socket. The integration connects to that socket the same way it
would connect to a native CNI.

```
C-Bus PCI ──USB──▶ ser2sock container ◀──TCP :10001── HA (this integration)
```

## Prerequisites

This integration depends on the `pycbus` library:

```json
"requirements": ["pycbus==0.1.0"]
```

Home Assistant resolves this via pip at install time. The library must
be published to PyPI at the pinned version before the integration can
be loaded.

## Installation

### Via HACS (recommended)

1. Open HACS in your Home Assistant instance
2. Go to **Integrations** → **⋮** → **Custom repositories**
3. Add `https://github.com/DamianFlynn/ha-cbus` as an **Integration**
4. Install **C-Bus** from the HACS store
5. Restart Home Assistant
6. Go to **Settings** → **Devices & Services** → **Add Integration** → **C-Bus**

### Manual

Copy `custom_components/cbus/` into your Home Assistant
`custom_components/` directory and restart.

## Configuration

The integration uses a 3-step config flow (no YAML configuration):

1. **Transport** — choose TCP or Serial
2. **Connection** — enter host/port (TCP) or serial device path (serial)
3. **Done** — the integration creates a config entry and connects

Duplicate entries for the same host are detected and rejected.

## Supported platforms

| Platform | C-Bus Application | Entity type | Features |
|---|---|---|---|
| **Light** | Lighting (app 0x38) | `LightEntity` | On/off, brightness (0–255), ramp with duration |
| **Switch** | Enable Control (app 0xCB) | `SwitchEntity` | Binary on/off |
| **Event** | Trigger Control (app 0xCA) | `EventEntity` | Fire-and-forget scene triggers |

### Planned platforms

| Platform | C-Bus Application | Notes |
|---|---|---|
| **Sensor** | Measurement (app 0xE4) | SNEL light-level broadcasts — parser exists in pycbus |
| **Climate** | HVAC Actuator | Future |

## Architecture

```
custom_components/cbus/
├── __init__.py         # async_setup_entry / async_unload_entry
├── config_flow.py      # 3-step UI flow (transport → details → done)
├── const.py            # DOMAIN, transport type constants, PLATFORMS list
├── coordinator.py      # DataUpdateCoordinator: protocol lifecycle,
│                       #   state cache, SAL event dispatch, command proxy
├── entity.py           # CbusEntity base class (device_info, unique_id)
├── light.py            # Lighting platform (brightness + ramp duration)
├── switch.py           # Enable Control platform (binary on/off)
├── event.py            # Trigger Control platform (stateless events)
├── manifest.json       # Integration metadata + pycbus dependency
├── strings.json        # UI strings for config flow
└── translations/
    └── en.json         # English translations
```

### Data flow

```
C-Bus Network
    │
    ▼ TCP :10001 / Serial 9600 8N1
┌──────────────┐
│  pycbus       │  TcpTransport → CbusProtocol (state machine)
└──────┬───────┘
       │ SAL events + state
┌──────▼───────┐
│  Coordinator  │  CbusCoordinator
│               │  - manages connect/disconnect lifecycle
│               │  - caches group state (level per group address)
│               │  - dispatches SAL events to entity callbacks
│               │  - proxies commands from entities to protocol
└──────┬───────┘
       │ state updates
┌──────▼───────┐
│  Entities     │  light.py / switch.py / event.py
│               │  - read state from coordinator cache
│               │  - send commands via coordinator proxy
│               │  - register SAL event listeners
└──────────────┘
```

## Testing

65 integration tests in `tests/integration/`:

```bash
# Requires pytest-homeassistant-custom-component
pip install pytest-homeassistant-custom-component
python -m pytest tests/integration/ -v
```

Test coverage:
- `test_config_flow.py` — 8 tests (all flow steps, duplicate detection, errors)
- `test_coordinator.py` — 22 tests (state cache, SAL dispatch, lifecycle)
- `test_light.py` — 16 tests (on/off, brightness, ramp, state updates)
- `test_switch.py` — 10 tests (on/off, state updates)
- `test_event.py` — 9 tests (trigger events, fire-and-forget)

## CI pipeline (`ci-integration.yml`)

Triggered when `custom_components/`, `pycbus/`, `tests/integration/`,
or `tests/conftest.py` change.

| Job | Steps |
|---|---|
| **Validate** | `ruff check` → `ruff format --check` → `manifest.json` schema check |
| **Test** | `pytest tests/integration/` with `pytest-homeassistant-custom-component` |

## Versioning

| | |
|---|---|
| **Scheme** | [CalVer](https://calver.org/) — `YYYY.M.PATCH` |
| **Current** | `2026.4.0` |
| **Source of truth** | `manifest.json` `version` field |

The integration version follows the Home Assistant release cycle.
Bump the year and month to match the current HA release, increment
the patch for fixes within the same cycle.

The `requirements` field in `manifest.json` pins `pycbus==<version>`.
Any update to the library that changes the integration's behaviour
must be coordinated:

1. Publish the new `pycbus` version to PyPI
2. Update `manifest.json` to pin the new version
3. Release the integration update via HACS

## Relationship to pycbus

This integration is a *consumer* of the `pycbus` library. It does not
import from library internals — only from the public API:

```python
from pycbus import CbusProtocol, TcpTransport, SerialTransport
from pycbus.applications.lighting import lighting_on, lighting_ramp, ...
from pycbus.applications.enable import enable_on, enable_off
from pycbus.commands import parse_sal_event, SalEvent
from pycbus.constants import ApplicationId, LightingCommand
```

The library handles all protocol-level concerns (framing, checksums,
state machine, SAL parsing). The integration handles Home Assistant
concerns (config entries, entity lifecycle, state management, UI).
