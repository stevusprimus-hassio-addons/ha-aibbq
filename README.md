# AiBBQ Life — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration for the **AiBBQ Life** Bluetooth BBQ thermometer probe.

Communicates directly over BLE — no cloud, no app required.

---

## Features

- **Auto-discovery** — HA detects the probe automatically when it is powered on
- **Live probe temperature** — updated every second, integer °C resolution
- **Min / max temperature thresholds** — set directly in the HA UI
- **Low / high alarm switches** — enable or disable each alarm independently
- **Alarm binary sensors** — `on` when a threshold is crossed; ready for HA Alerts or automations
- **Built-in notifications** — persistent notification fires automatically when an alarm triggers
- **HA event** — `aibbq_alarm` is fired on every threshold crossing for custom automations
- **Local push** — data flows device → HA over BLE; no polling, no cloud

---

## Requirements

- Home Assistant 2024.1 or newer
- A Bluetooth adapter visible to HA (built-in, USB dongle, or [Bluetooth proxy](https://esphome.io/projects/?type=bluetooth))
- AiBBQ Life thermometer probe (tested with single-probe model, advertising as `AIBBQLife`)

---

## Installation via HACS

1. Open HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add your repository URL — category **Integration**
3. Click **Download**
4. Restart Home Assistant

## Manual installation

```bash
cp -r custom_components/aibbq /config/custom_components/aibbq
```

Restart Home Assistant after copying.

---

## Setup

1. Power on your AiBBQ probe
2. Go to **Settings → Devices & Services**
3. The integration appears under **Discovered** — click **Configure** and confirm
4. If it does not auto-appear, click **+ Add Integration**, search for *AiBBQ Life Thermometer*, and pick your device

---

## Entities

| Entity | Type | Description |
|--------|------|-------------|
| `probe_temperature` | `sensor` | Live probe temperature (°C), updated every ~1 s |
| `min_temperature` | `number` | Lower threshold for the low alarm (°C) |
| `max_temperature` | `number` | Upper threshold for the high alarm (°C) |
| `alarm_low_enabled` | `switch` | Enable / disable the low temperature alarm |
| `alarm_high_enabled` | `switch` | Enable / disable the high temperature alarm |
| `alarm_low` | `binary_sensor` | `on` when probe ≤ Min Temperature and low alarm is enabled |
| `alarm_high` | `binary_sensor` | `on` when probe ≥ Max Temperature and high alarm is enabled |

---

## Alarms

### Out-of-the-box behaviour

When an alarm triggers, the integration automatically creates a **persistent notification** in the HA UI (bell icon, top right). No configuration required.

The alarm re-arms automatically once the temperature moves back past the threshold by 1 °C (hysteresis), so it will fire again on the next crossing.

### HA event — `aibbq_alarm`

Every alarm trigger also fires an event on the HA event bus. You can use this in **Developer Tools → Events** or in automations:

| Field | Values | Description |
|-------|--------|-------------|
| `kind` | `"low"` / `"high"` | Which threshold was crossed |
| `current_temp` | `float` | Probe temperature at trigger time (°C) |
| `threshold` | `float` | The configured min or max value (°C) |
| `device_address` | `string` | BLE address of the device |
| `message` | `string` | Human-readable description of the alarm |

**Example automation — send a mobile push notification:**

```yaml
automation:
  - alias: "BBQ alarm → mobile push"
    trigger:
      - platform: event
        event_type: aibbq_alarm
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "{{ trigger.event.data.message }}"
          message: "AiBBQ alert"
          data:
            push:
              sound:
                name: default
                critical: 1        # iOS: bypass Do Not Disturb
                volume: 1.0
```

### HA Alert integration — repeating alerts

For repeating / escalating notifications with acknowledgement, use HA's built-in [Alert integration](https://www.home-assistant.io/integrations/alert/) pointed at the binary sensors:

```yaml
alert:
  bbq_too_cold:
    name: "BBQ probe too cold"
    entity_id: binary_sensor.aibbq_life_thermometer_alarm_low
    state: "on"
    repeat: [1, 5, 10]        # escalate: 1 min → 5 min → 10 min
    notifiers:
      - mobile_app_your_phone
    can_acknowledge: true

  bbq_target_reached:
    name: "BBQ target temperature reached"
    entity_id: binary_sensor.aibbq_life_thermometer_alarm_high
    state: "on"
    repeat: 2
    notifiers:
      - mobile_app_your_phone
    can_acknowledge: true
```

> **Note:** When using HA Alerts, disable the alarm switches in the HA UI if you want to avoid the built-in persistent notification firing alongside the alert.

---

## Protocol

Reverse-engineered from live BLE captures. See [PROTOCOL.md](PROTOCOL.md) for full details.

| Packet | Content |
|--------|---------|
| `0x10` | Current temperature — `frame[8]` → whole °C, sent every ~1 s |
| `0x01` | High-resolution status — `frame[2] / 10` → °C, sent every ~5 s (used as fallback) |
| `0x11` | Device alarm setpoint — `frame[8]` → °C, sent every ~10 s |

Auth handshake `21 07 06 05 04 03 02 01 B8 22 00 00 00 00` must be written to the write characteristic after connecting to start the data stream.

---

## Contributing

PRs welcome. Especially useful:

- Multi-probe support (up to 4 probes suspected from protocol analysis)
- Battery level sensor
- Reverse-engineering the write command for the device-side alarm setpoint

---

## License

MIT
