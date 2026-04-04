"""DataUpdateCoordinator for C-Bus.

The coordinator sits between the Home Assistant entity platforms and the
pycbus protocol layer.  Its responsibilities:

1. **Lifecycle management** -- create, start, and stop the
   :class:`pycbus.protocol.CbusProtocol` state machine.
2. **State cache** -- maintain a dict of ``{(app_id, group): level}``
   representing the last-known state of every group on the bus.
3. **Event dispatch** -- when the protocol receives a monitor SAL event
   (e.g. a level change from a wall switch), update the cache and call
   ``async_set_updated_data()`` to notify all listening entities.
4. **Command proxy** -- entity platforms call coordinator methods
   (e.g. ``async_turn_on(group, level, ramp)``) which encode the SAL
   command and queue it for transmission.

Refresh model:
    This coordinator does **not** poll.  C-Bus is inherently push-based:
    the PCI/CNI sends monitor events for every SAL on the network.
    The coordinator's ``_async_update_data`` is a no-op; all state
    changes flow through the protocol's event callback.
"""

from __future__ import annotations

import bisect
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from pycbus.commands import (
    lighting_off,
    lighting_on,
    lighting_ramp,
    lighting_terminate_ramp,
)
from pycbus.constants import (
    RAMP_DURATIONS,
    ApplicationId,
    LightingCommand,
)
from pycbus.exceptions import CbusConnectionError
from pycbus.protocol import CbusProtocol
from pycbus.transport import SerialTransport, TcpTransport

