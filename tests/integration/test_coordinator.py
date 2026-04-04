"""Tests for the C-Bus coordinator.

Tests use a mock protocol to simulate PCI communication without
real hardware.  Tests for the HA integration side use
pytest-homeassistant-custom-component fixtures.
"""

from __future__ import annotations

import pytest

from custom_components.cbus.coordinator import (
    CbusCoordinator,
    _closest_ramp_rate,
)
from pycbus.constants import ApplicationId, LightingCommand

# ---------------------------------------------------------------------------
# _closest_ramp_rate
# ---------------------------------------------------------------------------


class TestClosestRampRate:
    """Test the binary-search ramp rate picker."""

    def test_exact_match_0s(self) -> None:
        assert _closest_ramp_rate(0) == LightingCommand.RAMP_INSTANT

    def test_exact_match_4s(self) -> None:
        assert _closest_ramp_rate(4) == LightingCommand.RAMP_4S

    def test_exact_match_60s(self) -> None:
        assert _closest_ramp_rate(60) == LightingCommand.RAMP_60S

    def test_exact_match_1020s(self) -> None:
        assert _closest_ramp_rate(1020) == LightingCommand.RAMP_1020S

    def test_between_picks_closer_lower(self) -> None:
        # 5s is closer to 4s than 8s
        assert _closest_ramp_rate(5) == LightingCommand.RAMP_4S

    def test_between_picks_closer_upper(self) -> None:
        # 7s is closer to 8s than 4s
        assert _closest_ramp_rate(7) == LightingCommand.RAMP_8S

    def test_midpoint_picks_lower(self) -> None:
        # 6s is equidistant from 4s and 8s; picks lower
        assert _closest_ramp_rate(6) == LightingCommand.RAMP_4S

    def test_below_minimum(self) -> None:
        # Negative seconds should still return instant
        assert _closest_ramp_rate(-1) == LightingCommand.RAMP_INSTANT

    def test_above_maximum(self) -> None:
        # Way above max should return the longest ramp
        assert _closest_ramp_rate(9999) == LightingCommand.RAMP_1020S

    def test_fractional_seconds(self) -> None:
        # 2.0s is closer to 0s instant than 4s
        assert _closest_ramp_rate(2.0) == LightingCommand.RAMP_INSTANT


# ---------------------------------------------------------------------------
# SAL event parsing (_handle_sal_event)
# ---------------------------------------------------------------------------


class TestHandleSalEvent:
    """Test the SAL event parser in isolation (no HA, no protocol)."""

    def _make_coordinator(self) -> CbusCoordinator:
        """Create a coordinator without HA wiring for unit testing."""
        # We can't call the normal constructor without HA, so we
        # construct manually with just the parts we need.
        coord = object.__new__(CbusCoordinator)
        coord.data = {}
        coord.logger = __import__("logging").getLogger("test")
        # Stub out async_set_updated_data so it doesn't need HA
        coord.async_set_updated_data = lambda data: None  # type: ignore[assignment]
        return coord

    def test_lighting_on(self) -> None:
        coord = self._make_coordinator()
        # ON command: 05 38 00 79 01 FF <checksum>
        from pycbus.checksum import checksum

        payload = bytes([0x05, 0x38, 0x00, 0x79, 0x01, 0xFF])
        cs = checksum(payload)
        sal = payload + bytes([cs])

        coord._handle_sal_event(sal)

        assert coord.data[(ApplicationId.LIGHTING, 1)] == 0xFF

    def test_lighting_off(self) -> None:
        coord = self._make_coordinator()
        from pycbus.checksum import checksum

        payload = bytes([0x05, 0x38, 0x00, 0x01, 0x05])
        cs = checksum(payload)
        sal = payload + bytes([cs])

        coord._handle_sal_event(sal)

        assert coord.data[(ApplicationId.LIGHTING, 5)] == 0x00

    def test_lighting_ramp(self) -> None:
        coord = self._make_coordinator()
        from pycbus.checksum import checksum

        # RAMP_4S to group 3, level 128
        payload = bytes([0x05, 0x38, 0x00, 0x0A, 0x03, 0x80])
        cs = checksum(payload)
        sal = payload + bytes([cs])

        coord._handle_sal_event(sal)

        assert coord.data[(ApplicationId.LIGHTING, 3)] == 0x80

    def test_lighting_terminate_ramp_no_update(self) -> None:
        coord = self._make_coordinator()
        # Pre-set a level
        coord.data[(ApplicationId.LIGHTING, 1)] = 0x80

        from pycbus.checksum import checksum

        payload = bytes([0x05, 0x38, 0x00, 0x09, 0x01])
        cs = checksum(payload)
        sal = payload + bytes([cs])

        coord._handle_sal_event(sal)

        # Level should remain unchanged
        assert coord.data[(ApplicationId.LIGHTING, 1)] == 0x80

    def test_short_packet_ignored(self) -> None:
        coord = self._make_coordinator()
        coord._handle_sal_event(b"\x05\x38\x00")
        assert len(coord.data) == 0

    def test_unknown_app_ignored(self) -> None:
        coord = self._make_coordinator()
        from pycbus.checksum import checksum

        # App 0xFF (unknown)
        payload = bytes([0x05, 0xFF, 0x00, 0x79, 0x01, 0xFF])
        cs = checksum(payload)
        sal = payload + bytes([cs])

        coord._handle_sal_event(sal)

        assert len(coord.data) == 0

    def test_multiple_events_accumulate(self) -> None:
        coord = self._make_coordinator()
        from pycbus.checksum import checksum

        # Group 1 ON
        p1 = bytes([0x05, 0x38, 0x00, 0x79, 0x01, 0xFF])
        coord._handle_sal_event(p1 + bytes([checksum(p1)]))

        # Group 2 ramp to 100
        p2 = bytes([0x05, 0x38, 0x00, 0x02, 0x02, 0x64])
        coord._handle_sal_event(p2 + bytes([checksum(p2)]))

        assert coord.data[(ApplicationId.LIGHTING, 1)] == 0xFF
        assert coord.data[(ApplicationId.LIGHTING, 2)] == 0x64


