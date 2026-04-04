"""Tests for the C-Bus event platform (Trigger Control).

Tests verify CbusTriggerEvent entity behaviour using mock coordinators,
without requiring a real C-Bus connection.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.cbus.event import EVENT_TRIGGER_ACTION, CbusTriggerEvent
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

    # Track trigger callbacks to allow manual dispatch in tests.
    coord._trigger_cbs: list = []

    def _on_trigger(cb):
        coord._trigger_cbs.append(cb)
        return lambda: coord._trigger_cbs.remove(cb)

    coord.on_trigger = MagicMock(side_effect=_on_trigger)
    # CoordinatorEntity needs these
    coord.async_add_listener = MagicMock(return_value=lambda: None)
    return coord


# ===========================================================================
# Properties
# ===========================================================================


class TestCbusTriggerEventProperties:
    """Test CbusTriggerEvent property accessors."""

    def test_unique_id(self) -> None:
        coord = _make_coordinator()
        ev = CbusTriggerEvent(coord, group=5)
        assert ev.unique_id == f"cbus_test_entry_123_{ApplicationId.TRIGGER}_5"

    def test_name_default(self) -> None:
        coord = _make_coordinator()
        ev = CbusTriggerEvent(coord, group=5)
        assert ev.name == "Group 5"

    def test_name_custom(self) -> None:
        coord = _make_coordinator()
        ev = CbusTriggerEvent(coord, group=5, name="All Off")
        assert ev.name == "All Off"

    def test_event_types(self) -> None:
        coord = _make_coordinator()
        ev = CbusTriggerEvent(coord, group=5)
        assert ev.event_types == [EVENT_TRIGGER_ACTION]

    def test_device_info(self) -> None:
        coord = _make_coordinator()
        ev = CbusTriggerEvent(coord, group=5)
        info = ev.device_info
        assert ("cbus", "test_entry_123") in info["identifiers"]


# ===========================================================================
# Trigger firing
# ===========================================================================


class TestCbusTriggerEventFiring:
    """Test trigger event dispatch."""

    def test_fire_trigger_calls_trigger_event(self) -> None:
        """fire_trigger should call _trigger_event with correct args."""
        coord = _make_coordinator()
        ev = CbusTriggerEvent(coord, group=5)

        with patch.object(ev, "_trigger_event") as mock_trigger:
            ev.fire_trigger(42)
            mock_trigger.assert_called_once_with(EVENT_TRIGGER_ACTION, {"action": 42})

    def test_on_trigger_filters_by_group(self) -> None:
        """_on_trigger should only fire for matching group."""
        coord = _make_coordinator()
        ev = CbusTriggerEvent(coord, group=5)

        with patch.object(ev, "_trigger_event") as mock_trigger:
            ev._on_trigger(group=99, action=0)
            mock_trigger.assert_not_called()

            ev._on_trigger(group=5, action=10)
            mock_trigger.assert_called_once_with(EVENT_TRIGGER_ACTION, {"action": 10})


# ===========================================================================
# async_setup_entry
# ===========================================================================


class TestAsyncSetupEntry:
    """Test the platform setup function."""

    @pytest.mark.asyncio
    async def test_creates_entities_from_cache(self) -> None:
        """Entities are created for trigger groups already in the cache."""
        from custom_components.cbus.event import async_setup_entry

        coord = _make_coordinator(
            {
                (ApplicationId.TRIGGER, 5): 0,
                (ApplicationId.TRIGGER, 10): 0,
                (ApplicationId.LIGHTING, 1): 128,  # non-trigger, skip
            }
        )

        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry_123"
        entry.async_on_unload = MagicMock()
        hass.data = {"cbus": {"test_entry_123": coord}}

        added: list[CbusTriggerEvent] = []

        def _add(entities: list[CbusTriggerEvent]) -> None:
            added.extend(entities)

        await async_setup_entry(hass, entry, _add)

        assert len(added) == 2
        unique_ids = {e.unique_id for e in added}
        assert unique_ids == {
            f"cbus_test_entry_123_{ApplicationId.TRIGGER}_5",
            f"cbus_test_entry_123_{ApplicationId.TRIGGER}_10",
        }

    @pytest.mark.asyncio
    async def test_dynamic_entity_on_new_trigger(self) -> None:
        """New trigger group fires dynamic entity creation."""
        from custom_components.cbus.event import async_setup_entry

        coord = _make_coordinator()

        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry_123"
        entry.async_on_unload = MagicMock()
        hass.data = {"cbus": {"test_entry_123": coord}}

        added: list[CbusTriggerEvent] = []

        def _add(entities: list[CbusTriggerEvent]) -> None:
            added.extend(entities)

        await async_setup_entry(hass, entry, _add)

        # No entities initially.
        assert len(added) == 0

        # Simulate a trigger event for a new group.
        assert coord.on_trigger.called
        trigger_cb = coord.on_trigger.call_args[0][0]
        trigger_cb(group=7, action=0)

        # Should have dynamically added one entity.
        assert len(added) == 1
        assert added[0].unique_id == f"cbus_test_entry_123_{ApplicationId.TRIGGER}_7"
