"""
Step 1: Scan for BLE devices and enumerate the GATT profile of the AiBBQ thermometer.
Run with: .venv/bin/python enumerate.py
"""

import asyncio
from bleak import BleakScanner, BleakClient


async def scan():
    print("Scanning for BLE devices (10s) — make sure your probe is on and nearby...\n")
    # bleak 3.x: return_adv=True gives (BLEDevice, AdvertisementData) pairs keyed by address
    results = await BleakScanner.discover(timeout=10, return_adv=True)

    if not results:
        print("No devices found. Check Bluetooth is enabled and the probe is powered.")
        return None

    print(f"{'Address':<20} {'Name':<30} {'RSSI'}")
    print("-" * 60)
    candidates = []
    for address, (device, adv) in sorted(results.items(), key=lambda x: x[1][1].rssi or -999, reverse=True):
        name = device.name or adv.local_name or "(unknown)"
        print(f"{address:<20} {name:<30} {adv.rssi}")
        if any(k in name.lower() for k in ["bbq", "ibbq", "inkbird", "xbbq", "tpro"]):
            candidates.append(device)

    return candidates


async def enumerate_gatt(address: str):
    print(f"\nConnecting to {address} ...")
    async with BleakClient(address, timeout=15) as client:
        print(f"Connected: {client.is_connected}\n")
        print("=" * 70)
        print("GATT PROFILE")
        print("=" * 70)

        for service in client.services:
            print(f"\nSERVICE  {service.uuid}")
            print(f"         {service.description}")
            for char in service.characteristics:
                props = ", ".join(char.properties)
                print(f"  CHAR   {char.uuid}  [{props}]")
                print(f"         {char.description}")

                # Try to read readable characteristics
                if "read" in char.properties:
                    try:
                        val = await client.read_gatt_char(char.uuid)
                        print(f"         VALUE = {val.hex()} ({list(val)})")
                    except Exception as e:
                        print(f"         READ ERR: {e}")

                for desc in char.descriptors:
                    try:
                        val = await client.read_gatt_descriptor(desc.handle)
                        print(f"    DESC {desc.uuid}  = {val.hex()}")
                    except Exception:
                        print(f"    DESC {desc.uuid}")

        print("\n" + "=" * 70)


async def main():
    import sys
    # Accept an explicit address as CLI arg: python enumerate.py <address>
    if len(sys.argv) > 1:
        await enumerate_gatt(sys.argv[1])
        return

    candidates = await scan()

    if not candidates:
        print("\nNo AiBBQ/iBBQ keywords matched — re-run with address as argument:")
        print("  python enumerate.py <ADDRESS>")
        return

    if len(candidates) == 1:
        addr = candidates[0].address
        print(f"\nAuto-selected: {candidates[0].name} @ {addr}")
    else:
        print(f"\nAuto-selected first match: {candidates[0].name} @ {candidates[0].address}")
        addr = candidates[0].address

    await enumerate_gatt(addr)


asyncio.run(main())
