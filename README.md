# ha-cbus — Native Home Assistant Integration for Clipsal C-Bus

[![License](https://img.shields.io/github/license/DamianFlynn/ha-cbus)](LICENSE)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange)](https://hacs.xyz)

A native [Home Assistant](https://www.home-assistant.io/) integration for
[Clipsal C-Bus](https://www.clipsal.com/products/c-bus) home automation —
communicating directly with PCI/CNI hardware over serial or TCP. No C-Gate
server required.

## Status

**Early development** — not yet functional. See [docs/PRD.md](docs/PRD.md)
for goals and [docs/DESIGN.md](docs/DESIGN.md) for architecture.

## Features (Planned)

- **Direct PCI/CNI protocol** — no dependency on C-Gate, Java, or MQTT
- **Config-flow UI** — onboard via the HA integrations page
- **Device import** — import group labels from C-Gate XML or Toolkit CBZ files
- **Lighting** (app 56) — on/off, brightness, ramp rates
- **Triggers** (app 202) — scene triggers as HA events
- **Enable Control** (app 203) — binary switches
- **Extensible** — application registry supports future apps (climate, fan, sensors…)

## Architecture

```
┌─────────────────────────┐     ┌──────────────────────┐
│  Home Assistant          │     │  C-Bus Network        │
│                          │     │                       │
│  custom_components/cbus  │◄───►│  CNI (TCP :10001)     │
│         │                │     │  PCI (USB serial)     │
│      pycbus              │     │                       │
└─────────────────────────┘     └──────────────────────┘
```

Two packages in one repo:

| Package | Purpose |
|---|---|
| `pycbus` | Pure-Python async C-Bus PCI protocol library |
| `custom_components/cbus` | Home Assistant integration |

## Installation

> Not yet available — coming soon via HACS.

## Documentation

- [Product Requirements](docs/PRD.md)
- [Architecture & Design](docs/DESIGN.md)
- [Device Discovery Strategy](docs/DISCOVERY.md)
- [Protocol References](docs/references/) — C-Bus Serial Interface guides and application chapters

## License

[Apache-2.0](LICENSE)
