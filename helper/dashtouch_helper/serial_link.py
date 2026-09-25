"""Port discovery and line framing.

DTR must be asserted before opening or the ESP32-S3's native USB CDC
stays completely silent — the board looks dead. Hard-won; don't remove.
"""
from __future__ import annotations

from dataclasses import dataclass

import serial
import serial.tools.list_ports

BAUD = 115200


class AmbiguousPortError(Exception):
    pass


@dataclass(frozen=True)
class UsbPort:
    device: str
    label: str
    # Stable across a re-enumeration onto a new /dev node, where the board
    # reports a serial number. Used to find the same board again after a
    # reset renames its port.
    identity: tuple


def usb_ports() -> list[UsbPort]:
    """USB serial ports a dashtouch could be on, with a name for each.

    Only /dev/cu.usbmodem*, the same ports find_port() considers: the
    firmware is built for a native-USB ESP32-S3, and a board that turns up
    anywhere else is one the helper would never find after flashing it.
    """
    out = []
    for p in serial.tools.list_ports.comports():
        if p.vid is None or not p.device.startswith("/dev/cu.usbmodem"):
            continue
        label = " ".join(x for x in (p.manufacturer, p.product) if x)
        identity = (p.vid, p.pid, p.serial_number or p.location or p.device)
        out.append(UsbPort(p.device, label or p.description or "", identity))
    return out


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
