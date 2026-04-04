"""Tests for pycbus data model validation.

Verifies that the dataclass topology models enforce constraints
correctly and handle edge cases in group/unit/network addressing.

Covers:
    - CbusGroup address range validation (0-255).
    - CbusGroup boundary values (0 and 255).
    - CbusUnit default field values.
    - CbusApplication group dictionary operations.
    - CbusNetwork nested structure.
    - CbusProject top-level container.
"""

from __future__ import annotations

import pytest

from pycbus.model import (
    CbusApplication,
    CbusGroup,
    CbusNetwork,
    CbusProject,
    CbusUnit,
)


class TestCbusGroup:
    """Tests for CbusGroup dataclass validation."""

    def test_valid_group_address(self) -> None:
        """Group addresses 0-255 should be accepted."""
        group = CbusGroup(address=100, name="Test Group")
        assert group.address == 100
        assert group.name == "Test Group"

    def test_group_address_zero(self) -> None:
        """Boundary: address 0 is valid (used for broadcast in some apps)."""
        group = CbusGroup(address=0)
        assert group.address == 0

    def test_group_address_max(self) -> None:
        """Boundary: address 255 is valid."""
        group = CbusGroup(address=255)
        assert group.address == 255

    def test_group_address_negative_rejected(self) -> None:
        """Negative addresses must be rejected."""
        with pytest.raises(ValueError, match="0-255"):
            CbusGroup(address=-1)

    def test_group_address_overflow_rejected(self) -> None:
        """Addresses above 255 must be rejected."""
        with pytest.raises(ValueError, match="0-255"):
            CbusGroup(address=256)

    def test_group_default_name_empty(self) -> None:
        """Name defaults to empty string when not provided."""
        group = CbusGroup(address=1)
        assert group.name == ""


class TestCbusUnit:
    """Tests for CbusUnit dataclass."""

    def test_unit_defaults(self) -> None:
        """All optional fields should default to empty/empty-list."""
        unit = CbusUnit(address=12)
        assert unit.address == 12
        assert unit.name == ""
        assert unit.unit_type == ""
        assert unit.catalog_number == ""
        assert unit.serial_number == ""
        assert unit.firmware_version == ""
        assert unit.groups == []

    def test_unit_with_groups(self) -> None:
        """Unit should store its associated group addresses."""
        unit = CbusUnit(address=12, name="Kitchen Dimmer", groups=[1, 2, 3])
        assert unit.groups == [1, 2, 3]

    def test_unit_groups_are_independent(self) -> None:
        """Each unit instance should have its own groups list (no sharing)."""
        unit_a = CbusUnit(address=1)
        unit_b = CbusUnit(address=2)
        unit_a.groups.append(10)
        assert unit_b.groups == []


class TestCbusApplication:
    """Tests for CbusApplication dataclass."""

    def test_application_with_groups(self) -> None:
        """Application should hold a dict of groups keyed by address."""
        g1 = CbusGroup(address=1, name="Lounge")
        g2 = CbusGroup(address=2, name="Kitchen")
        app = CbusApplication(app_id=56, name="Lighting", groups={1: g1, 2: g2})
        assert app.groups[1].name == "Lounge"
        assert app.groups[2].name == "Kitchen"
        assert len(app.groups) == 2

    def test_application_empty_groups(self) -> None:
        """Application with no groups should have an empty dict."""
        app = CbusApplication(app_id=202, name="Trigger")
        assert app.groups == {}


class TestCbusNetwork:
    """Tests for CbusNetwork dataclass."""

    def test_network_with_applications_and_units(self) -> None:
        """Network should contain both applications and units."""
        app = CbusApplication(app_id=56, name="Lighting")
        unit = CbusUnit(address=12, name="Dimmer")
        net = CbusNetwork(
            network_number=254,
            name="HOME",
            interface_type="tcp",
            interface_address="192.168.1.50:10001",
            applications={56: app},
            units={12: unit},
        )
        assert net.network_number == 254
        assert net.applications[56].name == "Lighting"
        assert net.units[12].name == "Dimmer"


class TestCbusProject:
    """Tests for CbusProject top-level container."""

    def test_project_with_network(self) -> None:
        """Project should contain networks keyed by number."""
        net = CbusNetwork(network_number=254, name="HOME")
        project = CbusProject(name="My Home", networks={254: net})
        assert project.name == "My Home"
        assert project.networks[254].name == "HOME"

    def test_project_empty(self) -> None:
        """Empty project should be constructable (manual config starts empty)."""
        project = CbusProject()
        assert project.name == ""
        assert project.networks == {}
