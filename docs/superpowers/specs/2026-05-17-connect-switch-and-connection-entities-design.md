# Design: Connect Switch, Connected Binary Sensor, RSSI & Battery Sensors

**Date:** 2026-05-17
**Status:** Approved

## Overview

Add four new entities to the AiBBQ Home Assistant integration:

1. **Switch "Connect"** — user controls whether the device should auto-connect. ON by default. When turned OFF, disconnects the device and suppresses auto-reconnect until turned ON again.
2. **Binary Sensor "Connected"** — reflects the real-time BLE connection state.
3. **Sensor "Signal Strength" (RSSI)** — BLE signal strength in dBm. Disabled by default in the entity registry.
4. **Sensor "Battery"** — battery level % read from the standard BLE Battery Service (UUID `0x180F` / characteristic `0x2A19`) immediately after connecting. Shows unavailable if the device does not expose that service.

## Approach

Approach A: extend the coordinator with new properties and methods; fit new entities into the existing descriptor/`CoordinatorEntity` patterns wherever possible. The Connect switch gets its own dedicated class because it requires async BLE operations and defaults ON (unlike the alarm switches).

## Coordinator Changes (`coordinator.py`)

### New state

```python
_connect_enabled: bool = True   # user intent
_rssi: float | None = None      # updated on every advertisement
_battery: int | None = None     # read once after connecting
```

### New public API

| Property / method | Returns / does |
|---|---|
| `connect_enabled` | `bool` — current value of `_connect_enabled` |
| `is_connected` | `bool` — exposes existing `_is_connected` |
| `rssi` | `float \| None` |
| `battery` | `int \| None` |
| `async_set_connect_enabled(enabled: bool)` | If `False`: set flag, cancel in-flight connect task, disconnect, push update. If `True`: set flag, schedule connect, push update. |

### Modified behaviour

- **`_async_on_advertisement`**: capture `service_info.rssi` → `_rssi`; check `_connect_enabled` before calling `_schedule_connect`; always call `async_set_updated_data` so the RSSI sensor refreshes even while already connected.
- **`_schedule_connect`**: early-return if `not _connect_enabled`.
- **`_async_connect`**: after a successful connection, attempt to read characteristic `0x2A19`. Store as `_battery` (int 0–100); silently ignore `BleakError` if the service is absent. Call `async_set_updated_data` so the Connected binary sensor flips to ON.
- **`_async_on_disconnect`**: call `async_set_updated_data` so the Connected binary sensor flips to OFF.

## New Entities

### Binary Sensor — Connected (`binary_sensor.py`)

Added to the existing `BINARY_SENSORS` tuple using `AiBBQBinarySensorDescription`. No new class required.

```python
AiBBQBinarySensorDescription(
    key=BINARY_SENSOR_CONNECTED,
    translation_key=BINARY_SENSOR_CONNECTED,
    name="Connected",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    is_on_fn=lambda c: c.is_connected,
)
```

### Switch — Connect (`switch.py`)

New class `AiBBQConnectSwitch` (separate from the existing `AiBBQSwitch` alarm descriptor pattern).

- `is_on` → `coordinator.connect_enabled`
- `async_turn_on` → `await coordinator.async_set_connect_enabled(True)`
- `async_turn_off` → `await coordinator.async_set_connect_enabled(False)`
- `async_added_to_hass`: restores last state from `RestoreEntity`; if last state was OFF, calls `async_set_connect_enabled(False)` so HA restarts honour the user's intent and do not auto-reconnect.

Added to `async_setup_entry` alongside existing alarm switches.

### Sensor — Signal Strength / RSSI (`sensor.py`)

```python
AiBBQSensorDescription(
    key=SENSOR_RSSI,
    translation_key=SENSOR_RSSI,
    name="Signal Strength",
    device_class=SensorDeviceClass.SIGNAL_STRENGTH,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    entity_registry_enabled_default=False,
    value_fn=lambda c: c.rssi,
)
```

### Sensor — Battery (`sensor.py`)

```python
AiBBQSensorDescription(
    key=SENSOR_BATTERY,
    translation_key=SENSOR_BATTERY,
    name="Battery",
    device_class=SensorDeviceClass.BATTERY,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=PERCENTAGE,
    value_fn=lambda c: c.battery,
)
```

`None` native value maps automatically to "unavailable" in HA — no special handling needed if the BLE Battery Service is absent.

### `value_fn` signature change in `sensor.py`

`AiBBQSensorDescription.value_fn` changes from `Callable[[AiBBQState], float | None]` to `Callable[[AiBBQCoordinator], float | None]` so RSSI and Battery can read coordinator properties directly. The existing temperature sensor lambda updates from:

```python
value_fn=lambda s: s.best_temp
```
to:
```python
value_fn=lambda c: c.data.best_temp
```

## Constants (`const.py`)

Four new keys:

```python
BINARY_SENSOR_CONNECTED   = "connected"
SWITCH_CONNECT            = "connect"
SENSOR_RSSI               = "rssi"
SENSOR_BATTERY            = "battery"
```

## Translations (`strings.json`, `translations/en.json`)

Add `entity.binary_sensor.connected`, `entity.switch.connect`, `entity.sensor.rssi`, `entity.sensor.battery` sections with appropriate display names.

## Files Changed

| File | Change |
|---|---|
| `const.py` | 4 new constant keys |
| `coordinator.py` | New fields, properties, `async_set_connect_enabled`, modified connect/disconnect/advertisement handlers |
| `binary_sensor.py` | Add Connected entry to `BINARY_SENSORS` tuple; import `BinarySensorDeviceClass` |
| `switch.py` | Add `AiBBQConnectSwitch` class; register it in `async_setup_entry` |
| `sensor.py` | Change `value_fn` signature; add RSSI and Battery entries to `SENSORS` tuple |
| `strings.json` | Translation keys for 4 new entities |
| `translations/en.json` | English labels for 4 new entities |

## Edge Cases & Error Handling

- **HA restart with Connect switch OFF**: restored via `RestoreEntity`; `async_set_connect_enabled(False)` called before any BT advertisement arrives.
- **BLE Battery Service absent**: `BleakError` caught silently; `_battery` stays `None`; sensor shows unavailable.
- **Advertisement while disconnected and Connect OFF**: `_schedule_connect` early-returns; no reconnect attempt.
- **Turn Connect ON while already connected**: `async_set_connect_enabled(True)` sets flag and calls `_schedule_connect`, which is a no-op because `_is_connected` is already true.
- **Turn Connect OFF while connection in progress**: in-flight `_connect_task` is cancelled before disconnect.
