"""
AiBBQ Life BLE protocol parser.

Reverse-engineered packet format
─────────────────────────────────
All packets are framed:  0xFF  <type>  <payload…>  0xFD

Observed message types
──────────────────────
0x01  High-res status   payload[0] / 10  →  temperature in °C  (0.1 °C resolution)
                        Sent every ~5 s as a keep-alive / precision reading.

0x10  Current temp      payload[-1]      →  temperature in °C  (1 °C resolution)
                        Sent every ~1 s; this is the main probe temperature.

0x11  Target / alarm    payload[-1]      →  target °C  (default 100 °C = unset)
                        Sent every ~10 s.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

_LOGGER = logging.getLogger(__name__)

FRAME_START = 0xFF
FRAME_END   = 0xFD
MSG_STATUS  = 0x01
MSG_CURRENT = 0x10
MSG_TARGET  = 0x11


@dataclass
class AiBBQState:
    """Represents the last-known state of one AiBBQ probe."""

    # High-res reading (tenths, from 0x01 packets) — preferred for display
    current_temp_hires: float | None = None

    # Low-res reading (whole °C, from 0x10 packets) — arrives every second
    current_temp: float | None = None

    # Alarm setpoint (from 0x11 packets)
    target_temp: float | None = None

    @property
    def best_temp(self) -> float | None:
        """Return the highest-resolution available temperature."""
        return self.current_temp_hires if self.current_temp_hires is not None else self.current_temp


def split_frames(data: bytes) -> list[bytes]:
    """
    Split a raw BLE notification into individual 0xFF…0xFD frames.

    The device occasionally batches multiple frames into a single notification.
    """
    frames: list[bytes] = []
    i = 0
    while i < len(data):
        if data[i] == FRAME_START:
            end = data.find(FRAME_END, i + 1)
            if end != -1:
                frames.append(data[i : end + 1])
                i = end + 1
                continue
        i += 1
    return frames or [data]


def parse_frame(frame: bytes) -> dict | None:
    """
    Parse a single AiBBQ frame.

    Returns a dict with at minimum a ``"type"`` key, or ``None`` if the frame
    is malformed or unrecognised.
    """
    if len(frame) < 4:
        _LOGGER.debug("Frame too short: %s", frame.hex())
        return None

    if frame[0] != FRAME_START or frame[-1] != FRAME_END:
        _LOGGER.debug("Bad framing: %s", frame.hex())
        return None

    msg_type = frame[1]
    payload  = frame[2:-1]  # everything between type byte and end marker

    if msg_type == MSG_STATUS:
        # byte[0] of payload = temperature × 10
        if len(payload) < 1:
            return None
        temp = payload[0] / 10.0
        return {"type": "status", "temp_c": temp}

    if msg_type == MSG_CURRENT:
        # last byte of payload = temperature in whole °C
        if len(payload) < 1:
            return None
        temp = float(payload[-1])
        return {"type": "current", "temp_c": temp}

    if msg_type == MSG_TARGET:
        # last byte of payload = target/alarm temperature in whole °C
        if len(payload) < 1:
            return None
        target = float(payload[-1])
        return {"type": "target", "target_c": target}

    _LOGGER.debug("Unknown message type 0x%02x: %s", msg_type, frame.hex())
    return {"type": "unknown", "msg_type": msg_type, "raw": frame.hex()}


def process_notification(data: bytes, state: AiBBQState) -> bool:
    """
    Apply all frames in a raw BLE notification to *state* in-place.

    Returns ``True`` if any field was updated.
    """
    updated = False
    for frame in split_frames(data):
        result = parse_frame(frame)
        if result is None:
            continue

        t = result["type"]
        if t == "status":
            state.current_temp_hires = result["temp_c"]
            updated = True
        elif t == "current":
            state.current_temp = result["temp_c"]
            updated = True
        elif t == "target":
            state.target_temp = result["target_c"]
            updated = True

    return updated
