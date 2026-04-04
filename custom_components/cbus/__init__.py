"""C-Bus integration for Home Assistant.

This custom integration provides native Home Assistant support for
Clipsal C-Bus home automation networks, communicating directly with a
PCI (serial) or CNI (TCP/IP) interface - no C-Gate middleware required.

Integration architecture::

    Home Assistant
    +-- config_flow.py   - UI-guided setup (TCP/serial, optional XML import)
    +-- coordinator.py   - manages pycbus Protocol lifecycle + state cache
    +-- entity.py        - shared base entity with device_info
    +-- light.py         - Lighting application (app 56) -> LightEntity
    +-- switch.py        - Enable Control (app 203) -> SwitchEntity
    +-- event.py         - Trigger Control (app 202) -> EventEntity

Versioning:
    The integration follows CalVer (YYYY.M.patch) to align with
    Home Assistant's release cadence.  The underlying pycbus library
    uses SemVer independently.

Setup entry points:
    - ``async_setup_entry``  - called when HA loads a config entry
    - ``async_unload_entry`` - called when HA removes/reloads the entry
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, PLATFORMS
from .coordinator import CbusCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

type CbusConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: CbusConfigEntry) -> bool:
    """Set up C-Bus from a config entry."""
    coordinator = CbusCoordinator(hass, entry)
    await coordinator.async_setup()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        await coordinator.async_shutdown()
        raise

    return True


async def async_unload_entry(hass: HomeAssistant, entry: CbusConfigEntry) -> bool:
    """Unload a C-Bus config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: CbusCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unload_ok
