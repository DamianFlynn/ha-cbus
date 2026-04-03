# Architecture & Design — ha-cbus

## Repository Layout

```
ha-cbus/
├── docs/                          # PRD, design docs, protocol PDFs
├── pycbus/                        # Standalone protocol library (pip-installable)
│   ├── __init__.py
│   ├── protocol.py                # CbusProtocol — packet encode/decode, state machine
│   ├── transport.py               # Async TCP and serial transports
│   ├── commands.py                # SAL / CAL command builders
│   ├── constants.py               # Opcodes, application IDs, ramp rates
│   ├── applications/              # Per-application SAL definitions
│   │   ├── __init__.py            # Application registry
│   │   ├── lighting.py            # App 56 — SAL commands, ramp rates
│   │   ├── trigger.py             # App 202 — trigger events
│   │   ├── enable.py              # App 203 — enable/disable
│   │   └── ...                    # Future apps added per-file
│   ├── checksum.py                # Two's-complement checksum
│   └── model.py                   # Dataclasses: Group, Unit, Network, Level, etc.
├── custom_components/
│   └── cbus/                      # Home Assistant integration
│       ├── __init__.py            # async_setup_entry
│       ├── manifest.json
│       ├── config_flow.py         # UI onboarding (TCP / serial / import)
│       ├── coordinator.py         # DataUpdateCoordinator bridging pycbus ↔ HA
│       ├── light.py               # LightEntity — app 56
│       ├── switch.py              # SwitchEntity — app 203 enable
│       ├── event.py               # EventEntity — app 202 triggers
│       ├── entity.py              # CbusEntity base class
│       ├── strings.json           # UI translations
│       └── translations/
│           └── en.json
├── tests/
│   ├── test_protocol.py
│   ├── test_commands.py
│   ├── test_checksum.py
│   ├── test_config_flow.py
│   └── conftest.py
├── pyproject.toml                 # pycbus build config
├── hacs.json                      # HACS metadata
└── README.md
```

Two packages live in one repo:

| Package | Purpose | Install target |
|---|---|---|
| `pycbus` | Pure-Python C-Bus PCI protocol library | `pip install pycbus` (PyPI) |
| `custom_components/cbus` | Home Assistant integration | HACS / HA core |

The HA integration depends on `pycbus` (declared in `manifest.json`
`requirements`). This mirrors the HA pattern used by integrations like
`pymodbus` → Modbus, `aiohomekit` → HomeKit, etc.

---

## 1. Protocol Library — `pycbus`

### 1.1 Transport Abstraction

```
┌──────────────┐
│  CbusProtocol│  ← single implementation
└──────┬───────┘
       │ read_packet() / write_packet()
       ▼
┌──────────────┐     ┌──────────────┐
│  TcpTransport│     │SerialTransport│
│  (CNI :10001)│     │(PCI /dev/ttyX)│
└──────────────┘     └──────────────┘
```

Both transports implement the same async interface:

```python
class CbusTransport(Protocol):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def read(self) -> bytes: ...
    async def write(self, data: bytes) -> None: ...
    @property
    def connected(self) -> bool: ...
```

- **TcpTransport** — `asyncio.open_connection(host, 10001)`
- **SerialTransport** — `serial_asyncio.open_serial_connection(url, 9600, 8N1)`

### 1.2 PCI Initialisation Sequence

After transport connect, `CbusProtocol` runs the init handshake:

```
Step  Tx (hex)             Purpose
───── ──────────────────── ────────────────────────────────
  1   ~~~\r                Reset PCI to normal mode
  2   A3 21 00 38 xx\r     Set Application Address 1 = 0x38 (app 56, lighting)
  3   A3 42 00 0E xx\r     Interface Options #3: LOCAL_SAL + PUN + EXSTAT
  4   A3 30 00 59 xx\r     Interface Options #1: CONNECT + SRCHK + SMART + MONITOR + IDMON
```

Where `xx` is the checksum byte. Each step waits for `g#` (positive
confirmation) before proceeding.

### 1.3 Checksum Algorithm

```python
def checksum(data: bytes) -> int:
    """C-Bus two's-complement checksum."""
    return ((~sum(data) & 0xFF) + 1) & 0xFF
```

