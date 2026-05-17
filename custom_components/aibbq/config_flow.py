"""Config flow for AiBBQ Life integration.

Two entry paths:
  1. Bluetooth autodiscovery  — HA sees an "AIBBQLife" advertisement and calls
     async_step_bluetooth().  User just confirms.
  2. Manual setup             — User opens "Add Integration", picks aibbq, and
     chooses from a dropdown of discovered devices.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import DEVICE_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


class AiBBQConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the AiBBQ Life config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, str] = {}  # address → title

    # ── Path 1: Bluetooth autodiscovery ──────────────────────────────────────

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Called by HA when a matching BLE advertisement is received."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {
            "name": discovery_info.name or DEVICE_NAME
        }
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirmation step for auto-discovered device."""
        if user_input is not None:
            assert self._discovery_info is not None
            return self._async_create_entry(self._discovery_info.address)

        self._set_confirm_only()
        name = (self._discovery_info.name if self._discovery_info else None) or DEVICE_NAME
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": name},
        )

    # ── Path 2: Manual setup ─────────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual setup: show a picker of already-scanned AiBBQ devices."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self._async_create_entry(address)

        # Enumerate BLE devices seen by HA and filter to AiBBQ ones
        current_addresses = self._async_current_ids()
        self._discovered_devices = {}

        for service_info in async_discovered_service_info(self.hass, connectable=True):
            address = service_info.address
            if address in current_addresses:
                continue
            name = service_info.name or ""
            if DEVICE_NAME.lower() in name.lower():
                self._discovered_devices[address] = f"{name} ({address})"

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In(self._discovered_devices)}
            ),
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _async_create_entry(self, address: str) -> ConfigFlowResult:
        """Create the config entry."""
        return self.async_create_entry(
            title=DEVICE_NAME,
            data={CONF_ADDRESS: address},
        )
