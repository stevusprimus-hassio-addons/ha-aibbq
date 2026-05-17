"""
AiBBQ Life coordinator.

Manages the active BLE connection lifecycle:
  1. On startup, registers a bluetooth advertisement callback so HA tells us
     when the device is in range.
  2. When the device is seen (or on initial setup), opens a BleakClient,
     subscribes to GATT notifications, and sends the auth handshake.
  3. Every incoming notification is decoded by parser.py and pushed into HA
     via async_set_updated_data(), which wakes all subscribed sensor entities.
  4. On disconnect the client is cleaned up; the advertisement callback
     triggers an automatic reconnect on the next advertisement.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.exc import BleakError

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import AUTH_CMD, DOMAIN, NOTIFY_HANDLE, WRITE_HANDLE
from .parser import AiBBQState, process_notification

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

# How long to wait before retrying a failed connection (seconds)
_RECONNECT_DELAY = 10


class AiBBQCoordinator(DataUpdateCoordinator[AiBBQState]):
    """
    Coordinator for a single AiBBQ thermometer.

    Uses HA's bluetooth subsystem for device discovery and bleak for the
    active GATT connection.  Data is pushed (not polled): update_interval=None.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,   # push-only; we call async_set_updated_data()
        )
        self._address: str = entry.unique_id  # BLE MAC / UUID
        self._entry = entry
        self._client: BleakClient | None = None
        self._connect_task: asyncio.Task | None = None
        self._cancel_bluetooth_cb: callable | None = None

        # Shared state object mutated in-place by the parser
        self.data = AiBBQState()

    # ── Setup / Teardown ─────────────────────────────────────────────────────

    async def async_setup(self) -> None:
        """Register BT callback and attempt initial connection."""
        self._cancel_bluetooth_cb = bluetooth.async_register_callback(
            self.hass,
            self._async_on_advertisement,
            BluetoothCallbackMatcher(address=self._address),
            BluetoothScanningMode.ACTIVE,
        )
        # Try to connect immediately in case the device is already visible
        self._schedule_connect()

    async def async_shutdown(self) -> None:
        """Cancel tasks and disconnect cleanly."""
        if self._cancel_bluetooth_cb:
            self._cancel_bluetooth_cb()
            self._cancel_bluetooth_cb = None

        if self._connect_task and not self._connect_task.done():
            self._connect_task.cancel()

        await self._async_disconnect()

    # ── Bluetooth advertisement callback ─────────────────────────────────────

    @callback
    def _async_on_advertisement(
        self,
        service_info: BluetoothServiceInfoBleak,
        change: BluetoothChange,
    ) -> None:
        """Called by HA every time the device advertises."""
        if change == BluetoothChange.ADVERTISEMENT and not self._is_connected:
            _LOGGER.debug("Advertisement from %s — scheduling connect", self._address)
            self._schedule_connect()

    # ── Connection management ─────────────────────────────────────────────────

    @property
    def _is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    def _schedule_connect(self) -> None:
        """Schedule a connection attempt unless one is already running."""
        if self._connect_task and not self._connect_task.done():
            return
        self._connect_task = self.hass.async_create_task(
            self._async_connect(), eager_start=True
        )

    async def _async_connect(self) -> None:
        """Open BleakClient, subscribe to notifications, send auth command."""
        if self._is_connected:
            return

        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self._address, connectable=True
        )
        if ble_device is None:
            _LOGGER.debug("Device %s not found in BT cache — will retry on next ad", self._address)
            return

        _LOGGER.debug("Connecting to %s", self._address)
        try:
            client = BleakClient(
                ble_device,
                disconnected_callback=self._async_on_disconnect,
            )
            await client.connect()
            self._client = client

            # Subscribe to the notify characteristic
            await client.start_notify(NOTIFY_HANDLE, self._async_on_notification)

            # Send auth handshake — this triggers the device to start streaming
            await client.write_gatt_char(WRITE_HANDLE, AUTH_CMD, response=False)

            _LOGGER.info("Connected to AiBBQ %s", self._address)

        except (BleakError, asyncio.TimeoutError) as err:
            _LOGGER.warning("Failed to connect to %s: %s — retrying in %ds", self._address, err, _RECONNECT_DELAY)
            self._client = None
            await asyncio.sleep(_RECONNECT_DELAY)
            self._schedule_connect()

    @callback
    def _async_on_disconnect(self, client: BleakClient) -> None:
        """Handle unexpected disconnection."""
        _LOGGER.warning("Disconnected from AiBBQ %s — will reconnect on next advertisement", self._address)
        self._client = None

    async def _async_disconnect(self) -> None:
        """Disconnect cleanly if connected."""
        if self._client and self._client.is_connected:
            try:
                await self._client.disconnect()
            except BleakError:
                pass
        self._client = None

    # ── Notification handler ──────────────────────────────────────────────────

    @callback
    def _async_on_notification(self, sender: int, raw: bytearray) -> None:
        """Decode incoming BLE frame(s) and push updated state to HA."""
        updated = process_notification(bytes(raw), self.data)
        if updated:
            # Push a *copy* so entity listeners see a new object reference
            import copy
            self.async_set_updated_data(copy.copy(self.data))

    # ── DataUpdateCoordinator override ────────────────────────────────────────

    async def _async_update_data(self) -> AiBBQState:
        """
        Not used for scheduled polling (update_interval=None).
        Required by the base class; returns current state.
        """
        return self.data