# ---------------------------------------------------------------------------
# Command methods (unit test without HA)
# ---------------------------------------------------------------------------


class TestCommandMethods:
    """Test command building without actual protocol sending."""

    @pytest.mark.asyncio
    async def test_light_on_updates_cache(self) -> None:
        """async_light_on should build the right command and update cache."""
        coord = object.__new__(CbusCoordinator)
        coord.data = {}
        coord.async_set_updated_data = lambda data: None  # type: ignore[assignment]

        sent_commands: list[bytes] = []

        class FakeProtocol:
            async def send_command(self, payload: bytes) -> bool:
                sent_commands.append(payload)
                return True

        coord._protocol = FakeProtocol()  # type: ignore[assignment]

        await coord.async_light_on(group=1)

        assert coord.data[(ApplicationId.LIGHTING, 1)] == 0xFF
        assert len(sent_commands) == 1

    @pytest.mark.asyncio
    async def test_light_off_updates_cache(self) -> None:
        coord = object.__new__(CbusCoordinator)
        coord.data = {}
        coord.async_set_updated_data = lambda data: None  # type: ignore[assignment]

        sent_commands: list[bytes] = []

        class FakeProtocol:
            async def send_command(self, payload: bytes) -> bool:
                sent_commands.append(payload)
                return True

        coord._protocol = FakeProtocol()  # type: ignore[assignment]

        await coord.async_light_off(group=5)

        assert coord.data[(ApplicationId.LIGHTING, 5)] == 0x00
        assert len(sent_commands) == 1

    @pytest.mark.asyncio
    async def test_light_ramp_updates_cache(self) -> None:
        coord = object.__new__(CbusCoordinator)
        coord.data = {}
        coord.async_set_updated_data = lambda data: None  # type: ignore[assignment]

        sent_commands: list[bytes] = []

        class FakeProtocol:
            async def send_command(self, payload: bytes) -> bool:
                sent_commands.append(payload)
                return True

        coord._protocol = FakeProtocol()  # type: ignore[assignment]

        await coord.async_light_ramp(group=3, level=128, transition=4.0)

        assert coord.data[(ApplicationId.LIGHTING, 3)] == 128
        assert len(sent_commands) == 1

    @pytest.mark.asyncio
    async def test_light_terminate_ramp(self) -> None:
        coord = object.__new__(CbusCoordinator)
        coord.data = {}
        coord.async_set_updated_data = lambda data: None  # type: ignore[assignment]

        sent_commands: list[bytes] = []

        class FakeProtocol:
            async def send_command(self, payload: bytes) -> bool:
                sent_commands.append(payload)
                return True

        coord._protocol = FakeProtocol()  # type: ignore[assignment]

        await coord.async_light_terminate_ramp(group=1)

        # terminate_ramp doesn't update the cache
        assert (ApplicationId.LIGHTING, 1) not in coord.data
        assert len(sent_commands) == 1

    @pytest.mark.asyncio
    async def test_send_when_not_connected(self) -> None:
        from pycbus.exceptions import CbusConnectionError

        coord = object.__new__(CbusCoordinator)
        coord.data = {}
        coord._protocol = None

        with pytest.raises(CbusConnectionError, match="not connected"):
            await coord.async_light_on(group=1)
