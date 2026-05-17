# Connect Switch & Connection Entities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Connect switch (controls auto-connect intent), a Connected binary sensor (reflects live BLE state), a Signal Strength sensor (RSSI, disabled by default), and a Battery sensor to the AiBBQ Home Assistant integration.

**Architecture:** Extend the coordinator with `_connect_enabled`, `_rssi`, and `_battery` fields plus an `async_set_connect_enabled` method. Push `async_set_updated_data` on connect/disconnect/advertisement so all new entities react to state changes. New entities follow existing `CoordinatorEntity` + descriptor patterns; the Connect switch gets its own class because it needs async BLE operations and defaults ON.

**Tech Stack:** Python 3.12+, Home Assistant core (`DataUpdateCoordinator`, `CoordinatorEntity`, `RestoreEntity`), Bleak BLE library, bleak-retry-connector.

> **Note:** This repo has no test infrastructure. Steps include manual HA verification instead of automated tests. Setting up `pytest-homeassistant-custom-component` is a separate future task.

---

## File Map

| File | Change |
|---|---|
| `custom_components/aibbq/const.py` | Add 4 new constant keys |
| `custom_components/aibbq/coordinator.py` | New fields/properties, `async_set_connect_enabled`, updated advertisement/connect/disconnect handlers |
| `custom_components/aibbq/binary_sensor.py` | Add Connected entry to `BINARY_SENSORS`; import `BinarySensorDeviceClass` |
| `custom_components/aibbq/switch.py` | Add `AiBBQConnectSwitch` class; update `async_setup_entry` |
| `custom_components/aibbq/sensor.py` | Change `value_fn` signature; add RSSI and Battery sensor entries |
| `custom_components/aibbq/strings.json` | Translation keys for 4 new entities |
| `custom_components/aibbq/translations/en.json` | English labels for 4 new entities |

---

### Task 1: Add constants

**Files:**
- Modify: `custom_components/aibbq/const.py`

- [ ] **Step 1: Add four new keys at the bottom of the HA section**

Open `custom_components/aibbq/const.py`. The last four lines currently read:

```python
SWITCH_ALARM_LOW_ENABLED  = "alarm_low_enabled"
SWITCH_ALARM_HIGH_ENABLED = "alarm_high_enabled"
```

Append after them:

```python
BINARY_SENSOR_CONNECTED   = "connected"
SWITCH_CONNECT            = "connect"
SENSOR_RSSI               = "rssi"
SENSOR_BATTERY            = "battery"
```

- [ ] **Step 2: Verify the file looks correct**

`const.py` HA section should now end with:

```python
BINARY_SENSOR_ALARM_LOW   = "alarm_low"
BINARY_SENSOR_ALARM_HIGH  = "alarm_high"
SWITCH_ALARM_LOW_ENABLED  = "alarm_low_enabled"
SWITCH_ALARM_HIGH_ENABLED = "alarm_high_enabled"
BINARY_SENSOR_CONNECTED   = "connected"
SWITCH_CONNECT            = "connect"
SENSOR_RSSI               = "rssi"
SENSOR_BATTERY            = "battery"
```

- [ ] **Step 3: Commit**

```bash
git add custom_components/aibbq/const.py
git commit -m "feat(aibbq): add constants for connect switch, connected sensor, RSSI, battery"
```

---

### Task 2: Extend coordinator — new fields, properties, and `async_set_connect_enabled`

**Files:**
- Modify: `custom_components/aibbq/coordinator.py`

- [ ] **Step 1: Add three new instance fields in `__init__`**

Locate the block that ends with:

```python
        self._low_alarm_triggered: bool = False
        self._high_alarm_triggered: bool = False
```

Add immediately after:

```python
        # Connection control
        self._connect_enabled: bool = True
        self._rssi: float | None = None
        self._battery: int | None = None
```

- [ ] **Step 2: Add four new public properties**

Locate the existing `# ── Temperature thresholds & alarms` section. Insert a new section directly above it:

```python
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

    @property
    def battery(self) -> int | None:
        return self._battery
```

- [ ] **Step 3: Add `async_set_connect_enabled` method**

Add this method immediately after the four new properties, still in the `# ── Connection state` section:

```python
    async def async_set_connect_enabled(self, enabled: bool) -> None:
        """Enable or disable BLE auto-connect and update HA state."""
        self._connect_enabled = enabled
        if not enabled:
            if self._connect_task and not self._connect_task.done():
                self._connect_task.cancel()
            await self._async_disconnect()
        else:
            self._schedule_connect()
        self.async_set_updated_data(copy.copy(self.data))
```

