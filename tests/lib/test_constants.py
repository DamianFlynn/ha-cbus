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
    LABEL_MAX_TEXT_LENGTH,
    LABEL_MIN_ARG_COUNT,
    LABEL_OPCODE_MASK,
    RAMP_DURATIONS,
    SERIAL_BAUD,
    TCP_PORT,
    ApplicationId,
    ConfirmationCode,
    InterfaceOption1,
    InterfaceOption3,
    LabelLanguage,
    LabelOption,
    LightingCommand,
    PointToMultipointDAT,
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
            assert 0 <= app <= 255, f"{app.name} = {app} is outside 0-255"


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
            lc.value for lc in LightingCommand if lc.name.startswith("RAMP_")
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
        ramp_opcodes = {lc for lc in LightingCommand if lc.name.startswith("RAMP_")}
        assert ramp_opcodes == table_opcodes

    def test_max_duration_is_1020(self) -> None:
        """Longest ramp is 1020 seconds (17 minutes) per Chapter 02."""
        assert RAMP_DURATIONS[-1][0] == 1020


class TestConfirmationCode:
    """Verify PCI confirmation codes."""

    def test_positive_is_g(self) -> None:
        assert ord("g") == ConfirmationCode.POSITIVE

    def test_negative_is_bang(self) -> None:
        assert ord("!") == ConfirmationCode.NEGATIVE

    def test_ready_is_hash(self) -> None:
        assert ord("#") == ConfirmationCode.READY

    def test_busy_is_dot(self) -> None:
        assert ord(".") == ConfirmationCode.BUSY


class TestInterfaceOptions:
    """Verify interface option bitmask values."""

    def test_option1_connect(self) -> None:
        assert InterfaceOption1.CONNECT == 0x01

    def test_option1_smart(self) -> None:
        assert InterfaceOption1.SMART == 0x10

    def test_option1_monitor(self) -> None:
        assert InterfaceOption1.MONITOR == 0x20

    def test_option3_exstat(self) -> None:
        assert InterfaceOption3.EXSTAT == 0x08

    def test_our_init_option1(self) -> None:
        """Our init sets CONNECT|SRCHK|SMART|MONITOR|IDMON = 0x79."""
        value = (
            InterfaceOption1.CONNECT
            | InterfaceOption1.SRCHK
            | InterfaceOption1.SMART
            | InterfaceOption1.MONITOR
            | InterfaceOption1.IDMON
        )
        assert value == 0x79

    def test_option1_bit_positions_match_spec(self) -> None:
        """Bit positions per Serial Interface User Guide, Table p58.

        Bit 0 = CONNECT  (0x01)
        Bit 3 = SRCHK    (0x08)
        Bit 4 = SMART    (0x10)
        Bit 5 = MONITOR  (0x20)
        Bit 6 = IDMON    (0x40)
        """
        assert InterfaceOption1.CONNECT == 0x01  # bit 0
        assert InterfaceOption1.SRCHK == 0x08  # bit 3
        assert InterfaceOption1.SMART == 0x10  # bit 4
        assert InterfaceOption1.MONITOR == 0x20  # bit 5
        assert InterfaceOption1.IDMON == 0x40  # bit 6

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


class TestLabelOption:
    """Verify LabelOption enum values match Chapter 02, s2.6.5."""

    def test_text_label(self) -> None:
        """TEXT_LABEL = 0x00 (bits 2:1 = 00)."""
        assert LabelOption.TEXT_LABEL == 0x00

    def test_predefined_icon(self) -> None:
        """PREDEFINED_ICON = 0x02 (bits 2:1 = 01)."""
        assert LabelOption.PREDEFINED_ICON == 0x02

    def test_dynamic_icon(self) -> None:
        """DYNAMIC_ICON = 0x04 (bits 2:1 = 10)."""
        assert LabelOption.DYNAMIC_ICON == 0x04

    def test_set_preferred_language(self) -> None:
        """SET_PREFERRED_LANGUAGE = 0x06 (bits 2:1 = 11)."""
        assert LabelOption.SET_PREFERRED_LANGUAGE == 0x06

    def test_flavour_encoding(self) -> None:
        """Flavour n should produce n << 5 when OR'd with TEXT_LABEL."""
        for flav in range(4):
            opts = LabelOption.TEXT_LABEL | (flav << 5)
            assert (opts >> 5) & 0x03 == flav


class TestLabelLanguage:
    """Verify LabelLanguage codes match Chapter 02, s2.4.3."""

    def test_english(self) -> None:
        assert LabelLanguage.ENGLISH == 0x01

    def test_english_au(self) -> None:
        assert LabelLanguage.ENGLISH_AU == 0x02

    def test_english_us(self) -> None:
        assert LabelLanguage.ENGLISH_US == 0x0D

    def test_french(self) -> None:
        assert LabelLanguage.FRENCH == 0x4A

    def test_german(self) -> None:
        assert LabelLanguage.GERMAN == 0x50

    def test_chinese(self) -> None:
        assert LabelLanguage.CHINESE == 0xCA


class TestLabelConstants:
    """Verify label encoding constants."""

    def test_opcode_mask(self) -> None:
        """LABEL_OPCODE_MASK = 0xA0 = %10100000."""
        assert LABEL_OPCODE_MASK == 0xA0

    def test_max_text_length(self) -> None:
        """Max 16 ASCII text bytes."""
        assert LABEL_MAX_TEXT_LENGTH == 16

    def test_min_arg_count(self) -> None:
        """Minimum 3 args: group + options + language."""
        assert LABEL_MIN_ARG_COUNT == 3

    def test_opcode_range(self) -> None:
        """Label opcode should be 0xA3 (empty) to 0xB3 (16 chars)."""
        min_opcode = LABEL_OPCODE_MASK | LABEL_MIN_ARG_COUNT
        max_opcode = LABEL_OPCODE_MASK | (LABEL_MIN_ARG_COUNT + LABEL_MAX_TEXT_LENGTH)
        assert min_opcode == 0xA3
        assert max_opcode == 0xB3
