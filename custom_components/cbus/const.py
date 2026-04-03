"""Constants for the C-Bus integration."""

from __future__ import annotations

DOMAIN = "cbus"

PLATFORMS: list[str] = []  # Populated as entity platforms are implemented.

CONF_TRANSPORT = "transport"
CONF_SERIAL_PORT = "serial_port"

TRANSPORT_TCP = "tcp"
TRANSPORT_SERIAL = "serial"

DEFAULT_PORT = 10001