- [ ] **Step 4: Commit**

```bash
git add custom_components/aibbq/coordinator.py
git commit -m "feat(aibbq): add connect_enabled/rssi/battery fields and async_set_connect_enabled to coordinator"
```

---

### Task 3: Update coordinator connection handlers

**Files:**
- Modify: `custom_components/aibbq/coordinator.py`

- [ ] **Step 1: Update `_async_on_advertisement` to capture RSSI, guard on `_connect_enabled`, and always push update**

Replace the existing method:

```python
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
```

With:

```python
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
```

- [ ] **Step 2: Guard `_schedule_connect` with `_connect_enabled`**

Replace:

```python
    def _schedule_connect(self) -> None:
        """Schedule a connection attempt unless one is already running."""
        if self._connect_task and not self._connect_task.done():
            return
        self._connect_task = self.hass.async_create_task(
            self._async_connect(), eager_start=True
        )
```

With:

```python
    def _schedule_connect(self) -> None:
        """Schedule a connection attempt unless one is already running."""
        if not self._connect_enabled:
            return
        if self._connect_task and not self._connect_task.done():
            return
        self._connect_task = self.hass.async_create_task(
            self._async_connect(), eager_start=True
        )
```

- [ ] **Step 3: Read battery and push update in `_async_connect` after successful connection**

Locate the line in `_async_connect`:

```python
            _LOGGER.info("Connected to AiBBQ %s", self._address)
```

Add immediately after it (still inside the `try` block, before the `except`):

```python
            # Attempt to read standard BLE Battery Service (UUID 0x180F / char 0x2A19).
            # Silently skip if the device does not expose the service.
            battery_char = client.services.get_characteristic(
                "00002a19-0000-1000-8000-00805f9b34fb"
            )
            if battery_char is not None:
                try:
                    raw = await client.read_gatt_char(battery_char)
                    self._battery = int(raw[0])
                except BleakError:
                    pass

            self.async_set_updated_data(copy.copy(self.data))
```

- [ ] **Step 4: Push update in `_async_on_disconnect`**

Replace:

```python
    @callback
    def _async_on_disconnect(self, client: BleakClient) -> None:
        """Handle unexpected disconnection."""
        _LOGGER.warning("Disconnected from AiBBQ %s — will reconnect on next advertisement", self._address)
        self._client = None
        self._write_char = None
```

With:

```python
    @callback
    def _async_on_disconnect(self, client: BleakClient) -> None:
        """Handle unexpected disconnection."""
        _LOGGER.warning("Disconnected from AiBBQ %s — will reconnect on next advertisement", self._address)
        self._client = None
        self._write_char = None
        self.async_set_updated_data(copy.copy(self.data))
```

- [ ] **Step 5: Commit**

```bash
git add custom_components/aibbq/coordinator.py
git commit -m "feat(aibbq): update coordinator handlers — capture RSSI, battery read on connect, push updates on connect/disconnect"
```

---

### Task 4: Add "Connected" binary sensor

**Files:**
- Modify: `custom_components/aibbq/binary_sensor.py`

- [ ] **Step 1: Add `BinarySensorDeviceClass` to the import and add `BINARY_SENSOR_CONNECTED` to the const import**

Replace the import lines at the top:

```python
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
```

With:

```python
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
```

Replace:

```python
from .const import BINARY_SENSOR_ALARM_LOW, BINARY_SENSOR_ALARM_HIGH, DOMAIN
```

With:

```python
from .const import BINARY_SENSOR_ALARM_LOW, BINARY_SENSOR_ALARM_HIGH, BINARY_SENSOR_CONNECTED, DOMAIN
```

- [ ] **Step 2: Add Connected entry to `BINARY_SENSORS` tuple**

The tuple currently reads:

```python
BINARY_SENSORS: tuple[AiBBQBinarySensorDescription, ...] = (
    AiBBQBinarySensorDescription(
        key=BINARY_SENSOR_ALARM_LOW,
        translation_key=BINARY_SENSOR_ALARM_LOW,
        name="Low Temperature Alarm",
        is_on_fn=lambda c: c.alarm_low_active,
    ),
    AiBBQBinarySensorDescription(
        key=BINARY_SENSOR_ALARM_HIGH,
        translation_key=BINARY_SENSOR_ALARM_HIGH,
        name="High Temperature Alarm",
        is_on_fn=lambda c: c.alarm_high_active,
    ),
)
```

Replace with:

