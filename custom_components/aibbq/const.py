"""Constants for the AiBBQ Life integration."""

DOMAIN = "aibbq"
DEVICE_NAME = "AIBBQLife"

# ── BLE GATT ────────────────────────────────────────────────────────────────
# Service UUIDs (device exposes two identical-layout services)
SERVICE_UUID_1 = "43f4b114-ca67-48e8-a46f-9a8ffeb7146a"
SERVICE_UUID_2 = "2445314a-a1d4-4874-b4d1-fdfb6f501485"

# Characteristic UUIDs (same UUID appears in both services, differentiated by handle)
CHAR_WRITE_UUID  = "bf83f3f1-399a-414d-9035-ce64ceb3ff67"
CHAR_NOTIFY_UUID = "bf83f3f2-399a-414d-9035-ce64ceb3ff67"

# GATT handles (service 1)
WRITE_HANDLE  = 7
NOTIFY_HANDLE = 9

# Handshake command — must be sent after connecting to start the data stream
AUTH_CMD = bytes([
    0x21, 0x07, 0x06, 0x05, 0x04, 0x03, 0x02, 0x01,
    0xB8, 0x22, 0x00, 0x00, 0x00, 0x00,
])

# ── PROTOCOL ─────────────────────────────────────────────────────────────────
FRAME_START = 0xFF
FRAME_END   = 0xFD

# Message types found in byte[1] of each frame
MSG_STATUS  = 0x01   # High-resolution temperature (tenths of °C), sent every ~5 s
MSG_CURRENT = 0x10   # Current probe temperature (whole °C), sent every ~1 s
MSG_TARGET  = 0x11   # Alarm / target temperature (whole °C), sent every ~10 s

# Sentinel for "probe not connected" (not yet confirmed for this device)
PROBE_DISCONNECTED = 0xFF

# ── HA ───────────────────────────────────────────────────────────────────────
CONF_ADDRESS = "address"

SENSOR_TEMP_CURRENT    = "temperature_current"
SENSOR_TEMP_TARGET     = "temperature_target"
NUMBER_TEMP_MIN        = "min_temperature"
NUMBER_TEMP_MAX        = "max_temperature"
BINARY_SENSOR_ALARM_LOW  = "alarm_low"
BINARY_SENSOR_ALARM_HIGH = "alarm_high"
SWITCH_ALARM_LOW_ENABLED  = "alarm_low_enabled"
SWITCH_ALARM_HIGH_ENABLED = "alarm_high_enabled"
BINARY_SENSOR_CONNECTED   = "connected"
SWITCH_CONNECT            = "connect"
SENSOR_RSSI               = "rssi"
SENSOR_BATTERY            = "battery"
