"""Tests for C-Bus config flow.

Will test the HA config flow UI steps, input validation, connection
testing, and optional XML import.

Planned test cases:
    - TCP connection: valid host/port → success
    - TCP connection: unreachable host → error
    - Serial connection: valid device path → success
    - Serial connection: permission denied → error
    - XML import: valid HOME.xml → groups populated
    - XML import: malformed XML → graceful error
    - Options flow: edit group names
    - Duplicate entry detection (same host:port or device)

This is a stub - tests will be added alongside the config flow implementation.
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="config flow not yet implemented")
def test_config_flow_placeholder() -> None:
    """Placeholder so pytest collects at least one item."""
