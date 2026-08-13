#!/usr/bin/env python3
"""Read diagnostic sketch output from the QT Py over USB CDC.

Two things this handles that a naive `screen`/`cat` session does not:

1. **DTR must be asserted.** The ESP32-S3's native USB CDC only transmits when
   the host raises DTR. With DTR low the board looks completely dead -- no
   boot banner, no response to anything. This cost a debugging round before it
   was understood.
2. **Reset loops.** `--watch` reopens the port across disconnects and prints a
   timeline of appear/vanish events. A board that resets every few seconds is
   almost always browning out on a shorted pin, and that pattern is invisible
   if the reader just exits on the first read error.

Usage:
    ./capture.py                       # dump output for 20s
    ./capture.py --secs 60             # dump for longer
    ./capture.py --until "sweep complete"   # stop at a marker
    ./capture.py --watch               # survive resets, report port events
"""
import argparse
import os
import time

import serial
from serial.tools import list_ports


def find_port(explicit=None):
    if explicit:
        return explicit
    candidates = [
        p.device for p in list_ports.comports()
        if p.device.startswith("/dev/cu.usbmodem")
    ]
    if not candidates:
        raise SystemExit("No /dev/cu.usbmodem* device found. Is the board plugged in?")
    if len(candidates) > 1:
        raise SystemExit(f"Multiple boards found: {candidates}. Pass --port.")
    return candidates[0]


def open_port(port):
    s = serial.Serial()
    s.port = port
    s.baudrate = 115200
    s.timeout = 0.2
    s.dtr = True   # required -- see module docstring
    s.rts = False
    s.open()
    return s


def plain(port, secs, until):
    s = open_port(port)
    buf = ""
    end = time.time() + secs
    try:
        while time.time() < end:
            buf += s.read(4096).decode("utf-8", "replace")
            if until and until in buf:
                break
    finally:
        s.close()
    print(buf if buf else "(silence -- if this is unexpected, confirm DTR is asserted)")


def watch(port, secs):
    end = time.time() + secs
    events, chunks = [], []
    present_before, s = None, None

    def stamp():
        return f"t+{secs - (end - time.time()):5.1f}s"

    while time.time() < end:
        present = os.path.exists(port)
        if present != present_before:
            events.append(f"{stamp()}  port {'APPEARED' if present else 'VANISHED'}")
            present_before = present
            if not present and s:
                try:
                    s.close()
                except Exception:
                    pass
                s = None

        if present and s is None:
            try:
                s = open_port(port)
                events.append(f"{stamp()}  opened")
            except Exception:
                time.sleep(0.3)
                continue

        if s:
            try:
                chunk = s.read(4096)
                if chunk:
                    chunks.append(chunk)
            except Exception as exc:
                events.append(f"{stamp()}  read failed: {exc.__class__.__name__}")
                try:
                    s.close()
                except Exception:
                    pass
                s = None
                time.sleep(0.3)
        else:
            time.sleep(0.2)

    print("=== PORT EVENTS ===")
    print("\n".join(events) if events else "(no transitions -- board stayed up)")
    if len(events) > 3:
        print("\nRepeated APPEARED/VANISHED cycles mean the board is resetting.")
        print("Suspect a shorted pin browning out the regulator.")
    print("\n=== DATA ===")
    data = b"".join(chunks)
    print(data.decode("utf-8", "replace") if data else "(no data received)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--secs", type=float, default=20.0)
    ap.add_argument("--until", help="stop once this text appears")
    ap.add_argument("--watch", action="store_true",
                    help="survive resets and report port appear/vanish events")
    args = ap.parse_args()

    port = find_port(args.port)
    print(f"# {port}\n")
    if args.watch:
        watch(port, args.secs)
    else:
        plain(port, args.secs, args.until)


if __name__ == "__main__":
    main()
