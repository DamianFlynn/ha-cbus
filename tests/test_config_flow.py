"""Tests for C-Bus config flow.

Tests the HA config flow UI steps: transport selection, TCP/serial
details, entry creation, and duplicate detection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.cbus.const import (
    CONF_SERIAL_PORT,
    CONF_TRANSPORT,
    DEFAULT_PORT,
    DOMAIN,
    TRANSPORT_SERIAL,
    TRANSPORT_TCP,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def test_user_step_shows_form(hass: HomeAssistant) -> None:
    """Test the user step presents transport selection."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_step_tcp_goes_to_tcp_step(hass: HomeAssistant) -> None:
    """Selecting TCP transport advances to the tcp step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_TRANSPORT: TRANSPORT_TCP},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "tcp"


async def test_user_step_serial_goes_to_serial_step(hass: HomeAssistant) -> None:
    """Selecting serial transport advances to the serial step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_TRANSPORT: TRANSPORT_SERIAL},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "serial"


async def test_tcp_creates_entry(hass: HomeAssistant, mock_setup_entry: None) -> None:
    """Completing TCP details creates a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_TRANSPORT: TRANSPORT_TCP},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"host": "192.168.1.50", "port": DEFAULT_PORT},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"C-Bus (192.168.1.50:{DEFAULT_PORT})"
    assert result["data"] == {
        CONF_TRANSPORT: TRANSPORT_TCP,
        "host": "192.168.1.50",
        "port": DEFAULT_PORT,
    }


async def test_serial_creates_entry(
    hass: HomeAssistant, mock_setup_entry: None
) -> None:
    """Completing serial details creates a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_TRANSPORT: TRANSPORT_SERIAL},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_SERIAL_PORT: "/dev/ttyUSB0"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "C-Bus (/dev/ttyUSB0)"
    assert result["data"] == {
        CONF_TRANSPORT: TRANSPORT_SERIAL,
        CONF_SERIAL_PORT: "/dev/ttyUSB0",
    }


async def test_tcp_duplicate_aborts(
    hass: HomeAssistant, mock_setup_entry: None
) -> None:
    """A second TCP entry with the same host:port is aborted."""
    # Create the first entry.
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_TRANSPORT: TRANSPORT_TCP},
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"host": "192.168.1.50", "port": DEFAULT_PORT},
    )

    # Attempt the same host:port again.
    result2 = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        {CONF_TRANSPORT: TRANSPORT_TCP},
    )
    result2 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        {"host": "192.168.1.50", "port": DEFAULT_PORT},
    )
    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


async def test_serial_duplicate_aborts(
    hass: HomeAssistant, mock_setup_entry: None
) -> None:
    """A second serial entry with the same device path is aborted."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_TRANSPORT: TRANSPORT_SERIAL},
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_SERIAL_PORT: "/dev/ttyUSB0"},
    )

    result2 = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        {CONF_TRANSPORT: TRANSPORT_SERIAL},
    )
    result2 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        {CONF_SERIAL_PORT: "/dev/ttyUSB0"},
    )
    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


async def test_tcp_different_port_allowed(
    hass: HomeAssistant, mock_setup_entry: None
) -> None:
    """A TCP entry with a different port on the same host is accepted."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_TRANSPORT: TRANSPORT_TCP},
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"host": "192.168.1.50", "port": DEFAULT_PORT},
    )

    result2 = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        {CONF_TRANSPORT: TRANSPORT_TCP},
    )
    result2 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        {"host": "192.168.1.50", "port": 10002},
    )
    assert result2["type"] is FlowResultType.CREATE_ENTRY
