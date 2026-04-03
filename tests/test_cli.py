"""Tests for pycbus CLI (command-line interface).

The CLI allows testing C-Bus commands without Home Assistant.
These tests exercise the offline sub-commands (build, checksum)
that don't require a live C-Bus interface.

Covers:
    - ``build on``  — verify output format and checksum validity.
    - ``build off`` — verify OFF command structure.
    - ``build ramp`` — verify ramp with duration parsing.
    - ``build terminate`` — verify terminate ramp command.
    - ``checksum`` — compute mode.
    - ``checksum --verify`` — verification mode (valid and invalid).
    - No arguments — prints help without error.
    - Unknown command — returns non-zero exit code.
"""

from __future__ import annotations

from pycbus.cli import main


class TestCliBuild:
    """Tests for the ``build`` sub-command."""

    def test_build_on(self, capsys) -> None:  # type: ignore[no-untyped-def]
        """``build on --group 1`` should exit 0 and show valid checksum."""
        exit_code = main(["build", "on", "--group", "1"])
        assert exit_code == 0
        output = capsys.readouterr().out
        assert "Lighting ON" in output
        assert "valid" in output

    def test_build_off(self, capsys) -> None:  # type: ignore[no-untyped-def]
        """``build off --group 5`` should exit 0."""
        exit_code = main(["build", "off", "--group", "5"])
        assert exit_code == 0
        output = capsys.readouterr().out
        assert "Lighting OFF" in output

    def test_build_ramp_with_rate(self, capsys) -> None:  # type: ignore[no-untyped-def]
        """``build ramp --group 10 --level 128 --rate 4s`` should exit 0."""
        exit_code = main(
            ["build", "ramp", "--group", "10", "--level", "128", "--rate", "4s"]
        )
        assert exit_code == 0
        output = capsys.readouterr().out
        assert "Lighting RAMP" in output
        assert "128" in output

    def test_build_ramp_default_rate(self, capsys) -> None:  # type: ignore[no-untyped-def]
        """Ramp without --rate should default to RAMP_INSTANT."""
        exit_code = main(["build", "ramp", "--group", "1", "--level", "200"])
        assert exit_code == 0
        output = capsys.readouterr().out
        assert "RAMP_INSTANT" in output

    def test_build_terminate(self, capsys) -> None:  # type: ignore[no-untyped-def]
        """``build terminate --group 3`` should exit 0."""
        exit_code = main(["build", "terminate", "--group", "3"])
        assert exit_code == 0
        output = capsys.readouterr().out
        assert "TERMINATE RAMP" in output

    def test_build_with_network(self, capsys) -> None:  # type: ignore[no-untyped-def]
        """``--network 254`` should be accepted."""
        exit_code = main(["build", "on", "--group", "1", "--network", "254"])
        assert exit_code == 0


class TestCliChecksum:
    """Tests for the ``checksum`` sub-command."""

    def test_compute_checksum(self, capsys) -> None:  # type: ignore[no-untyped-def]
        """Compute checksum for known Lighting ON payload."""
        exit_code = main(["checksum", "05", "38", "00", "79", "01", "FF"])
        assert exit_code == 0
        output = capsys.readouterr().out
        assert "0x" in output

    def test_compute_checksum_joined_hex(self, capsys) -> None:  # type: ignore[no-untyped-def]
        """Accept joined hex string as well as separated."""
        exit_code = main(["checksum", "0538007901FF"])
        assert exit_code == 0

    def test_verify_valid(self, capsys) -> None:  # type: ignore[no-untyped-def]
        """Verify a correct checksum returns exit code 0."""
        # 05 38 00 79 01 FF + checksum 4A
        exit_code = main(
            ["checksum", "--verify", "05", "38", "00", "79", "01", "FF", "4A"]
        )
        assert exit_code == 0
        output = capsys.readouterr().out
        assert "YES" in output

    def test_verify_invalid(self, capsys) -> None:  # type: ignore[no-untyped-def]
        """Verify a bad checksum returns exit code 1."""
        exit_code = main(
            ["checksum", "--verify", "05", "38", "00", "79", "01", "FF", "00"]
        )
        assert exit_code == 1
        output = capsys.readouterr().out
        assert "NO" in output


class TestCliMisc:
    """Tests for edge cases and error handling."""

    def test_no_arguments_shows_help(self, capsys) -> None:  # type: ignore[no-untyped-def]
        """No arguments should print help and exit 0."""
        exit_code = main([])
        assert exit_code == 0

    def test_send_not_implemented(self, capsys) -> None:  # type: ignore[no-untyped-def]
        """``send`` should print not-implemented message."""
        exit_code = main(["send", "--host", "127.0.0.1", "on", "--group", "1"])
        assert exit_code == 1

    def test_monitor_not_implemented(self, capsys) -> None:  # type: ignore[no-untyped-def]
        """``monitor`` should print not-implemented message."""
        exit_code = main(["monitor", "--host", "127.0.0.1"])
        assert exit_code == 1
