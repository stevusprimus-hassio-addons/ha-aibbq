# AiBBQ Life — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Validate](https://github.com/YOUR_GITHUB_USERNAME/hacs-aibbq/actions/workflows/validate.yml/badge.svg)](https://github.com/YOUR_GITHUB_USERNAME/hacs-aibbq/actions/workflows/validate.yml)

A Home Assistant custom integration for the **AiBBQ Life** Bluetooth BBQ thermometer probe.

Communicates directly over BLE — no cloud, no app required.

---

## Features

- **Auto-discovery** — HA detects the probe automatically when it is powered on
- **Probe Temperature** — live reading at 0.1 °C resolution, updated every second
- **Target Temperature** — alarm setpoint configured on the device
- **Local push** — data flows from device → HA over BLE; no polling

---

## Requirements

- Home Assistant 2024.1 or newer
- A Bluetooth adapter visible to HA (built-in, USB dongle, or [Bluetooth proxy](https://esphome.io/projects/?type=bluetooth))
- AiBBQ Life thermometer probe (tested with the single-probe model, advertising as `AIBBQLife`)

---

## Installation via HACS

1. Open HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add `https://github.com/YOUR_GITHUB_USERNAME/hacs-aibbq` — category **Integration**
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
3. The integration will appear in the **Discovered** section — click **Configure** and confirm
4. If it doesn't auto-appear, click **+ Add Integration**, search for *AiBBQ Life Thermometer*, and pick your device from the list

---

## Entities

| Entity | Description | Update rate |
|--------|-------------|-------------|
| `sensor.aibbq_life_thermometer_probe_temperature` | Current probe temperature (°C) | ~1 s |
| `sensor.aibbq_life_thermometer_target_temperature` | Alarm setpoint (°C) | ~10 s |

---

## Protocol

This integration is based on reverse-engineered BLE communication with the AiBBQ Life device.

| Packet type | Content |
|-------------|---------|
| `0x01` | High-resolution temperature — `payload[0] / 10` → °C |
| `0x10` | Current temperature — `payload[-1]` → °C (whole degrees) |
| `0x11` | Target/alarm temperature — `payload[-1]` → °C |

All frames are delimited by `0xFF … 0xFD`.

---

## Contributing

PRs welcome — especially for:
- Multi-probe support
- Battery level sensor
- Alarm binary sensor

---

## License

MIT
