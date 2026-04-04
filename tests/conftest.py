"""Shared test fixtures for ha-cbus.

This root conftest is loaded automatically by pytest.  It intentionally
has no HA-specific imports so that library tests can run without
Home Assistant installed.

Test layout::

    tests/
    +-- conftest.py                  <- this file (shared, HA-free)
    +-- lib/                         <- pycbus library tests
    |   +-- conftest.py
    |   +-- test_checksum.py
    |   +-- test_commands.py
    |   +-- test_constants.py
    |   +-- test_model.py
    |   +-- test_protocol.py
    |   +-- test_transport.py
    +-- integration/                 <- HA integration tests
    |   +-- conftest.py
    |   +-- test_config_flow.py
    |   +-- test_coordinator.py
"""
