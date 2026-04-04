"""Constants for the C-Bus integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "cbus"

PLATFORMS: list[Platform] = [Platform.LIGHT]

CONF_TRANSPORT = "transport"
CONF_SERIAL_PORT = "serial_port"

TRANSPORT_TCP = "tcp"
TRANSPORT_SERIAL = "serial"

DEFAULT_PORT = 10001
