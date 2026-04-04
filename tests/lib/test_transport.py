"""Tests for pycbus transport layer (TcpTransport and SerialTransport).

Tests use mock readers/writers to simulate TCP and serial connections
without needing real hardware or network access.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pycbus.exceptions import CbusConnectionError, CbusTimeoutError
from pycbus.transport import SerialTransport, TcpTransport

# ---------------------------------------------------------------------------
# Helpers — fake asyncio StreamReader / StreamWriter
# ---------------------------------------------------------------------------


def _make_reader(lines: list[bytes]) -> asyncio.StreamReader:
    """Create a StreamReader pre-loaded with CR-terminated lines."""
    reader = asyncio.StreamReader()
    for line in lines:
        reader.feed_data(line)
    return reader


def _make_writer() -> MagicMock:
    """Create a mock StreamWriter with async drain and close."""
    writer = MagicMock(spec=asyncio.StreamWriter)
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    writer.is_closing = MagicMock(return_value=False)
    return writer


# ===========================================================================
# TcpTransport
# ===========================================================================


class TestTcpTransportProperties:
    """Test TcpTransport property accessors."""

    def test_defaults(self) -> None:
        t = TcpTransport(host="10.0.0.1")
        assert t.host == "10.0.0.1"
        assert t.port == 10001
        assert t.connected is False

    def test_custom_port(self) -> None:
        t = TcpTransport(host="10.0.0.1", port=9999)
        assert t.port == 9999


class TestTcpTransportConnect:
    """Test TcpTransport.connect()."""

    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        t = TcpTransport(host="10.0.0.1")
        reader = _make_reader([])
        writer = _make_writer()

        with patch("asyncio.open_connection", return_value=(reader, writer)):
            await t.connect()

        assert t.connected is True

    @pytest.mark.asyncio
    async def test_connect_already_connected(self) -> None:
        """Calling connect() twice is a no-op."""
        t = TcpTransport(host="10.0.0.1")
        reader = _make_reader([])
        writer = _make_writer()

        with patch("asyncio.open_connection", return_value=(reader, writer)) as mock:
            await t.connect()
            await t.connect()  # second call should not reconnect
            assert mock.call_count == 1

    @pytest.mark.asyncio
    async def test_connect_timeout(self) -> None:
        t = TcpTransport(host="10.0.0.1", timeout=0.01)

        async def _hang(
            *_args: object, **_kwargs: object
        ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
            await asyncio.sleep(10)
            raise AssertionError("Should not reach here")

        with (
            patch("asyncio.open_connection", side_effect=_hang),
            pytest.raises(CbusTimeoutError, match="Timeout connecting"),
        ):
            await t.connect()

    @pytest.mark.asyncio
    async def test_connect_refused(self) -> None:
        t = TcpTransport(host="10.0.0.1")

        with (
            patch(
                "asyncio.open_connection",
                side_effect=OSError("Connection refused"),
            ),
            pytest.raises(CbusConnectionError, match="Cannot connect"),
        ):
            await t.connect()


class TestTcpTransportDisconnect:
    """Test TcpTransport.disconnect()."""

    @pytest.mark.asyncio
    async def test_disconnect(self) -> None:
        t = TcpTransport(host="10.0.0.1")
        reader = _make_reader([])
        writer = _make_writer()

        with patch("asyncio.open_connection", return_value=(reader, writer)):
            await t.connect()

        await t.disconnect()
        assert t.connected is False

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self) -> None:
        """Disconnecting when not connected is a no-op."""
        t = TcpTransport(host="10.0.0.1")
        await t.disconnect()  # should not raise


class TestTcpTransportReadLine:
    """Test TcpTransport.read_line()."""

    @pytest.mark.asyncio
    async def test_read_line(self) -> None:
        t = TcpTransport(host="10.0.0.1")
        reader = _make_reader([b"g#\r"])
        writer = _make_writer()

        with patch("asyncio.open_connection", return_value=(reader, writer)):
            await t.connect()

        line = await t.read_line()
        assert line == b"g#"

    @pytest.mark.asyncio
    async def test_read_line_strips_crlf(self) -> None:
        """Lines ending in CR+LF should strip both."""
        t = TcpTransport(host="10.0.0.1")
        reader = _make_reader([b"D838\r\n\r"])
        writer = _make_writer()

        with patch("asyncio.open_connection", return_value=(reader, writer)):
            await t.connect()

        # readuntil(\r) will read up to first \r; the \n is left in buffer
        line = await t.read_line()
        assert line == b"D838"

    @pytest.mark.asyncio
    async def test_read_line_crlf_no_corruption(self) -> None:
        """CRLF-terminated frames must not corrupt the next read."""
        t = TcpTransport(host="10.0.0.1")
        reader = _make_reader([b"D838\r\nNEXT\r"])
        writer = _make_writer()

        with patch("asyncio.open_connection", return_value=(reader, writer)):
            await t.connect()

        line = await t.read_line()
        assert line == b"D838"

        next_line = await t.read_line()
        assert next_line == b"NEXT"

    @pytest.mark.asyncio
    async def test_read_line_not_connected(self) -> None:
        t = TcpTransport(host="10.0.0.1")
        with pytest.raises(CbusConnectionError, match="Not connected"):
            await t.read_line()

    @pytest.mark.asyncio
    async def test_read_line_timeout(self) -> None:
        t = TcpTransport(host="10.0.0.1", timeout=0.01)
        reader = _make_reader([])  # empty — will timeout
        writer = _make_writer()

        with patch("asyncio.open_connection", return_value=(reader, writer)):
            await t.connect()

        with pytest.raises(CbusTimeoutError, match="Timeout waiting"):
            await t.read_line()

    @pytest.mark.asyncio
    async def test_read_line_connection_reset(self) -> None:
        t = TcpTransport(host="10.0.0.1")
        reader = asyncio.StreamReader()
        writer = _make_writer()

        with patch("asyncio.open_connection", return_value=(reader, writer)):
            await t.connect()

        # Feed EOF to simulate connection drop
        reader.feed_eof()
        with pytest.raises(CbusConnectionError, match="Connection lost"):
            await t.read_line()
        assert t.connected is False


class TestTcpTransportWrite:
    """Test TcpTransport.write()."""

    @pytest.mark.asyncio
    async def test_write(self) -> None:
        t = TcpTransport(host="10.0.0.1")
        reader = _make_reader([])
        writer = _make_writer()

        with patch("asyncio.open_connection", return_value=(reader, writer)):
            await t.connect()

        await t.write(b"\\0538007901FF50\r")
        writer.write.assert_called_once_with(b"\\0538007901FF50\r")
        writer.drain.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_write_not_connected(self) -> None:
        t = TcpTransport(host="10.0.0.1")
        with pytest.raises(CbusConnectionError, match="Not connected"):
            await t.write(b"test")

    @pytest.mark.asyncio
    async def test_write_broken_pipe(self) -> None:
        t = TcpTransport(host="10.0.0.1")
        reader = _make_reader([])
        writer = _make_writer()
        writer.drain.side_effect = BrokenPipeError("Broken pipe")

        with patch("asyncio.open_connection", return_value=(reader, writer)):
            await t.connect()

        with pytest.raises(CbusConnectionError, match="Write failed"):
            await t.write(b"test")
        assert t.connected is False


# ===========================================================================
# SerialTransport
# ===========================================================================


class TestSerialTransportProperties:
    """Test SerialTransport property accessors."""

    def test_defaults(self) -> None:
        t = SerialTransport(url="/dev/ttyUSB0")
        assert t.url == "/dev/ttyUSB0"
        assert t.baud == 9600
        assert t.connected is False

    def test_custom_baud(self) -> None:
        t = SerialTransport(url="/dev/ttyUSB0", baud=115200)
        assert t.baud == 115200


class TestSerialTransportConnect:
    """Test SerialTransport.connect()."""

    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        t = SerialTransport(url="/dev/ttyUSB0")
        reader = _make_reader([])
        writer = _make_writer()

        mock_serial = MagicMock()
        mock_serial.open_serial_connection = AsyncMock(return_value=(reader, writer))

        with patch.dict("sys.modules", {"serial_asyncio": mock_serial}):
            await t.connect()

        assert t.connected is True

    @pytest.mark.asyncio
    async def test_connect_already_connected(self) -> None:
        t = SerialTransport(url="/dev/ttyUSB0")
        reader = _make_reader([])
        writer = _make_writer()

        mock_serial = MagicMock()
        mock_serial.open_serial_connection = AsyncMock(return_value=(reader, writer))

        with patch.dict("sys.modules", {"serial_asyncio": mock_serial}):
            await t.connect()
            await t.connect()  # no-op
            assert mock_serial.open_serial_connection.call_count == 1

    @pytest.mark.asyncio
    async def test_connect_device_not_found(self) -> None:
        t = SerialTransport(url="/dev/nonexistent")

        mock_serial = MagicMock()
        mock_serial.open_serial_connection = AsyncMock(
            side_effect=OSError("No such device")
        )

        with (
            patch.dict("sys.modules", {"serial_asyncio": mock_serial}),
            pytest.raises(CbusConnectionError, match="Cannot open serial"),
        ):
            await t.connect()


class TestSerialTransportDisconnect:
    """Test SerialTransport.disconnect()."""

    @pytest.mark.asyncio
    async def test_disconnect(self) -> None:
        t = SerialTransport(url="/dev/ttyUSB0")
        reader = _make_reader([])
        writer = _make_writer()

        mock_serial = MagicMock()
        mock_serial.open_serial_connection = AsyncMock(return_value=(reader, writer))

        with patch.dict("sys.modules", {"serial_asyncio": mock_serial}):
            await t.connect()

        await t.disconnect()
        assert t.connected is False

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self) -> None:
        t = SerialTransport(url="/dev/ttyUSB0")
        await t.disconnect()


class TestSerialTransportReadLine:
    """Test SerialTransport.read_line()."""

    @pytest.mark.asyncio
    async def test_read_line(self) -> None:
        t = SerialTransport(url="/dev/ttyUSB0")
        reader = _make_reader([b"g#\r"])
        writer = _make_writer()

        mock_serial = MagicMock()
        mock_serial.open_serial_connection = AsyncMock(return_value=(reader, writer))

        with patch.dict("sys.modules", {"serial_asyncio": mock_serial}):
            await t.connect()

        line = await t.read_line()
        assert line == b"g#"

    @pytest.mark.asyncio
    async def test_read_line_not_connected(self) -> None:
        t = SerialTransport(url="/dev/ttyUSB0")
        with pytest.raises(CbusConnectionError, match="Not connected"):
            await t.read_line()

    @pytest.mark.asyncio
    async def test_read_line_timeout(self) -> None:
        t = SerialTransport(url="/dev/ttyUSB0", timeout=0.01)
        reader = _make_reader([])
        writer = _make_writer()

        mock_serial = MagicMock()
        mock_serial.open_serial_connection = AsyncMock(return_value=(reader, writer))

        with patch.dict("sys.modules", {"serial_asyncio": mock_serial}):
            await t.connect()

        with pytest.raises(CbusTimeoutError, match="Timeout waiting"):
            await t.read_line()


class TestSerialTransportWrite:
    """Test SerialTransport.write()."""

    @pytest.mark.asyncio
    async def test_write(self) -> None:
        t = SerialTransport(url="/dev/ttyUSB0")
        reader = _make_reader([])
        writer = _make_writer()

        mock_serial = MagicMock()
        mock_serial.open_serial_connection = AsyncMock(return_value=(reader, writer))

        with patch.dict("sys.modules", {"serial_asyncio": mock_serial}):
            await t.connect()

        await t.write(b"\\0538007901FF50\r")
        writer.write.assert_called_once_with(b"\\0538007901FF50\r")
        writer.drain.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_write_not_connected(self) -> None:
        t = SerialTransport(url="/dev/ttyUSB0")
        with pytest.raises(CbusConnectionError, match="Not connected"):
            await t.write(b"test")

    @pytest.mark.asyncio
    async def test_write_oserror(self) -> None:
        t = SerialTransport(url="/dev/ttyUSB0")
        reader = _make_reader([])
        writer = _make_writer()
        writer.drain.side_effect = OSError("Device removed")

        mock_serial = MagicMock()
        mock_serial.open_serial_connection = AsyncMock(return_value=(reader, writer))

        with patch.dict("sys.modules", {"serial_asyncio": mock_serial}):
            await t.connect()

        with pytest.raises(CbusConnectionError, match="Write failed"):
            await t.write(b"test")
        assert t.connected is False


# ===========================================================================
# Structural typing — both classes satisfy CbusTransport protocol
# ===========================================================================


class TestProtocolConformance:
    """Verify TcpTransport and SerialTransport satisfy CbusTransport."""

    def test_tcp_is_cbus_transport(self) -> None:
        from pycbus.transport import CbusTransport

        t: CbusTransport = TcpTransport(host="10.0.0.1")
        assert hasattr(t, "connect")
        assert hasattr(t, "disconnect")
        assert hasattr(t, "read_line")
        assert hasattr(t, "write")
        assert hasattr(t, "connected")

    def test_serial_is_cbus_transport(self) -> None:
        from pycbus.transport import CbusTransport

        t: CbusTransport = SerialTransport(url="/dev/ttyUSB0")
        assert hasattr(t, "connect")
        assert hasattr(t, "disconnect")
        assert hasattr(t, "read_line")
        assert hasattr(t, "write")
        assert hasattr(t, "connected")
