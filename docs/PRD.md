# Product Requirements Document — ha-cbus

## Problem Statement

Clipsal C-Bus is a mature Australian home-automation bus widely deployed in
residential and commercial installations.  Today, the only path into
Home Assistant (HA) is via **Schneider Electric's C-Gate server** — a
closed-source Java application that exposes a text-based TCP protocol.

This dependency creates several pain points:

| Pain point | Impact |
|---|---|
| C-Gate is a black-box Java process | Extra service to run, monitor, and update |
| No native HA config-flow | Manual YAML configuration, no UI onboarding |
| Limited application support | Most bridges only handle lighting (app 56) |
| MQTT bridge adds a second hop | C-Bus → C-Gate → MQTT → HA increases latency and failure modes |
| No over-the-wire device enumeration | Users must label devices manually or import from Toolkit |

### Existing Solutions Analysed

| Project | Language | Protocol | Limitations |
|---|---|---|---|
| **cgate-mqtt** (DamianFlynn) | Node.js | C-Gate TCP | Requires C-Gate; MQTT-only; single network/app |
| **Weslide/cbus** | Python | C-Gate TCP | Requires C-Gate; limited to app 56; stale |
| **homebridge-cbus** | Node.js | C-Gate TCP | Requires C-Gate; Homebridge only |
| **micolous/cbus (libcbus)** | Python | **Direct PCI serial** | Outdated (Python 3.7); threading in asyncio; LGPL-3.0; unmaintained since 2020 |
| **Elve C-Bus.cs** (DamianFlynn) | C# | Direct PCI serial | Proprietary host; not HA; but complete protocol reference |

The micolous/cbus library proved that direct PCI communication is feasible in
pure Python with asyncio. However, its code quality, licensing (LGPL-3.0), and
age make it unsuitable for direct integration into HA core.

## Goals

1. **Eliminate C-Gate** — communicate directly with C-Bus PCI/CNI hardware
   over serial (USB) or TCP.
2. **Native HA integration** — full config-flow UI, coordinator pattern,
   entity platforms, diagnostics.
3. **HACS first, HA core later** — ship quickly via HACS, then pursue an
   upstream core submission at Gold quality-scale or above.
4. **Clean-room protocol library** — Apache-2.0 licensed `pycbus` package
   with no LGPL encumbrance, suitable for HA core bundling.
5. **Modern Python** — 3.12+, full type hints, dataclasses, pure asyncio
   (no threads).

## Non-Goals (for MVP)

- Applications beyond Lighting (56), Trigger (202), and Enable (203).
- Automatic over-the-wire device enumeration (C-Bus has no such mechanism).
- C-Gate compatibility or fallback mode.
- Cloud connectivity.

Post-MVP applications are documented in the phased roadmap below.

## MVP Scope

### Entity Platforms (MVP)

| Platform | C-Bus Application | Capabilities |
|---|---|---|
| **Light** | 56 (Lighting) | On / Off / Brightness (0-255) / Ramp rates |
| **Event** | 202 (Trigger) | Scene triggers fired as HA events |
| **Switch** | 203 (Enable) | On / Off binary control |

### Transports

| Transport | Hardware | Connection |
|---|---|---|
| **TCP** | CNI (C-Bus Network Interface) | `<host>:10001` |
| **Serial** | PCI (PC Interface, USB) | `/dev/ttyUSBx` @ 9600 8N1 |

Both transports share a single `CbusProtocol` implementation behind an async
transport abstraction. TCP will be the primary development/test target because
it does not require physical hardware on the dev machine.

### Device Discovery / Import

C-Bus groups have no self-describing names. The integration must support:

1. **C-Gate XML import** — parse `HOME.xml` / `NET_*.xml` exports.
2. **CBZ project import** — extract unit/group labels from C-Bus Toolkit
   backup files.
3. **Manual configuration** — user enters network, application, group, label
   via the config-flow UI.

### Quality Scale Target

| Tier | Target | Purpose |
|---|---|---|
| **Bronze** | MVP / HACS release | Config flow, basic entities, tests |
| **Silver** | Stability | Reauthentication, diagnostics, reconfigure |
| **Gold** | HA core submission | Entity translations, exception handling, repair flows |
| **Platinum** | Stretch | Dynamic device discovery (if protocol permits) |

## Success Criteria

- A user can install via HACS, onboard via config-flow (TCP or serial), import
  device labels, and control C-Bus lights from the HA UI with < 200 ms
  round-trip latency.
- Trigger events appear in the HA event bus within one C-Bus scan cycle.
- No dependency on C-Gate, Java, or any external bridge process.

## Constraints

- **Licensing**: all code Apache-2.0. No LGPL, GPL, or proprietary
  dependencies.
- **Protocol documentation**: the C-Bus Serial Interface Guide and Quick Start
  Guide are the canonical references; supplemented by field knowledge from
  Elve and micolous implementations.
- **Hardware available for testing**: CNI on the home network (TCP), PCI via
  USB on the HA host.

## Application Roadmap

Complete C-Bus Serial Application documentation has been obtained
(`docs/references/`). This enables a phased rollout beyond MVP:

### Phase 1 — MVP

| App ID | Application | HA Platform | Chapter |
|---|---|---|---|
| 56 | Lighting | `light` | Ch 02 |
| 202 | Trigger Control | `event` | Ch 07 |
| 203 | Enable Control | `switch` | Ch 08 |

### Phase 2 — Environmental

| App ID | Application | HA Platform | Chapter |
|---|---|---|---|
| — | Temperature Broadcast | `sensor` | Ch 09 |
| — | Air Conditioning | `climate` | Ch 25 |
| — | Ventilation | `fan` | Ch 10 |
| — | HVAC Actuator | `climate` | Ch 36 |

### Phase 3 — Metering & Measurement

| App ID | Application | HA Platform | Chapter |
|---|---|---|---|
| — | Metering | `sensor` | Ch 06 |
| — | Measurement | `sensor` | Ch 28 |
| — | Error Reporting | diagnostics | Ch 34 |

### Phase 4 — Specialty

| App ID | Application | HA Platform | Chapter |
|---|---|---|---|
| 208 | Security | `alarm_control_panel` | Ch 05 |
| — | Access Control | `lock` / `event` | Ch 11 |
| — | Irrigation | `valve` | Ch 26 |
| — | Pools/Spas/Ponds/Fountains | `switch` / `sensor` | Ch 31 |
| — | Clock & Timekeeping | `sensor` / service | Ch 23 |
| — | Media Transport Control | `media_player` | Ch 21 |
| — | Telephony | `sensor` | Ch 24 |

## Reference Resources

### Protocol Documentation (in `docs/references/`)

- C-Bus Serial Interface User Guide — definitive framing & protocol reference
- C-Bus Quick Start Guide — Serial Protocols (2003)
- C-Bus Quick Start Guide
- C-Bus Interface Requirements
- C-Bus Basic Training Manual vol 1
- Chapters 00–36 — complete SAL command definitions for all 16 applications

### External

- **C-Gate Server & Toolkit downloads** —
  <https://www.se.com/au/en/product/5500CN2/network-interface-cbus-control-and-management-system-v2-din/>
  (Schneider Electric Australia — firmware, C-Gate, Toolkit installers).
