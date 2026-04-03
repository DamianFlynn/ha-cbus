"""Data models for C-Bus networks, units, and groups.

C-Bus is organised in a strict hierarchy::

    Project
    └── Network  (0–255, usually just network 254)
        ├── Application  (identified by app ID, e.g. 56 = Lighting)
        │   └── Group  (0–255, each group is a logical load or scene)
        └── Unit  (0–255, each unit is a physical device on the bus)

A *project* is the top-level container exported by C-Gate / Toolkit.
A *network* represents one physical C-Bus cable run (some installations
have multiple networks bridged together).
An *application* is a functional domain (lighting, security, triggers …).
A *group* within an application is the addressable endpoint — this is
what shows up as an entity in Home Assistant.
A *unit* is a physical device (dimmer, relay, keypad) that responds to
commands on one or more groups.

Dataclass validation:
    ``CbusGroup.__post_init__`` enforces the 0–255 range for group
    addresses at construction time to catch configuration import errors
    early.

These models are protocol-agnostic — they describe the *topology*, not
the wire format.  See :mod:`pycbus.commands` for frame construction.

Usage::

    >>> from pycbus.model import CbusGroup, CbusApplication
    >>> lounge = CbusGroup(address=1, name="Lounge Downlights")
    >>> lighting = CbusApplication(app_id=56, name="Lighting",
    ...                            groups={1: lounge})
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CbusGroup:
    """A C-Bus group address within an application.

    A group is the fundamental addressable unit in C-Bus.  All commands
    target a specific group within a specific application.  For the
    Lighting application, a group typically maps to a circuit or a scene.

    Attributes:
        address:  The 8-bit group address (0–255).
        name:     Human-readable label, populated from C-Gate XML import
                  or entered manually during config flow.  Empty string
                  when no import data is available.

    Raises:
        ValueError: If *address* is outside the valid 0–255 range.
    """

    address: int
    name: str = ""

    def __post_init__(self) -> None:
        if not 0 <= self.address <= 255:
            raise ValueError(f"Group address must be 0–255, got {self.address}")


@dataclass
class CbusUnit:
    """A physical C-Bus unit (dimmer, relay, keypad, sensor, etc.).

    Units are the hardware devices on the bus.  Each unit has a unique
    address (0–255) within its network and may service one or more groups.

    The ``groups`` list records which group addresses this unit controls.
    This mapping comes from the ``PP`` (parameter page) values in the
    C-Gate ``GroupAddress`` export and enables Home Assistant to group
    entities under the correct device.

    Attributes:
        address:          The 8-bit unit address on the C-Bus network.
        name:             Human-readable label from C-Gate or Toolkit.
        unit_type:        Device type string (e.g. "L5508D1A" for a dimmer).
        catalog_number:   Schneider Electric catalog / part number.
        serial_number:    Factory serial number (if available).
        firmware_version: Firmware revision string (if available).
        groups:           List of group addresses this unit services.
    """

    address: int
    name: str = ""
    unit_type: str = ""
    catalog_number: str = ""
    serial_number: str = ""
    firmware_version: str = ""
    groups: list[int] = field(default_factory=list)


@dataclass
class CbusApplication:
    """An application on a C-Bus network (lighting, trigger, enable, etc.).

    Each application is identified by a unique 8-bit ``app_id``
    (see :class:`pycbus.constants.ApplicationId`).  The application holds
    a dictionary of groups keyed by group address.

    Attributes:
        app_id: The 8-bit application identifier (e.g. 56 for Lighting).
        name:   Human-readable name (e.g. "Lighting").
        groups: Mapping of group address → :class:`CbusGroup`.
    """

    app_id: int
    name: str = ""
    groups: dict[int, CbusGroup] = field(default_factory=dict)


@dataclass
class CbusNetwork:
    """A C-Bus network with its applications and units.

    Most installations have a single network (commonly network 254, the
    default).  Larger sites may bridge multiple networks together.

    Attributes:
        network_number:    The 8-bit network identifier (0–255).
        name:              Human-readable name (e.g. "HOME").
        interface_type:    Connection method: ``"tcp"`` (CNI) or ``"serial"`` (PCI).
        interface_address: Host:port for TCP, or device path for serial.
        applications:      Mapping of app ID → :class:`CbusApplication`.
        units:             Mapping of unit address → :class:`CbusUnit`.
    """

    network_number: int
    name: str = ""
    interface_type: str = ""
    interface_address: str = ""
    applications: dict[int, CbusApplication] = field(default_factory=dict)
    units: dict[int, CbusUnit] = field(default_factory=dict)


@dataclass
class CbusProject:
    """Top-level C-Bus project containing one or more networks.

    A project corresponds to the XML export from C-Gate (``HOME.xml``)
    or a ``.cbz`` Toolkit archive.  It is the root object passed into
    the config flow for device/entity discovery.

    Attributes:
        name:     Project name (e.g. "HOME").
        networks: Mapping of network number → :class:`CbusNetwork`.
    """

    name: str = ""
    networks: dict[int, CbusNetwork] = field(default_factory=dict)
