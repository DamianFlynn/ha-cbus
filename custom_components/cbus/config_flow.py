"""Config flow for C-Bus integration.

The config flow guides the user through setting up a C-Bus connection:

1. **Connection type** - TCP (CNI) or Serial (PCI).
2. **Connection details** - host:port for TCP, device path for serial.
3. **Confirmation** - create config entry with the chosen transport.

The flow stores the following in ``config_entry.data``::

    {
        "transport": "tcp" | "serial",
        "host": "192.168.1.50",    # TCP only
        "port": 10001,              # TCP only
        "serial_port": "/dev/ttyUSB0",  # serial only
    }

Options flow:
    After initial setup, the options flow allows adjusting connection
    parameters without removing the entry.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import (
    CONF_SERIAL_PORT,
    CONF_TRANSPORT,
    DEFAULT_PORT,
    DOMAIN,
    TRANSPORT_SERIAL,
    TRANSPORT_TCP,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TRANSPORT, default=TRANSPORT_TCP): vol.In(
            [TRANSPORT_TCP, TRANSPORT_SERIAL]
        ),
    }
)

STEP_TCP_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
    }
)

STEP_SERIAL_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SERIAL_PORT): str,
    }
)


class CbusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for C-Bus."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - choose transport type."""
        if user_input is not None:
            if user_input[CONF_TRANSPORT] == TRANSPORT_TCP:
                return await self.async_step_tcp()
            return await self.async_step_serial()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
        )

    async def async_step_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle TCP connection details."""
        if user_input is not None:
            self._async_abort_entries_match(
                {CONF_HOST: user_input[CONF_HOST], CONF_PORT: user_input[CONF_PORT]}
            )
            return self.async_create_entry(
                title=f"C-Bus ({user_input[CONF_HOST]}:{user_input[CONF_PORT]})",
                data={
                    CONF_TRANSPORT: TRANSPORT_TCP,
                    CONF_HOST: user_input[CONF_HOST],
                    CONF_PORT: user_input[CONF_PORT],
                },
            )

        return self.async_show_form(
            step_id="tcp",
            data_schema=STEP_TCP_DATA_SCHEMA,
        )

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle serial connection details."""
        if user_input is not None:
            self._async_abort_entries_match(
                {CONF_SERIAL_PORT: user_input[CONF_SERIAL_PORT]}
            )
            return self.async_create_entry(
                title=f"C-Bus ({user_input[CONF_SERIAL_PORT]})",
                data={
                    CONF_TRANSPORT: TRANSPORT_SERIAL,
                    CONF_SERIAL_PORT: user_input[CONF_SERIAL_PORT],
                },
            )

        return self.async_show_form(
            step_id="serial",
            data_schema=STEP_SERIAL_DATA_SCHEMA,
        )
