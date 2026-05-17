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
import copy
import logging
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import AUTH_CMD, CHAR_NOTIFY_UUID, CHAR_WRITE_UUID, DOMAIN, SERVICE_UUID_1
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
        self._write_char = None          # stored after connect for later writes
        self._connect_task: asyncio.Task | None = None
        self._cancel_bluetooth_cb: callable | None = None

        # Shared state object mutated in-place by the parser
        self.data = AiBBQState()

        # HA-managed temperature thresholds (not written to device)
        self._ha_min_temp: float | None = None
        self._ha_max_temp: float | None = None
        self._low_alarm_enabled: bool = False
        self._high_alarm_enabled: bool = False
        self._low_alarm_triggered: bool = False
        self._high_alarm_triggered: bool = False

        # Connection control
        self._connect_enabled: bool = True
        self._rssi: float | None = None

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
        self._rssi = service_info.rssi
        self.async_set_updated_data(copy.copy(self.data))
        if change == BluetoothChange.ADVERTISEMENT and not self._is_connected:
            _LOGGER.debug("Advertisement from %s — scheduling connect", self._address)
            self._schedule_connect()

    # ── Connection management ─────────────────────────────────────────────────

    @property
    def _is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    def _schedule_connect(self) -> None:
        """Schedule a connection attempt unless one is already running."""
        if not self._connect_enabled:
            return
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
            client = await establish_connection(
                BleakClient,
                ble_device,
                self._address,
                disconnected_callback=self._async_on_disconnect,
            )
            self._client = client

            # Device exposes two services with identical characteristic UUIDs;
            # scope to SERVICE_UUID_1 to get an unambiguous characteristic reference.
            service = client.services.get_service(SERVICE_UUID_1)
            notify_char = service.get_characteristic(CHAR_NOTIFY_UUID)
            write_char = service.get_characteristic(CHAR_WRITE_UUID)

            await client.start_notify(notify_char, self._async_on_notification)
            await client.write_gatt_char(write_char, AUTH_CMD, response=False)
            self._write_char = write_char   # keep for later writes (target temp, etc.)

            _LOGGER.info("Connected to AiBBQ %s", self._address)

            self.async_set_updated_data(copy.copy(self.data))

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
        self._write_char = None
        self.async_set_updated_data(copy.copy(self.data))

    async def _async_disconnect(self) -> None:
        """Disconnect cleanly if connected."""
        if self._client and self._client.is_connected:
            try:
                await self._client.disconnect()
            except BleakError:
                pass
        self._client = None

    # ── Connection state ─────────────────────────────────────────────────────

    @property
    def connect_enabled(self) -> bool:
        return self._connect_enabled

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def rssi(self) -> float | None:
        return self._rssi

    async def async_set_connect_enabled(self, enabled: bool) -> None:
        """Enable or disable BLE auto-connect and update HA state."""
        self._connect_enabled = enabled
        if not enabled:
            if self._connect_task and not self._connect_task.done():
                self._connect_task.cancel()
                try:
                    await self._connect_task
                except asyncio.CancelledError:
                    pass
            await self._async_disconnect()
        else:
            self._schedule_connect()
        self.async_set_updated_data(copy.copy(self.data))

    # ── Temperature thresholds & alarms ──────────────────────────────────────

    @property
    def ha_min_temp(self) -> float | None:
        return self._ha_min_temp

    @property
    def ha_max_temp(self) -> float | None:
        return self._ha_max_temp

    @property
    def low_alarm_enabled(self) -> bool:
        return self._low_alarm_enabled

    @property
    def high_alarm_enabled(self) -> bool:
        return self._high_alarm_enabled

    @property
    def alarm_low_active(self) -> bool:
        if not self._low_alarm_enabled or self._ha_min_temp is None or self.data.current_temp is None:
            return False
        return self.data.current_temp <= self._ha_min_temp

    @property
    def alarm_high_active(self) -> bool:
        if not self._high_alarm_enabled or self._ha_max_temp is None or self.data.current_temp is None:
            return False
        return self.data.current_temp >= self._ha_max_temp

    async def async_set_min_temp(self, temp: float) -> None:
        self._ha_min_temp = temp
        self._low_alarm_triggered = False
        self.async_set_updated_data(copy.copy(self.data))

    async def async_set_max_temp(self, temp: float) -> None:
        self._ha_max_temp = temp
        self._high_alarm_triggered = False
        self.async_set_updated_data(copy.copy(self.data))

    def set_low_alarm_enabled(self, enabled: bool) -> None:
        self._low_alarm_enabled = enabled
        self._low_alarm_triggered = False
        self.async_set_updated_data(copy.copy(self.data))

    def set_high_alarm_enabled(self, enabled: bool) -> None:
        self._high_alarm_enabled = enabled
        self._high_alarm_triggered = False
        self.async_set_updated_data(copy.copy(self.data))

    @callback
    def _check_alarms(self) -> None:
        temp = self.data.current_temp
        if temp is None:
            return
        if self._low_alarm_enabled and self._ha_min_temp is not None:
            if not self._low_alarm_triggered and temp <= self._ha_min_temp:
                self._low_alarm_triggered = True
                self._fire_alarm(
                    "low", temp, self._ha_min_temp,
                    f"Probe dropped to {temp:.0f} °C — below minimum of {self._ha_min_temp:.0f} °C.",
                    "AiBBQ: Low temperature alarm",
                    f"{DOMAIN}_alarm_low",
                )
            elif self._low_alarm_triggered and temp > self._ha_min_temp + 1:
                self._low_alarm_triggered = False

        if self._high_alarm_enabled and self._ha_max_temp is not None:
            if not self._high_alarm_triggered and temp >= self._ha_max_temp:
                self._high_alarm_triggered = True
                self._fire_alarm(
                    "high", temp, self._ha_max_temp,
                    f"Probe reached {temp:.0f} °C — above maximum of {self._ha_max_temp:.0f} °C.",
                    "AiBBQ: High temperature alarm",
                    f"{DOMAIN}_alarm_high",
                )
            elif self._high_alarm_triggered and temp < self._ha_max_temp - 1:
                self._high_alarm_triggered = False

    @callback
    def _fire_alarm(
        self,
        kind: str,
        temp: float,
        threshold: float,
        message: str,
        title: str,
        notification_id: str,
    ) -> None:
        # Persistent notification — works out of the box, no user config needed
        self.hass.async_create_task(
            self.hass.services.async_call(
                "persistent_notification",
                "create",
                {"message": message, "title": title, "notification_id": notification_id},
            )
        )
        # HA event — lets automations react with any notifier / logic
        self.hass.bus.async_fire(
            f"{DOMAIN}_alarm",
            {
                "kind": kind,
                "current_temp": temp,
                "threshold": threshold,
                "device_address": self._address,
                "message": message,
            },
        )

    # ── Notification handler ──────────────────────────────────────────────────

    @callback
    def _async_on_notification(self, sender: int, raw: bytearray) -> None:
        """Decode incoming BLE frame(s) and push updated state to HA."""
        updated = process_notification(bytes(raw), self.data)
        if updated:
            # Device stops advertising while connected, so refresh RSSI from HA's cache.
            service_info = bluetooth.async_last_service_info(
                self.hass, self._address, connectable=True
            )
            if service_info is not None:
                self._rssi = service_info.rssi
            _LOGGER.debug(
                "Notification: temp=%s °C target=%s",
                f"{self.data.best_temp:.0f}" if self.data.best_temp is not None else "—",
                f"{self.data.target_temp:.0f} °C" if self.data.target_temp is not None else "—",
            )
            self._check_alarms()
            # Push a *copy* so entity listeners see a new object reference
            self.async_set_updated_data(copy.copy(self.data))

    # ── DataUpdateCoordinator override ────────────────────────────────────────

    async def _async_update_data(self) -> AiBBQState:
        """
        Not used for scheduled polling (update_interval=None).
        Required by the base class; returns current state.
        """
        return self.data
