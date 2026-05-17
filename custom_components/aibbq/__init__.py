"""AiBBQ Life Thermometer — Home Assistant integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import AiBBQCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AiBBQ from a config entry."""
    address: str = entry.data[CONF_ADDRESS]

    # Ensure unique_id is set (may be missing on entries created before v0.1)
    if not entry.unique_id:
        hass.config_entries.async_update_entry(entry, unique_id=address)

    coordinator = AiBBQCoordinator(hass, entry)

    # Kick off the BLE connection
    await coordinator.async_setup()

    # Store coordinator for use by platform modules
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Set up sensor (and any future) platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Clean up on unload
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: AiBBQCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update (reload the entry)."""
    await hass.config_entries.async_reload(entry.entry_id)
