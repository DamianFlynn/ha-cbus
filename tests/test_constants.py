"""Tests for pycbus constants module.

Verifies that all protocol enumerations have the correct values, are
complete, and are consistent with the C-Bus specification.

Covers:
    - ApplicationId values match the documented hex codes.
    - LightingCommand opcodes match Chapter 02 Table 2-2.
    - RAMP_DURATIONS is sorted and covers all ramp opcodes.
    - ConfirmationCode ASCII values.
    - InterfaceOption bitmask values.
    - Serial and TCP default constants.
"""

from __future__ import annotations

from pycbus.constants import (
    RAMP_DURATIONS,
    ApplicationId,
    ConfirmationCode,
    InterfaceOption1,
    InterfaceOption3,
    LightingCommand,
    PointToMultipointDAT,
    SERIAL_BAUD,
    TCP_PORT,
)


class TestApplicationId:
    """Verify application IDs match the C-Bus specification."""

    def test_lighting_is_0x38(self) -> None:
        """Lighting app = 56 (0x38) per Chapter 02."""
        assert ApplicationId.LIGHTING == 0x38

    def test_trigger_is_0xCA(self) -> None:
        """Trigger app = 202 (0xCA) per Chapter 07."""
        assert ApplicationId.TRIGGER == 0xCA

    def test_enable_is_0xCB(self) -> None:
        """Enable app = 203 (0xCB) per Chapter 08."""
        assert ApplicationId.ENABLE == 0xCB

    def test_security_is_0xD0(self) -> None:
        """Security app = 208 (0xD0) per Chapter 05."""
        assert ApplicationId.SECURITY == 0xD0

    def test_all_values_in_byte_range(self) -> None:
        """Every application ID must fit in a single byte."""
        for app in ApplicationId:
            assert 0 <= app <= 255, f"{app.name} = {app} is outside 0–255"


class TestPointToMultipointDAT:
    """Verify DAT byte values."""

    def test_broadcast_is_0x05(self) -> None:
        """Broadcast DAT = 0x05 per Serial Interface User Guide §4.3.3."""
        assert PointToMultipointDAT.BROADCAST == 0x05


class TestLightingCommand:
    """Verify lighting SAL opcodes match Chapter 02 Table 2-2."""

    def test_off_opcode(self) -> None:
        assert LightingCommand.OFF == 0x01

    def test_on_opcode(self) -> None:
        assert LightingCommand.ON == 0x79

    def test_terminate_ramp_opcode(self) -> None:
        assert LightingCommand.TERMINATE_RAMP == 0x09

    def test_ramp_instant_opcode(self) -> None:
        assert LightingCommand.RAMP_INSTANT == 0x02

    def test_all_ramp_opcodes_unique(self) -> None:
        """Every ramp opcode must have a unique value."""
        ramp_values = [
            lc.value for lc in LightingCommand
            if lc.name.startswith("RAMP_")
        ]
        assert len(ramp_values) == len(set(ramp_values))


class TestRampDurations:
    """Verify the RAMP_DURATIONS lookup table."""

    def test_sorted_ascending(self) -> None:
        """Durations must be sorted in ascending order."""
        durations = [d for d, _ in RAMP_DURATIONS]
        assert durations == sorted(durations)

    def test_starts_at_zero(self) -> None:
        """First entry should be instant (0 seconds)."""
        assert RAMP_DURATIONS[0][0] == 0
        assert RAMP_DURATIONS[0][1] == LightingCommand.RAMP_INSTANT

    def test_covers_all_ramp_opcodes(self) -> None:
        """Every RAMP_* opcode should appear in the duration table."""
        table_opcodes = {rate for _, rate in RAMP_DURATIONS}
        ramp_opcodes = {
            lc for lc in LightingCommand
            if lc.name.startswith("RAMP_")
        }
        assert ramp_opcodes == table_opcodes

    def test_max_duration_is_1020(self) -> None:
        """Longest ramp is 1020 seconds (17 minutes) per Chapter 02."""
        assert RAMP_DURATIONS[-1][0] == 1020


class TestConfirmationCode:
    """Verify PCI confirmation codes."""

    def test_positive_is_g(self) -> None:
        assert ConfirmationCode.POSITIVE == ord("g")

    def test_negative_is_bang(self) -> None:
        assert ConfirmationCode.NEGATIVE == ord("!")

    def test_ready_is_hash(self) -> None:
        assert ConfirmationCode.READY == ord("#")

    def test_busy_is_dot(self) -> None:
        assert ConfirmationCode.BUSY == ord(".")


class TestInterfaceOptions:
    """Verify interface option bitmask values."""

    def test_option1_connect(self) -> None:
        assert InterfaceOption1.CONNECT == 0x01

    def test_option1_smart(self) -> None:
        assert InterfaceOption1.SMART == 0x10

    def test_option1_monitor(self) -> None:
        assert InterfaceOption1.MONITOR == 0x40

    def test_option3_exstat(self) -> None:
        assert InterfaceOption3.EXSTAT == 0x08

    def test_our_init_option1(self) -> None:
        """Our init sets CONNECT | SRCHK | SMART | MONITOR = 0x59."""
        value = (
            InterfaceOption1.CONNECT
            | InterfaceOption1.SRCHK
            | InterfaceOption1.SMART
            | InterfaceOption1.MONITOR
        )
        assert value == 0x59

    def test_our_init_option3(self) -> None:
        """Our init sets LOCAL_SAL | EXSTAT = 0x0A."""
        value = InterfaceOption3.LOCAL_SAL | InterfaceOption3.EXSTAT
        assert value == 0x0A


class TestDefaults:
    """Verify serial and TCP default constants."""

    def test_serial_baud(self) -> None:
        assert SERIAL_BAUD == 9600

    def test_tcp_port(self) -> None:
        assert TCP_PORT == 10001
