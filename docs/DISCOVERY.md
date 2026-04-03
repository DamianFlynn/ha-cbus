# Device Discovery Strategy — ha-cbus

## The Problem

C-Bus is a **command-based** bus, not a **discovery-based** one. Unlike
Zigbee or Z-Wave, there is no standard mechanism for a PCI/CNI to enumerate
all units and group addresses present on the network. The protocol carries
commands addressed to group numbers (0–255) — but the *names* of those
groups exist only in offline project databases.

This means a freshly connected integration sees traffic like
"group 24 set to 180" but has no idea that group 24 is called
"MasterBed Ensuite Mirror".

## Discovery Sources

### 1. C-Gate XML Export (`HOME.xml`)

C-Gate maintains an XML database of every project it has managed. When
exported (or copied from the C-Gate data directory), it contains:

```xml
<Installation>
  <Project>
    <TagName>HOME</TagName>
    <Network>
      <TagName>DeerCrest</TagName>
      <Address>254</Address>
      <NetworkNumber>254</NetworkNumber>
      <Interface>
        <InterfaceType>CNI</InterfaceType>
        <InterfaceAddress>172.16.1.128:10001</InterfaceAddress>
      </Interface>

      <Application>
        <TagName>Lighting</TagName>
        <Address>56</Address>
        <Group>
          <TagName>Bed1 Walk In</TagName>
          <Address>1</Address>
        </Group>
        <Group>
          <TagName>Kitchen Cabinets</TagName>
          <Address>74</Address>
        </Group>
        <!-- ... -->
      </Application>

      <Application>
        <TagName>Trigger Control</TagName>
        <Address>202</Address>
        <Group>
          <TagName>Trigger Group 1</TagName>
          <Address>1</Address>
          <Level Value="6">
            <TagName>Action Selector 6</TagName>
          </Level>
          <!-- ... -->
        </Group>
      </Application>

      <Unit>
        <TagName>DIM1A-01</TagName>
        <Address>3</Address>
        <UnitType>DIMDN8</UnitType>
        <UnitName>DIM1A-01</UnitName>
        <CatalogNumber>L5508D1A</CatalogNumber>
        <SerialNumber>100242.2281</SerialNumber>
        <FirmwareVersion>1.3.0</FirmwareVersion>
        <PP Name="GroupAddress"
            Value="0x1 0x2 0x3 0x4 0x5 0x6 0x7 0x8 ..."/>
      </Unit>
    </Network>
  </Project>
</Installation>
```

**What we extract:**

| Element | Data | Use |
|---|---|---|
| `Project/TagName` | Project name | Config entry title |
| `Network/TagName` | Network name | Device grouping |
| `Network/Address` | Network number | Protocol addressing |
| `Network/Interface` | CNI host:port | Auto-fill connection |
| `Application/TagName` | App name | Entity platform routing |
| `Application/Address` | App ID (56, 202…) | Protocol addressing |
| `Group/TagName` | **Group label** | Entity friendly name |
| `Group/Address` | Group number | Protocol addressing |
| `Level/TagName` | Trigger action name | Event metadata |
| `Unit/TagName` | Unit label | HA device name |
| `Unit/UnitType` | Hardware type | Device model info |
| `Unit/CatalogNumber` | Part number | Device model info |
| `Unit/SerialNumber` | Serial | Device unique ID |
| `Unit/PP[GroupAddress]` | Channel→group map | Unit↔group linkage |

**Unit-to-group mapping** is critical: the `GroupAddress` parameter on each
Unit tells us which physical channels drive which group addresses. This lets
us create proper HA devices (one per unit) with entities (one per group)
underneath.

### 2. CBZ Project File (C-Bus Toolkit)

CBZ files are ZIP archives created by the C-Bus Toolkit (Windows
application). They contain the full project database including:

- All network, application, group, and unit definitions
- Group labels and descriptions
- Unit parameters and addressing
- Scene/schedule definitions

The integration should accept `.cbz` file upload during config flow and
extract the same label data as the XML path.

**Implementation**: unzip in memory → parse the contained XML/database
files → extract the same fields as the C-Gate XML path.

### 3. Manual Configuration

For users without C-Gate or Toolkit exports, the config flow offers manual
entry:

- Network number (default 254)
- For each group: application ID, group number, user-chosen label
- Groups can be added/removed via the integration options flow

### 4. Auto-Detection from Bus Traffic (Future)

While C-Bus has no enumeration protocol, we *can* observe:

