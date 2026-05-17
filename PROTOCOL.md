# AiBBQ Life — BLE Protocol Reference

Reverse-engineered by live BLE capture on 2026-05-17.
Device: **AIBBQLife** (single-probe thermometer)

---

## Device discovery

| Field | Value |
|---|---|
| Advertised name | `AIBBQLife` |
| BLE address (macOS UUID) | `234E2854-5DC2-BB68-FF26-6EC80CBA27E7` |
| Connectable | Yes |
| Manufacturer data | None in advertisement |
| Service UUIDs in adv | None (only visible after GATT connect) |

---

## GATT Profile

The device exposes **two services** with identical characteristic layouts.
Service 1 is used for all communication.

### Services

| # | UUID |
|---|---|
| 1 | `43f4b114-ca67-48e8-a46f-9a8ffeb7146a` |
| 2 | `2445314a-a1d4-4874-b4d1-fdfb6f501485` |

### Characteristics (same UUID in both services, differentiated by handle)

| Handle | UUID | Properties | Role |
|---|---|---|---|
| 7 | `bf83f3f1-399a-414d-9035-ce64ceb3ff67` | write-without-response, read | **Write / command** |
| 9 | `bf83f3f2-399a-414d-9035-ce64ceb3ff67` | notify | **Notifications / data** |
| 13 | `bf83f3f1-…` | write-without-response, read | (service 2 duplicate) |
| 15 | `bf83f3f2-…` | notify | (service 2 duplicate) |

---

## Connection sequence

1. Connect to device (GATT)
2. Subscribe to notifications on **handle 9** (or by UUID scoped to service 1)
3. Write auth/handshake command to **handle 7** — this triggers the data stream

### Auth command

```
21 07 06 05 04 03 02 01 B8 22 00 00 00 00
```

Without this command the device sends no notifications.

---

## Packet format

All frames are delimited:

```
FF  <type>  <payload…>  FD
```

- `0xFF` — frame start
- `0xFD` — frame end
- The device occasionally batches multiple frames into a single notification; split on `FF…FD` boundaries.

---

## Message types

### `0x10` — Current probe temperature (1 °C resolution)

Sent every **~1 second**. Most frequent packet.

```
FF  10  FE  [A] [B] [C] [D]  B8  [TEMP]  FD
```

| Byte | Value (observed) | Meaning |
|---|---|---|
| `[0]` | `FF` | frame start |
| `[1]` | `10` | message type |
| `[2]` | `FE` | constant (unknown — possibly status flags) |
| `[3..6]` | `23 12 19 17` | constant 4-byte field (unknown — possibly device ID / serial fragment) |
| `[7]` | `B8` | constant (unknown — possibly raw battery ADC) |
| `[8]` | `17` / `16` | **current temperature in whole °C** |
| `[-1]` | `FD` | frame end |

**Decode:** `temp_c = frame[8]`

---

### `0x11` — Target / alarm temperature

Sent every **~10 seconds**. Same layout as `0x10`, last byte is the setpoint.

```
FF  11  FE  [A] [B] [C] [D]  B8  [TARGET]  FD
```

**Decode:** `target_c = frame[8]`

Default value when no alarm is set: `0x64` = **100 °C**.

---

### `0x01` — High-resolution status

Sent every **~5 seconds**, also fired once immediately after the auth command as a handshake acknowledgement.

```
FF  01  [TEMP_HIRES]  [?] [?] [?] [?] [?] [?]  FD
```

| Byte | Value (observed) | Meaning |
|---|---|---|
| `[2]` | `F0` | **temperature × 10** → `0xF0` = 240 → **24.0 °C** |
| `[3..8]` | `23 1C 19 0A DF 5A` | unknown (possibly session token / device state) |

**Decode:** `temp_c = frame[2] / 10.0`

This packet provides **0.1 °C resolution** vs the whole-degree `0x10` packet.
The HA integration prefers this value when available.

---

## Temperature encoding summary

| Packet | Field | Formula | Resolution |
|---|---|---|---|
| `0x10` | `frame[8]` | raw byte = °C | 1 °C |
| `0x11` | `frame[8]` | raw byte = °C | 1 °C |
| `0x01` | `frame[2]` | `/ 10.0` = °C | 0.1 °C |

---

## Still unknown

| Field | Observed value | Candidates |
|---|---|---|
| `frame[2]` in `0x10`/`0x11` | `0xFE` (constant) | Status flags, probe-connected bitmask |
| `frame[3..6]` in `0x10`/`0x11` | `23 12 19 17` (constant) | Device serial fragment, firmware version |
| `frame[7]` in `0x10`/`0x11` | `0xB8` (constant) | Raw battery ADC, RSSI, unknown |
| `frame[3..8]` in `0x01` | varies | Session token, RTC, device state |

To resolve the unknowns: capture with a **second probe inserted** and observe
which bytes in `frame[3..6]` change — if they're per-probe temperatures the
field is a 4-probe reading array (max 4 × 1 byte = 35 / 18 / 25 / 23 °C observed).

---

## Tools used

- `bleak` 3.0.2 (Python BLE library)
- macOS PacketLogger (BLE sniffer)
- Live capture script: `enumerate.py` / `aibbq.py` in repo root
