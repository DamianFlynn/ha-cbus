"""Shared test fixtures for ha-cbus.

This conftest is loaded automatically by pytest for every test module.
It provides common fixtures used across both pycbus library tests and
Home Assistant integration tests.

Fixture categories:
    - Protocol fixtures: mock transports, pre-built command bytes.
    - Model fixtures: sample CbusProject / CbusNetwork topologies.
    - HA fixtures: mock hass instance, config entries (integration tests).

Test layout::

    tests/
    ├── conftest.py              ← this file
    ├── test_checksum.py         — checksum algorithm unit tests
    ├── test_commands.py         — SAL command builder unit tests
    ├── test_constants.py        — enum completeness and value tests
    ├── test_model.py            — dataclass validation tests
    ├── test_protocol.py         — protocol state machine tests
    └── test_config_flow.py      — HA config flow tests
"""

from __future__ import annotations
