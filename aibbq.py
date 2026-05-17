"""
AiBBQ Life BLE client — reverse engineered protocol.

Device:  AIBBQLife
Service: 43f4b114-ca67-48e8-a46f-9a8ffeb7146a
         2445314a-a1d4-4874-b4d1-fdfb6f501485
Write:   bf83f3f1-399a-414d-9035-ce64ceb3ff67  (handle 7 / 13)
Notify:  bf83f3f2-399a-414d-9035-ce64ceb3ff67  (handle 9 / 15)

Packet framing:  ff  <type>  <payload...>  fd

Observed types:
  0x01  High-res status    payload[0]/10 = temperature in °C (e.g. 0xF0 = 24.0°C)
  0x10  Current temp       payload[-1]   = temperature in °C (whole degrees)
  0x11  Target/alarm temp  payload[-1]   = target °C (default 100°C)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from bleak import BleakScanner, BleakClient

# -- Constants ----------------------------------------------------------------

DEVICE_NAME   = "AIBBQLife"
DEVICE_ADDR   = "234E2854-5DC2-BB68-FF26-6EC80CBA27E7"  # your device

WRITE_HANDLE  = 7     # bf83f3f1 in service 1
NOTIFY_HANDLE = 9     # bf83f3f2 in service 1

# Auth / handshake command (triggers data stream)
AUTH_CMD = bytes([0x21, 0x07, 0x06, 0x05, 0x04, 0x03, 0x02, 0x01,
                  0xb8, 0x22, 0x00, 0x00, 0x00, 0x00])

MSG_STATUS      = 0x01   # high-res temp, sent every ~5s
MSG_CURRENT     = 0x10   # current temp,  sent every ~1s
MSG_TARGET      = 0x11   # alarm/target temp

# -- State --------------------------------------------------------------------

@dataclass
class ProbeState:
    current_c: float | None = None   # from 0x10 packets (whole °C)
    current_c_hires: float | None = None  # from 0x01 packets (tenths °C)
    target_c: float | None = None    # from 0x11 packets
    last_updated: datetime = field(default_factory=datetime.now)

    def display(self) -> str:
        temp = self.current_c_hires or self.current_c
        if temp is None:
            return "-- °C"
        return f"{temp:.1f} °C"


# -- Protocol decoder ---------------------------------------------------------

def decode_packet(data: bytes) -> dict | None:
    """Parse a single AiBBQ notification packet."""
    if len(data) < 4:
        return None
    if data[0] != 0xFF or data[-1] != 0xFD:
        return None

    msg_type = data[1]
    payload  = data[2:-1]

    if msg_type == MSG_STATUS and len(payload) >= 1:
        temp_c = payload[0] / 10.0
        return {"type": "status", "temp_c": temp_c, "raw": data.hex()}

    if msg_type == MSG_CURRENT and len(payload) >= 1:
        temp_c = payload[-1]
        return {"type": "current", "temp_c": float(temp_c), "raw": data.hex()}

    if msg_type == MSG_TARGET and len(payload) >= 1:
        target_c = payload[-1]
        return {"type": "target", "target_c": float(target_c), "raw": data.hex()}

    return {"type": "unknown", "msg_type": msg_type, "raw": data.hex()}


def split_frames(data: bytes) -> list[bytes]:
    """Split concatenated frames (device sometimes batches them)."""
    frames = []
    i = 0
    while i < len(data):
        if data[i] == 0xFF:
            end = data.find(0xFD, i + 1)
            if end != -1:
                frames.append(data[i:end + 1])
                i = end + 1
            else:
                break
        else:
            i += 1
    return frames if frames else [data]


# -- BLE client ---------------------------------------------------------------

class AiBBQClient:
    def __init__(self, address: str = DEVICE_ADDR):
        self.address = address
        self.state = ProbeState()
        self._client: BleakClient | None = None

    def _on_notify(self, sender, data: bytearray):
        for frame in split_frames(bytes(data)):
            result = decode_packet(frame)
            if result is None:
                return

            t = result["type"]
            if t == "status":
                self.state.current_c_hires = result["temp_c"]
                self.state.last_updated = datetime.now()
            elif t == "current":
                self.state.current_c = result["temp_c"]
                self.state.last_updated = datetime.now()
            elif t == "target":
                self.state.target_c = result["target_c"]

            self._print_state(result)

    def _print_state(self, result: dict):
        ts = datetime.now().strftime("%H:%M:%S")
        t = result["type"]
        if t == "current":
            print(f"[{ts}] TEMP     {self.state.current_c:5.1f} °C  (probe, 1°C res)")
        elif t == "status":
            print(f"[{ts}] TEMP     {self.state.current_c_hires:5.1f} °C  (hi-res 0.1°C)")
        elif t == "target":
            print(f"[{ts}] TARGET   {self.state.target_c:5.1f} °C  (alarm setpoint)")
        else:
            print(f"[{ts}] UNKNOWN  {result['raw']}")

    async def connect_and_stream(self, duration: float = 60):
        print(f"Connecting to {self.address} ...")
        async with BleakClient(self.address, timeout=15) as client:
            self._client = client
            print("Connected ✓")

            await client.start_notify(NOTIFY_HANDLE, self._on_notify)
            await client.write_gatt_char(WRITE_HANDLE, AUTH_CMD, response=False)

            print(f"Streaming for {duration}s  (Ctrl-C to stop)\n")
            try:
                await asyncio.sleep(duration)
            except asyncio.CancelledError:
                pass
            finally:
                await client.stop_notify(NOTIFY_HANDLE)

        print(f"\nFinal state: {self.state.display()}")
        if self.state.target_c:
            print(f"Target:      {self.state.target_c:.0f} °C")


# -- CLI entry point ----------------------------------------------------------

async def find_device() -> str:
    print(f"Scanning for '{DEVICE_NAME}' ...")
    results = await BleakScanner.discover(timeout=10, return_adv=True)
    for addr, (dev, adv) in results.items():
        name = dev.name or adv.local_name or ""
        if DEVICE_NAME.lower() in name.lower():
            print(f"Found: {name} @ {addr}  RSSI={adv.rssi}")
            return addr
    raise RuntimeError(f"Device '{DEVICE_NAME}' not found. Is it powered on?")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="AiBBQ BLE thermometer client")
    parser.add_argument("--scan",     action="store_true", help="Scan and find device address")
    parser.add_argument("--address",  default=DEVICE_ADDR, help="BLE device address")
    parser.add_argument("--duration", type=float, default=60, help="Stream duration in seconds")
    args = parser.parse_args()

    if args.scan:
        addr = await find_device()
    else:
        addr = args.address

    client = AiBBQClient(address=addr)
    await client.connect_and_stream(duration=args.duration)


if __name__ == "__main__":
    asyncio.run(main())
