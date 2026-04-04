"""Conftest for Home Assistant integration tests.

These tests require ``pytest-homeassistant-custom-component`` and the
full Home Assistant runtime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

try:
    from pytest_homeassistant_custom_component.common import (  # noqa: F401
        MockConfigEntry,
    )
except ImportError as exc:
    raise ImportError(
        "Integration tests require pytest-homeassistant-custom-component"
    ) from exc


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> None:
    """Enable loading of custom_components/cbus for all tests."""


@pytest.fixture
def mock_setup_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent actual async_setup_entry during config flow tests."""

    async def _noop(hass: HomeAssistant, entry: object) -> bool:
        return True

    monkeypatch.setattr("custom_components.cbus.async_setup_entry", _noop)
