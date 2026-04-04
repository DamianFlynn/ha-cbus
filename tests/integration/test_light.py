"""Tests for the C-Bus light platform.

Tests verify CbusLight entity behaviour using mock coordinators,
without requiring a real C-Bus connection.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.cbus.light import CbusLight
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
    coord.async_light_on = AsyncMock()
    coord.async_light_off = AsyncMock()
    coord.async_light_ramp = AsyncMock()
    coord.async_light_terminate_ramp = AsyncMock()
    # CoordinatorEntity needs these
    coord.async_add_listener = MagicMock(return_value=lambda: None)
    return coord


# ===========================================================================
# Properties
# ===========================================================================


class TestCbusLightProperties:
    """Test CbusLight property accessors."""

    def test_unique_id(self) -> None:
        coord = _make_coordinator()
        light = CbusLight(coord, group=1)
        assert light.unique_id == f"cbus_test_entry_123_{ApplicationId.LIGHTING}_1"

    def test_name_default(self) -> None:
        coord = _make_coordinator()
        light = CbusLight(coord, group=5)
        assert light.name == "Group 5"

    def test_name_custom(self) -> None:
        coord = _make_coordinator()
        light = CbusLight(coord, group=1, name="Kitchen Downlights")
        assert light.name == "Kitchen Downlights"

    def test_brightness_unknown(self) -> None:
        coord = _make_coordinator()
        light = CbusLight(coord, group=1)
        assert light.brightness is None

    def test_brightness_from_cache(self) -> None:
        coord = _make_coordinator({(ApplicationId.LIGHTING, 1): 128})
        light = CbusLight(coord, group=1)
        assert light.brightness == 128

    def test_is_on_true(self) -> None:
        coord = _make_coordinator({(ApplicationId.LIGHTING, 1): 255})
        light = CbusLight(coord, group=1)
        assert light.is_on is True

    def test_is_on_false_zero(self) -> None:
        coord = _make_coordinator({(ApplicationId.LIGHTING, 1): 0})
        light = CbusLight(coord, group=1)
        assert light.is_on is False

    def test_is_on_false_missing(self) -> None:
        coord = _make_coordinator()
        light = CbusLight(coord, group=1)
        assert light.is_on is False

    def test_device_info(self) -> None:
        coord = _make_coordinator()
        light = CbusLight(coord, group=1)
        info = light.device_info
        assert ("cbus", "test_entry_123") in info["identifiers"]


# ===========================================================================
# Turn on
# ===========================================================================


class TestCbusLightTurnOn:
    """Test async_turn_on behaviour."""

    @pytest.mark.asyncio
    async def test_turn_on_simple(self) -> None:
        """Turn on with no kwargs → lighting_on."""
        coord = _make_coordinator()
        light = CbusLight(coord, group=1)
        await light.async_turn_on()
        coord.async_light_on.assert_awaited_once_with(group=1)

    @pytest.mark.asyncio
    async def test_turn_on_with_brightness(self) -> None:
        """Turn on with brightness → ramp."""
        coord = _make_coordinator()
        light = CbusLight(coord, group=3)
        await light.async_turn_on(brightness=128)
        coord.async_light_ramp.assert_awaited_once_with(
            group=3, level=128, transition=0.0
        )

    @pytest.mark.asyncio
    async def test_turn_on_with_brightness_and_transition(self) -> None:
        """Turn on with brightness + transition → ramp with duration."""
        coord = _make_coordinator()
        light = CbusLight(coord, group=2)
        await light.async_turn_on(brightness=200, transition=4.0)
        coord.async_light_ramp.assert_awaited_once_with(
            group=2, level=200, transition=4.0
        )

    @pytest.mark.asyncio
    async def test_turn_on_with_transition_only(self) -> None:
        """Turn on with transition but no brightness → ramp to 255."""
        coord = _make_coordinator()
        light = CbusLight(coord, group=1)
        await light.async_turn_on(transition=8.0)
        coord.async_light_ramp.assert_awaited_once_with(
            group=1, level=255, transition=8.0
        )


# ===========================================================================
# Turn off
# ===========================================================================


class TestCbusLightTurnOff:
    """Test async_turn_off behaviour."""

    @pytest.mark.asyncio
    async def test_turn_off_simple(self) -> None:
        """Turn off with no kwargs → lighting_off."""
        coord = _make_coordinator()
        light = CbusLight(coord, group=5)
        await light.async_turn_off()
        coord.async_light_off.assert_awaited_once_with(group=5)

    @pytest.mark.asyncio
    async def test_turn_off_with_transition(self) -> None:
        """Turn off with transition → ramp to 0."""
        coord = _make_coordinator()
        light = CbusLight(coord, group=2)
        await light.async_turn_off(transition=4.0)
        coord.async_light_ramp.assert_awaited_once_with(
            group=2, level=0, transition=4.0
        )


# ===========================================================================
# async_setup_entry
# ===========================================================================


class TestAsyncSetupEntry:
    """Test the platform setup function."""

    @pytest.mark.asyncio
    async def test_creates_entities_from_cache(self) -> None:
        """Entities are created for existing lighting groups in the cache."""
        from custom_components.cbus.light import async_setup_entry

        coord = _make_coordinator(
            {
                (ApplicationId.LIGHTING, 1): 255,
                (ApplicationId.LIGHTING, 5): 0,
                (0xFF, 10): 100,  # non-lighting, should be skipped
            }
        )

        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry_123"
        entry.async_on_unload = MagicMock()
        hass.data = {"cbus": {"test_entry_123": coord}}

        added: list[CbusLight] = []

        def _add(entities: list[CbusLight]) -> None:
            added.extend(entities)

        await async_setup_entry(hass, entry, _add)

        # Should create 2 lighting entities, not the 0xFF one.
        assert len(added) == 2
        unique_ids = {e.unique_id for e in added}
        assert unique_ids == {
            f"cbus_test_entry_123_{ApplicationId.LIGHTING}_1",
            f"cbus_test_entry_123_{ApplicationId.LIGHTING}_5",
        }