- **Level status responses** reveal which group addresses are active
  (non-zero or responding) on each application.
- **SAL traffic** from wall switches reveals which groups are in use.

A future enhancement could offer "we detected activity on these groups —
would you like to add them?" This would be a Platinum quality-scale feature.

---

## Config Flow UX

### Initial Setup

```
┌─────────────────────────────────────┐
│  C-Bus Integration Setup            │
│                                     │
│  Connection Type:                   │
│  ○ TCP (CNI)                        │
│  ○ Serial (PCI/USB)                 │
│                                     │
│  [Next]                             │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  Connection Details                 │
│                                     │
│  Host: [172.16.1.128]               │
│  Port: [10001]                      │
│                                     │
│  [Test Connection]  [Next]          │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  Import Device Labels (Optional)    │
│                                     │
│  ○ Import C-Gate XML (.xml)         │
│  ○ Import Toolkit Project (.cbz)    │
│  ○ Skip — I'll add groups manually  │
│                                     │
│  [Upload File]  [Next]              │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  Import Summary                     │
│                                     │
│  Project: HOME                      │
│  Network: DeerCrest (254)           │
│  Lighting groups: 76                │
│  Trigger groups: 1                  │
│  Enable groups: 0                   │
│  Units: 35                          │
│                                     │
│  [Finish]                           │
└─────────────────────────────────────┘
```

### Options Flow (Post-Setup)

- Re-import labels from a new XML/CBZ file
- Add/remove groups manually
- Change connection parameters (reconfigure flow)

---

## Entity Naming Strategy

### With Import

Entities receive friendly names directly from the import data:

| Source Field | HA Property | Example |
|---|---|---|
| `Group/TagName` | `name` | "Kitchen Cabinets" |
| `Unit/TagName` | `device.name` | "DIM1A-01" |
| `Unit/CatalogNumber` | `device.model` | "L5508D1A" |
| `Unit/SerialNumber` | `device.serial_number` | "100242.2281" |
| `Network/TagName` | `device.suggested_area` | "DeerCrest" |

Entity unique ID format: `cbus_{network}_{app}_{group}`  
Example: `cbus_254_56_74` → Kitchen Cabinets light

### Without Import

Fallback naming uses the addressing scheme:

| Property | Format | Example |
|---|---|---|
| Entity name | `C-Bus Light {network}/{group}` | "C-Bus Light 254/74" |
| Device name | `C-Bus Group {network}/{group}` | "C-Bus Group 254/74" |

Users can rename entities in the HA UI at any time.

### Unit-to-Device Mapping

When import data is available, we create proper HA device entries:

```
Device: "DIM1A-01" (L5508D1A, S/N 100242.2281)
├── Light: "Bed1 Walk In"        (group 1)
├── Light: "Bed1 Roof"           (group 2)
├── Light: "Bed1 Ensuite Mirror" (group 3)
├── Light: "Bed1 Ensuite Roof"   (group 4)
├── Light: "Bed1 Lockers"        (group 5)
├── Light: "Bed2 Lockers"        (group 6)
├── Light: "Bed2 Roof"           (group 7)
└── Light: "Upstairs Hall Roof"  (group 8)
```

The `GroupAddress` PP value on each Unit (`0x1 0x2 0x3 …`) maps
physical channels to group addresses — channel 1 drives group 1, channel 2
drives group 2, etc. Values of `0xFF` indicate unused channels.

Without import data, each group becomes its own device (since we don't know
which unit drives it).

---

## Data Storage

Imported labels are stored in the config entry's `data` dict:

```python
{
    "transport": "tcp",
    "host": "172.16.1.128",
    "port": 10001,
    "network": 254,
    "project_name": "HOME",
    "network_name": "DeerCrest",
    "groups": {
        "56": {
            "1": {"name": "Bed1 Walk In"},
            "74": {"name": "Kitchen Cabinets"},
            ...
        },
        "202": {
            "1": {"name": "Trigger Group 1", "levels": {
                "0": "Action Selector 0",
                "1": "Action Selector 1",
                ...
            }}
        }
    },
    "units": {
        "3": {
            "name": "DIM1A-01",
            "type": "DIMDN8",
            "catalog": "L5508D1A",
            "serial": "100242.2281",
            "groups": [1, 2, 3, 4, 5, 6, 7, 8]
        },
        ...
    }
}
```

This keeps the integration self-contained — no external files needed after
initial import.
