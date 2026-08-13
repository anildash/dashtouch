"""Port discovery and line framing.

DTR must be asserted before opening or the ESP32-S3's native USB CDC
stays completely silent — the board looks dead. Hard-won; don't remove.
"""
from __future__ import annotations

import serial
import serial.tools.list_ports

BAUD = 115200


class AmbiguousPortError(Exception):
    pass


def find_port() -> str | None:
    cands = [p.device for p in serial.tools.list_ports.comports()
             if p.device.startswith("/dev/cu.usbmodem")]
    if not cands:
        return None
    if len(cands) > 1:
        raise AmbiguousPortError(f"several boards found: {cands}")
    return cands[0]


def open_port(port: str) -> serial.Serial:
    s = serial.Serial()
    s.port = port
    s.baudrate = BAUD
    s.timeout = 0.2
    s.dtr = True
    s.rts = False
    s.open()
    return s


def read_line(ser) -> str | None:
    raw = ser.readline()
    if not raw:
        return None
    return raw.decode("utf-8", "replace").strip()