```python
BINARY_SENSORS: tuple[AiBBQBinarySensorDescription, ...] = (
    AiBBQBinarySensorDescription(
        key=BINARY_SENSOR_ALARM_LOW,
        translation_key=BINARY_SENSOR_ALARM_LOW,
        name="Low Temperature Alarm",
        is_on_fn=lambda c: c.alarm_low_active,
    ),
    AiBBQBinarySensorDescription(
        key=BINARY_SENSOR_ALARM_HIGH,
        translation_key=BINARY_SENSOR_ALARM_HIGH,
        name="High Temperature Alarm",
        is_on_fn=lambda c: c.alarm_high_active,
    ),
    AiBBQBinarySensorDescription(
        key=BINARY_SENSOR_CONNECTED,
        translation_key=BINARY_SENSOR_CONNECTED,
        name="Connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        is_on_fn=lambda c: c.is_connected,
    ),
)
```

- [ ] **Step 3: Commit**

```bash
git add custom_components/aibbq/binary_sensor.py
git commit -m "feat(aibbq): add Connected binary sensor"
```

---

### Task 5: Add "Connect" switch

**Files:**
- Modify: `custom_components/aibbq/switch.py`

- [ ] **Step 1: Add `SWITCH_CONNECT` to the const import**

Replace:

```python
from .const import DOMAIN, SWITCH_ALARM_LOW_ENABLED, SWITCH_ALARM_HIGH_ENABLED
```

With:

```python
from .const import DOMAIN, SWITCH_ALARM_LOW_ENABLED, SWITCH_ALARM_HIGH_ENABLED, SWITCH_CONNECT
```

- [ ] **Step 2: Add the `AiBBQConnectSwitch` class**

After the closing `}` of the existing `AiBBQSwitch` class (at the end of the file), add:

```python


class AiBBQConnectSwitch(CoordinatorEntity[AiBBQCoordinator], SwitchEntity, RestoreEntity):
    """Controls whether the device should auto-connect when in BLE range."""

    _attr_has_entity_name = True
    _attr_translation_key = SWITCH_CONNECT

    def __init__(
        self,
        coordinator: AiBBQCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id}_{SWITCH_CONNECT}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state != STATE_ON:
            await self.coordinator.async_set_connect_enabled(False)

    @property
    def is_on(self) -> bool:
        return self.coordinator.connect_enabled

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_connect_enabled(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_connect_enabled(False)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
```

- [ ] **Step 3: Register `AiBBQConnectSwitch` in `async_setup_entry`**

Replace:

```python
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AiBBQCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        AiBBQSwitch(coordinator, entry, description) for description in SWITCHES
    )
```

With:

```python
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AiBBQCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list = [
        AiBBQSwitch(coordinator, entry, description) for description in SWITCHES
    ]
    entities.append(AiBBQConnectSwitch(coordinator, entry))
    async_add_entities(entities)
```

- [ ] **Step 4: Commit**

```bash
git add custom_components/aibbq/switch.py
git commit -m "feat(aibbq): add Connect switch with async BLE connect/disconnect and state restore"
```

---

### Task 6: Update sensor.py — signature change, RSSI, and Battery

**Files:**
- Modify: `custom_components/aibbq/sensor.py`

- [ ] **Step 1: Update imports**

Replace:

```python
from homeassistant.const import UnitOfTemperature
```

With:

```python
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, UnitOfTemperature
```

Replace:

```python
from .const import DOMAIN, SENSOR_TEMP_CURRENT
```

With:

```python
from .const import DOMAIN, SENSOR_BATTERY, SENSOR_RSSI, SENSOR_TEMP_CURRENT
```

Remove the now-unused import of `AiBBQState`:

```python
from .parser import AiBBQState
```

(Delete that line entirely — `value_fn` will now take `AiBBQCoordinator`, so `AiBBQState` is no longer referenced in this file.)

- [ ] **Step 2: Change `value_fn` type in the descriptor dataclass**

Replace:

```python
@dataclass(frozen=True, kw_only=True)
class AiBBQSensorDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with a value accessor."""
    value_fn: Callable[[AiBBQState], float | None]
```

With:

```python
@dataclass(frozen=True, kw_only=True)
class AiBBQSensorDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with a value accessor."""
    value_fn: Callable[[AiBBQCoordinator], float | None]
```

- [ ] **Step 3: Update existing temperature sensor lambda and add RSSI + Battery sensors**

Replace the entire `SENSORS` tuple:

```python
SENSORS: tuple[AiBBQSensorDescription, ...] = (
    AiBBQSensorDescription(
        key=SENSOR_TEMP_CURRENT,
        name="Probe Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        value_fn=lambda s: s.best_temp,
    ),
)
```

With:

