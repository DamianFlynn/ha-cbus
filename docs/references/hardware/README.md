# Hardware references — the C-Bus units deployed at Deer Crest

The PDFs in the parent `docs/references/` folder are **protocol and application
specs** — how C-Bus talks. The ones in *this* folder are **hardware datasheets
and installation instructions** for the specific units on the Deer Crest network,
gathered 2026-08-17.

They exist to answer the questions the protocol docs can't: per-channel load
rating, minimum load, side-by-side derating, and phase-cut type (leading vs
trailing edge) — i.e. whether a given channel can drive an LED retrofit.

## Deployed at Deer Crest

Extracted from the C-Gate `HOME.xml` export — 8 dimmer packs / 60 channels total.

| Catalog no. | What it is | Qty |
|---|---|---|
| **L5508D1A** | DIN dimmer, 8 channel, 1 A per channel (`DIMDN8`) | 7 |
| **L5504D2A** | DIN dimmer, 4 channel, 2 A per channel (`DIMDN4`) | 1 |
| **L5512RVF** | DIN relay, 12 channel, voltage-free (`RELDN12`) | 2 |
| **5500PACA** | Pascal Automation Controller (`PC_PACA`) | 1 |
| **5031PE** | Light level sensor / luxmeter (`SENLL`) | 1 |
| **5084NL** | Saturn wall switch | 12 |
| **5086NL** | Saturn wall switch | 10 |
| **5500PS** | Network power supply, 350 mA | — |
| **5500CN2** | Ethernet network interface (CNI) Mk II | — |

## Also here, not deployed

- **L5504D2U** — universal (leading *and* trailing edge) dimmer. Held for
  comparison: it is the part that *would* handle trailing-edge LED loads, which
  the installed `D2A`/`D1A` packs cannot.
- **31LCDA** — load correction device brochure, for LED/CFL dimming.
- **SpaceLogic C-Bus digital dimmers** (5504D2D / 5508D1D) — the modern
  replacements for the installed packs.
- **Range catalogues** — Schneider C-Bus product guide, combined E-Series
  catalogue, and the single 4/8-channel dimmer range page.

## Provenance

Every file's source URL and retrieval date is recorded in the vault note that
cites them:
`neocortex/clients/deer-crest/ha-cbus/index.md` § Files.