Applied to all transmitted command bytes (excluding the framing `\` prefix and
`\r` suffix). On received packets with SRCHK enabled, the last byte is the
checksum — verify by summing all bytes including it; result must be 0x00.

### 1.4 Packet Framing

| Direction | Prefix | Suffix | Checksum |
|---|---|---|---|
| Tx (command) | `\` | `\r` | Appended before `\r` |
| Rx (from PCI) | none | `\r\n` | Last byte (verify) |

Confirmation codes from PCI:

| Code | Meaning |
|---|---|
| `g` | Positive — command accepted (followed by `#` or `.`) |
| `!` | Negative — checksum error or malformed |
| `#` | Ready for next command |
| `.` | Busy — wait and retry |

### 1.5 SAL Commands (Lighting — App 56)

All commands use **Point-to-Multipoint** framing (DAT = `0x05`).

| Command | SAL Opcode | Payload |
|---|---|---|
| **ON** | `0x79` | `05 38 00 79 <group> FF xx` |
| **OFF** | `0x01` | `05 38 00 01 <group> xx` |
| **RAMP** | `0x02`–`0x12` (rate) | `05 38 00 <rate> <group> <level> xx` |
| **TERMINATE RAMP** | `0x09` | `05 38 00 09 <group> xx` |

Ramp rate opcodes encode duration:

| Opcode | Duration |
|---|---|
| `0x02` | 0 s (instant) |
| `0x0A` | 4 s |
| `0x12` | 8 s |
| `0x1A` | 12 s |
| `0x22` | 20 s |
| `0x2A` | 30 s |
| `0x32` | 40 s |
| `0x3A` | 60 s |
| `0x42` | 90 s |
| `0x4A` | 120 s |
| `0x52` | 180 s |
| `0x5A` | 300 s |
| `0x62` | 420 s |
| `0x6A` | 600 s |
| `0x72` | 900 s |
| `0x7A` | 1020 s (17 min) |

### 1.6 Trigger Commands (App 202)

Triggers use application `0xCA` (202). SAL opcodes:

| Command | Opcode | Payload |
|---|---|---|
| **TRIGGER_MIN** | `0x02` | `05 CA 00 02 <group> 00 xx` |
| **TRIGGER_MAX** | `0x79` | `05 CA 00 79 <group> FF xx` |
| **TRIGGER_EVENT** | `0x02` | group + action level |

Triggers are typically received (not sent) and mapped to HA events.

### 1.6a Application Registry

With full protocol documentation for all 16 C-Bus applications
(`docs/references/Chapter *`), `pycbus` uses an extensible application
registry rather than hardcoding SAL opcodes per-application.

```python
@dataclass(frozen=True)
class CbusApplication:
    """Defines a C-Bus application's SAL command set."""
    app_id: int            # e.g. 56, 202, 203
    name: str              # human-readable
    sal_commands: dict[str, int]   # command_name → opcode
    has_level: bool        # True if commands carry a level byte (0–255)

# Registry — populated from protocol docs, extensible per-file
APPLICATION_REGISTRY: dict[int, CbusApplication] = {}

def register_application(app: CbusApplication) -> None:
    APPLICATION_REGISTRY[app.app_id] = app
```

Each `pycbus/applications/<name>.py` file registers its app on import.
New applications (climate, fan, sensor, etc.) are added by dropping a
file — no changes to core protocol code required.

**Known application IDs** (from docs/references):

| App ID | Hex | Application | Chapter |
|---|---|---|---|
| 56 | 0x38 | Lighting | Ch 02 |
| 202 | 0xCA | Trigger Control | Ch 07 |
| 203 | 0xCB | Enable Control | Ch 08 |
| 208 | 0xD0 | Security | Ch 05 |
| — | — | Temperature Broadcast | Ch 09 |
| — | — | Ventilation | Ch 10 |
| — | — | Access Control | Ch 11 |
| — | — | Media Transport | Ch 21 |
| — | — | Clock & Timekeeping | Ch 23 |
| — | — | Telephony | Ch 24 |
| — | — | Air Conditioning | Ch 25 |
| — | — | Irrigation | Ch 26 |
| — | — | Measurement | Ch 28 |
| — | — | Metering | Ch 06 |
| — | — | Pools/Spas/Ponds | Ch 31 |
| — | — | Error Reporting | Ch 34 |
| — | — | HVAC Actuator | Ch 36 |

> App IDs marked `—` will be filled in as each chapter PDF is reviewed
> during implementation of that phase.

### 1.7 Level Status (Monitoring)

With `MONITOR` + `EXSTAT` enabled, the PCI streams level-status replies:

```
Header: D8 38 00          (Point-to-Multipoint, app 56, network-wide)
Coding: 07 or 47          (0x07 = binary, 0x47 = extended)
Status: E0 <b1> <b2> ...  (start group 0, two levels per status pair)
     or C0 <b1> <b2> ...  (continuation block)
```

Each pair of nibbles represents the brightness level (0x00–0xFF) for
consecutive group addresses.

### 1.8 State Machine

```
                  ┌─────────┐
       connect()  │CONNECTING│
      ┌──────────►│         │
      │           └────┬────┘
      │                │ transport ready
      │           ┌────▼────┐
      │           │  RESET  │  send ~~~
      │           └────┬────┘
      │                │ got #
      │           ┌────▼────┐
      │           │  INIT   │  send address/options
      │           └────┬────┘
      │                │ all g# confirmed
      │           ┌────▼────┐
      │           │  READY  │  normal operation
      │           └────┬────┘
      │                │ error / disconnect
      │           ┌────▼────┐
      │           │  RETRY  │  backoff → reconnect
      │           └────┬────┘
      │                │
      └────────────────┘
```

---

## 2. Home Assistant Integration — `custom_components/cbus`

### 2.1 Integration Pattern

```
Config Flow  →  async_setup_entry()  →  CbusCoordinator  →  Entity Platforms
                                             │
                                        pycbus.CbusProtocol
                                             │
                                     TcpTransport / SerialTransport
```

### 2.2 Config Flow

**Step 1 — Connection type**: TCP or Serial  
**Step 2 — Connection details**: host:port or serial device path  
**Step 3 — Device import** (optional): upload C-Gate XML / CBZ file, or skip  
**Step 4 — Confirm**: unique ID = `cbus_<network>` (derived from PCI identity)

### 2.3 Coordinator

`CbusCoordinator` extends `DataUpdateCoordinator`:

- Owns the `CbusProtocol` instance.
- On startup: connect → init → request level status for all groups.
- Pushes real-time SAL events to entities via `async_set_updated_data()`.
- Periodically polls full level status as a heartbeat/sync fallback.
- Handles reconnection with exponential backoff.

### 2.4 Entity Model

#### Light (app 56)

```python
class CbusLight(CbusEntity, LightEntity):
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    # brightness: 0–255 maps directly to C-Bus level
```

- `async_turn_on(brightness, transition)` → RAMP command (pick closest rate).
- `async_turn_off(transition)` → RAMP to 0 or OFF command.
- State updated from SAL monitoring stream.

#### Event (app 202)

```python
class CbusTriggerEvent(CbusEntity, EventEntity):
    _attr_event_types = ["trigger"]
```

- Fires `event_type="trigger"` with `group` and `level` in event data.
- No controllable state — receive-only entity.

### 2.5 Device Registry

Each C-Bus **unit** (dimmer, relay, input) becomes an HA device.  
Each **group address** becomes an entity under that device.

When labels are imported, units and groups get friendly names. Without import,
entities use `C-Bus Light <network>/<group>` naming.

---

## 3. Quality Scale Roadmap

### Bronze (MVP — HACS release)

- [ ] Config flow with TCP and serial options
- [ ] `async_setup_entry` / `async_unload_entry`
- [ ] Light entity with brightness + ramp (app 56)
- [ ] Switch entity for enable control (app 203)
- [ ] Event entity for triggers (app 202)
- [ ] Application registry in pycbus with extensible per-app SAL definitions
- [ ] Unit tests for protocol, checksum, config flow
- [ ] `manifest.json`, `hacs.json`, `strings.json`
- [ ] Basic README and setup instructions

### Silver

- [ ] Reauthentication flow
- [ ] Diagnostics (`async_get_config_entry_diagnostics`)
- [ ] Reconfigure flow (change host/port)
- [ ] Stale data handling + entity availability
- [ ] Log-only exceptions for runtime errors (no unhandled crashes)

### Gold (HA core submission)

- [ ] Entity translations (all strings in `strings.json`)
- [ ] Strict exception handling at integration boundaries
- [ ] Repair flows for common issues (connection lost, wrong port)
- [ ] Full entity category annotations
- [ ] Integration test coverage ≥ 80%

### Platinum (stretch)

- [ ] Dynamic discovery via PCI identify commands (if feasible)
- [ ] Automatic entity creation on new group detection
- [ ] Performance telemetry
