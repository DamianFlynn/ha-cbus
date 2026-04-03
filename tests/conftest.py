"""Shared test fixtures for ha-cbus.

This conftest is loaded automatically by pytest for every test module.
It provides common fixtures used across both pycbus library tests and
Home Assistant integration tests.

Test layout::

    tests/
    +-- conftest.py              <- this file
    +-- test_checksum.py         - checksum algorithm unit tests
    +-- test_commands.py         - SAL command builder unit tests
    +-- test_constants.py        - enum completeness and value tests
    +-- test_model.py            - dataclass validation tests
    +-- test_protocol.py         - protocol state machine tests
    +-- test_config_flow.py      - HA config flow tests
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

# Only define HA-specific fixtures when pytest-homeassistant-custom-component
# is installed.  Library tests (checksum, commands, model, etc.) run without
# Home Assistant and must not fail on missing HA fixtures.
try:
    from pytest_homeassistant_custom_component.common import (  # noqa: F401
        MockConfigEntry,
    )

    _HAS_HA_TEST = True
except ImportError:
    _HAS_HA_TEST = False


if _HAS_HA_TEST:

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