from .const import (
    CONF_SERIAL_PORT,
    CONF_TRANSPORT,
    DEFAULT_PORT,
    DOMAIN,
    TRANSPORT_SERIAL,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Type alias for the group state cache.
# Key: (app_id, group_address), Value: level (0-255).
type GroupStateDict = dict[tuple[int, int], int]


def _closest_ramp_rate(seconds: float) -> LightingCommand:
    """Find the C-Bus ramp opcode closest to the requested duration.

    Uses binary search on the pre-sorted :data:`RAMP_DURATIONS` table.

    Args:
        seconds: Desired transition time in seconds.

    Returns:
        The ``LightingCommand`` ramp opcode with the closest duration.
    """
    durations = [d for d, _ in RAMP_DURATIONS]
    idx = bisect.bisect_left(durations, seconds)

    if idx == 0:
        return RAMP_DURATIONS[0][1]
    if idx >= len(RAMP_DURATIONS):
        return RAMP_DURATIONS[-1][1]

    # Pick whichever neighbour is closer.
    before_dur, before_cmd = RAMP_DURATIONS[idx - 1]
    after_dur, after_cmd = RAMP_DURATIONS[idx]

    if (seconds - before_dur) <= (after_dur - seconds):
        return before_cmd
    return after_cmd


class CbusCoordinator(DataUpdateCoordinator[GroupStateDict]):
    """Coordinator for a single C-Bus network connection.

    Creates and manages a :class:`CbusProtocol` connected via
    :class:`TcpTransport`.  Listens for SAL monitor events and
    maintains a live state cache of group levels.

    Entity platforms read ``self.data[(app_id, group)]`` for current
    state and call ``async_light_on`` / ``async_light_off`` /
    ``async_light_ramp`` to issue commands.
    """

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
        )
        self._entry = entry
        self._protocol: CbusProtocol | None = None
        self._unsubscribe_events: Any = None

        # Initialise the state cache.
        self.data: GroupStateDict = {}

    @property
    def protocol(self) -> CbusProtocol | None:
        """The underlying protocol handler, if connected."""
        return self._protocol

    async def async_setup(self) -> None:
        """Create the transport + protocol and connect to the PCI/CNI.

        Called from ``async_setup_entry``.  On success the protocol is
        in READY state and the coordinator is receiving SAL events.

        Raises:
            CbusConnectionError: If the connection fails.
        """
        transport_type: str = self._entry.data.get(CONF_TRANSPORT, "tcp")

        if transport_type == TRANSPORT_SERIAL:
            serial_port: str = self._entry.data[CONF_SERIAL_PORT]
            transport = SerialTransport(url=serial_port)
            _LOGGER.info("C-Bus coordinator using serial transport: %s", serial_port)
        else:
            host: str = self._entry.data.get("host", "")
            port: int = self._entry.data.get("port", DEFAULT_PORT)
            transport = TcpTransport(host=host, port=port)
            _LOGGER.info("C-Bus coordinator using TCP transport: %s:%d", host, port)

        self._protocol = CbusProtocol(transport)

        await self._protocol.connect()

        # Register for SAL monitor events.
        self._unsubscribe_events = self._protocol.on_event(self._handle_sal_event)

        _LOGGER.info("C-Bus coordinator connected")

    async def async_shutdown(self) -> None:
        """Disconnect from the PCI/CNI and clean up.

        Called from ``async_unload_entry``.
        """
        if self._unsubscribe_events is not None:
            self._unsubscribe_events()
            self._unsubscribe_events = None

        if self._protocol is not None:
            await self._protocol.disconnect()
            self._protocol = None

        _LOGGER.info("C-Bus coordinator disconnected")

    async def _async_update_data(self) -> GroupStateDict:
        """No-op: C-Bus is push-based, state flows through events."""
        return self.data

    # ------------------------------------------------------------------
    # Command methods (called by entity platforms)
    # ------------------------------------------------------------------

    async def async_light_on(self, group: int, network: int = 0) -> None:
        """Turn a lighting group on (full brightness).

        Args:
            group: Target group address (0-255).
            network: C-Bus network number (default 0).
        """
        cmd = lighting_on(group=group, network=network)
        if await self._send(cmd):
            self._update_level(ApplicationId.LIGHTING, group, 0xFF)

    async def async_light_off(self, group: int, network: int = 0) -> None:
        """Turn a lighting group off.

        Args:
            group: Target group address (0-255).
            network: C-Bus network number (default 0).
        """
        cmd = lighting_off(group=group, network=network)
        if await self._send(cmd):
            self._update_level(ApplicationId.LIGHTING, group, 0x00)

    async def async_light_ramp(
        self,
        group: int,
        level: int,
        transition: float = 0.0,
        network: int = 0,
    ) -> None:
        """Ramp a lighting group to a specific level.

        Args:
            group: Target group address (0-255).
            level: Target brightness (0-255).
            transition: Fade duration in seconds (picks closest ramp rate).
            network: C-Bus network number (default 0).
        """
        rate = _closest_ramp_rate(transition)
        cmd = lighting_ramp(group=group, level=level, rate=rate, network=network)
        if await self._send(cmd):
            self._update_level(ApplicationId.LIGHTING, group, level)

    async def async_light_terminate_ramp(self, group: int, network: int = 0) -> None:
        """Stop a running ramp on a lighting group.

        Args:
            group: Target group address (0-255).
            network: C-Bus network number (default 0).
        """
        cmd = lighting_terminate_ramp(group=group, network=network)
        await self._send(cmd)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _send(self, cmd_bytes: bytes) -> bool:
        """Hex-encode and send a command via the protocol.

        Args:
            cmd_bytes: Raw SAL command bytes (from pycbus.commands).

        Returns:
            ``True`` if the PCI confirmed the command, ``False`` otherwise.

        Raises:
            CbusConnectionError: If not connected.
        """
        if self._protocol is None:
            raise CbusConnectionError("Coordinator not connected")

        hex_payload = cmd_bytes.hex().upper().encode()
        confirmed = await self._protocol.send_command(hex_payload)
        if not confirmed:
            _LOGGER.warning("PCI rejected command: %s", hex_payload.decode())
        return confirmed

    def _update_level(self, app_id: int, group: int, level: int) -> None:
        """Update the state cache and notify entities."""
        self.data[(app_id, group)] = level
        self.async_set_updated_data(self.data)

    def _handle_sal_event(self, sal_bytes: bytes) -> None:
        """Parse an incoming SAL event and update state cache.

        SAL monitor events for Lighting (app 56) have the structure::

            05 38 00 <opcode> <group> [<level>] <checksum>

        The checksum has already been verified by the protocol layer.

        Args:
            sal_bytes: Raw decoded SAL bytes (checksum included).
        """
        if len(sal_bytes) < 5:
            return

        # Byte 0: DAT (0x05 = broadcast)
        # Byte 1: application ID
        # Byte 2: network (0x00)
        # Byte 3: opcode
        # Byte 4: group address
        # Byte 5: level (optional, present for ON/RAMP)
        app_id = sal_bytes[1]
        opcode = sal_bytes[3]
        group = sal_bytes[4]

        if app_id == ApplicationId.LIGHTING:
            self._handle_lighting_event(opcode, group, sal_bytes)

    def _handle_lighting_event(self, opcode: int, group: int, sal_bytes: bytes) -> None:
        """Handle a Lighting application SAL event.

        Args:
            opcode: The SAL opcode byte.
            group: The target group address.
            sal_bytes: Full SAL frame bytes.
        """
        try:
            cmd = LightingCommand(opcode)
        except ValueError:
            _LOGGER.debug("Unknown lighting opcode: 0x%02X", opcode)
            return

        if cmd == LightingCommand.OFF:
            self._update_level(ApplicationId.LIGHTING, group, 0x00)
        elif cmd == LightingCommand.ON:
            level = sal_bytes[5] if len(sal_bytes) > 5 else 0xFF
            self._update_level(ApplicationId.LIGHTING, group, level)
        elif cmd == LightingCommand.TERMINATE_RAMP:
            pass  # Level unchanged; stays at current position.
        else:
            # Ramp command — extract the target level.
            if len(sal_bytes) > 5:
                level = sal_bytes[5]
                self._update_level(ApplicationId.LIGHTING, group, level)
