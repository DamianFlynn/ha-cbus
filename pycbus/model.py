"""Data models for C-Bus networks, units, and groups."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CbusGroup:
    """A C-Bus group address within an application."""

    address: int
    name: str = ""

    def __post_init__(self) -> None:
        if not 0 <= self.address <= 255:
            raise ValueError(f"Group address must be 0–255, got {self.address}")


@dataclass
class CbusUnit:
    """A physical C-Bus unit (dimmer, relay, keypad, etc.)."""

    address: int
    name: str = ""
    unit_type: str = ""
    catalog_number: str = ""
    serial_number: str = ""
    firmware_version: str = ""
    groups: list[int] = field(default_factory=list)


@dataclass
class CbusApplication:
    """An application on a C-Bus network (lighting, trigger, etc.)."""

    app_id: int
    name: str = ""
    groups: dict[int, CbusGroup] = field(default_factory=dict)


@dataclass
class CbusNetwork:
    """A C-Bus network with its applications and units."""

    network_number: int
    name: str = ""
    interface_type: str = ""
    interface_address: str = ""
    applications: dict[int, CbusApplication] = field(default_factory=dict)
    units: dict[int, CbusUnit] = field(default_factory=dict)


@dataclass
class CbusProject:
    """Top-level C-Bus project containing networks."""

    name: str = ""
    networks: dict[int, CbusNetwork] = field(default_factory=dict)