```python
SENSORS: tuple[AiBBQSensorDescription, ...] = (
    AiBBQSensorDescription(
        key=SENSOR_TEMP_CURRENT,
        name="Probe Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        value_fn=lambda c: c.data.best_temp,
    ),
    AiBBQSensorDescription(
        key=SENSOR_RSSI,
        translation_key=SENSOR_RSSI,
        name="Signal Strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.rssi,
    ),
    AiBBQSensorDescription(
        key=SENSOR_BATTERY,
        translation_key=SENSOR_BATTERY,
        name="Battery",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda c: c.battery,
    ),
)
```

- [ ] **Step 4: Update `native_value` to pass coordinator instead of `coordinator.data`**

Replace:

```python
    @property
    def native_value(self) -> float | None:
        """Return the current sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
```

With:

```python
    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator)
```

- [ ] **Step 5: Commit**

```bash
git add custom_components/aibbq/sensor.py
git commit -m "feat(aibbq): add RSSI and Battery sensors; update value_fn signature to accept coordinator"
```

---

### Task 7: Add translations

**Files:**
- Modify: `custom_components/aibbq/strings.json`
- Modify: `custom_components/aibbq/translations/en.json`

- [ ] **Step 1: Update `strings.json`**

Replace the entire file content with:

```json
{
  "config": {
    "step": {
      "bluetooth_confirm": {
        "description": "Do you want to set up {name}?",
        "title": "AiBBQ Life Thermometer discovered"
      },
      "user": {
        "data": {
          "address": "Device"
        },
        "description": "Choose your AiBBQ thermometer from the list of discovered devices.",
        "title": "Set up AiBBQ Life Thermometer"
      }
    },
    "error": {
      "cannot_connect": "Failed to connect to the device. Make sure it is powered on and in range.",
      "no_devices_found": "No AiBBQ devices were found. Make sure the device is powered on."
    },
    "abort": {
      "already_configured": "Device is already configured.",
      "no_devices_found": "No AiBBQ devices were found nearby."
    }
  },
  "entity": {
    "binary_sensor": {
      "connected": {
        "name": "Connected"
      }
    },
    "switch": {
      "connect": {
        "name": "Connect"
      }
    },
    "sensor": {
      "rssi": {
        "name": "Signal Strength"
      },
      "battery": {
        "name": "Battery"
      }
    }
  }
}
```

- [ ] **Step 2: Update `translations/en.json`**

Replace the entire file content with:

```json
{
  "config": {
    "step": {
      "bluetooth_confirm": {
        "description": "Do you want to set up **{name}**?",
        "title": "AiBBQ Life Thermometer discovered"
      },
      "user": {
        "data": {
          "address": "Device"
        },
        "description": "Choose your AiBBQ thermometer from the list of discovered Bluetooth devices.",
        "title": "Set up AiBBQ Life Thermometer"
      }
    },
    "error": {
      "cannot_connect": "Failed to connect to the device. Make sure it is powered on and within Bluetooth range.",
      "no_devices_found": "No AiBBQ devices were found. Power on the thermometer and try again."
    },
    "abort": {
      "already_configured": "This device is already configured.",
      "no_devices_found": "No AiBBQ devices were found nearby. Make sure the thermometer is powered on."
    }
  },
  "entity": {
    "binary_sensor": {
      "connected": {
        "name": "Connected"
      }
    },
    "switch": {
      "connect": {
        "name": "Connect"
      }
    },
    "sensor": {
      "rssi": {
        "name": "Signal Strength"
      },
      "battery": {
        "name": "Battery"
      }
    }
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add custom_components/aibbq/strings.json custom_components/aibbq/translations/en.json
git commit -m "feat(aibbq): add translations for connected sensor, connect switch, RSSI, and battery"
```

---

## Manual Verification Checklist

After all tasks are complete, reload the integration in Home Assistant and verify:

- [ ] Six switch entities appear: Low Alarm Enabled, High Alarm Enabled, **Connect**
- [ ] Three binary sensor entities appear: Low Temperature Alarm, High Temperature Alarm, **Connected**
- [ ] Temperature sensor still works
- [ ] **Signal Strength** sensor exists but is disabled by default in the entity registry
- [ ] **Battery** sensor appears (value may be unavailable if the device lacks Battery Service)
- [ ] Turning **Connect** OFF disconnects the device; **Connected** flips to OFF
- [ ] Turning **Connect** ON reconnects; **Connected** flips back to ON within a few seconds
- [ ] RSSI sensor updates every time the device advertises (enable it first in the entity registry)
- [ ] After an HA restart with Connect OFF, the device does not auto-connect
