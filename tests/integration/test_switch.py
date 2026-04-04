"""Tests for the C-Bus switch platform.

Tests verify CbusSwitch entity behaviour using mock coordinators,
without requiring a real C-Bus connection.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.cbus.switch import CbusSwitch
from pycbus.constants import ApplicationId

# ---------------------------------------------------------------------------
# Helpers — minimal coordinator mock
# ---------------------------------------------------------------------------


def _make_coordinator(
    state: dict[tuple[int, int], int] | None = None,
) -> MagicMock:
    """Create a mock coordinator with the given state cache."""
    coord = MagicMock()
    coord.data = state or {}
    coord.config_entry = MagicMock()
    coord.config_entry.entry_id = "test_entry_123"
    coord.async_enable_on = AsyncMock()
    coord.async_enable_off = AsyncMock()
    # CoordinatorEntity needs these
    coord.async_add_listener = MagicMock(return_value=lambda: None)
    return coord


# ===========================================================================
# Properties
# ===========================================================================


class TestCbusSwitchProperties:
    """Test CbusSwitch property accessors."""

    def test_unique_id(self) -> None:
        coord = _make_coordinator()
        sw = CbusSwitch(coord, group=10)
        assert sw.unique_id == f"cbus_test_entry_123_{ApplicationId.ENABLE}_10"

    def test_name_default(self) -> None:
        coord = _make_coordinator()
        sw = CbusSwitch(coord, group=3)
        assert sw.name == "Group 3"

    def test_name_custom(self) -> None:
        coord = _make_coordinator()
        sw = CbusSwitch(coord, group=10, name="Garden Irrigation")
        assert sw.name == "Garden Irrigation"

    def test_is_on_true(self) -> None:
        coord = _make_coordinator({(ApplicationId.ENABLE, 10): 0xFF})
        sw = CbusSwitch(coord, group=10)
        assert sw.is_on is True

    def test_is_on_false_zero(self) -> None:
        coord = _make_coordinator({(ApplicationId.ENABLE, 10): 0})
        sw = CbusSwitch(coord, group=10)
        assert sw.is_on is False

    def test_is_on_false_missing(self) -> None:
        coord = _make_coordinator()
        sw = CbusSwitch(coord, group=10)
        assert sw.is_on is False

    def test_device_info(self) -> None:
        coord = _make_coordinator()
        sw = CbusSwitch(coord, group=10)
        info = sw.device_info
        assert ("cbus", "test_entry_123") in info["identifiers"]


# ===========================================================================
# Turn on / off
# ===========================================================================


class TestCbusSwitchTurnOn:
    """Test async_turn_on behaviour."""

    @pytest.mark.asyncio
    async def test_turn_on(self) -> None:
        coord = _make_coordinator()
        sw = CbusSwitch(coord, group=10)
        await sw.async_turn_on()
        coord.async_enable_on.assert_awaited_once_with(group=10)


class TestCbusSwitchTurnOff:
    """Test async_turn_off behaviour."""

    @pytest.mark.asyncio
    async def test_turn_off(self) -> None:
        coord = _make_coordinator()
        sw = CbusSwitch(coord, group=10)
        await sw.async_turn_off()
        coord.async_enable_off.assert_awaited_once_with(group=10)


# ===========================================================================
# async_setup_entry
# ===========================================================================


class TestAsyncSetupEntry:
    """Test the platform setup function."""

    @pytest.mark.asyncio
    async def test_creates_entities_from_cache(self) -> None:
        """Entities are created for existing enable groups in the cache."""
        from custom_components.cbus.switch import async_setup_entry

        coord = _make_coordinator(
            {
                (ApplicationId.ENABLE, 10): 0xFF,
                (ApplicationId.ENABLE, 20): 0x00,
                (ApplicationId.LIGHTING, 1): 128,  # non-enable, should be skipped
            }
        )

        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry_123"
        entry.async_on_unload = MagicMock()
        hass.data = {"cbus": {"test_entry_123": coord}}

        added: list[CbusSwitch] = []

        def _add(entities: list[CbusSwitch]) -> None:
            added.extend(entities)

        await async_setup_entry(hass, entry, _add)

        assert len(added) == 2
        unique_ids = {e.unique_id for e in added}
        assert unique_ids == {
            f"cbus_test_entry_123_{ApplicationId.ENABLE}_10",
            f"cbus_test_entry_123_{ApplicationId.ENABLE}_20",
        }
