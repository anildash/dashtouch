#!/usr/bin/env python3
"""Interactive fingerprint enrollment over the ESP32's USB serial port.

Run this instead of tinytouch_helper.py while enrolling — both scripts open
the same serial port, so stop the helper (or don't start it yet) first.
"""
import argparse
import sys
import time

import serial


def open_serial(port: str) -> serial.Serial:
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = 115200
    ser.timeout = 0.5
    ser.write_timeout = 2
    ser.dtr = True
    ser.rts = False
    ser.open()
    return ser


def read_lines_until(ser: serial.Serial, prefixes: tuple[str, ...], timeout_s: float) -> str | None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        raw = ser.readline()
        if not raw:
            continue
        line = raw.decode("utf-8", "replace").strip()
        if not line:
            continue
        print(f"esp: {line}")
        if line.startswith(prefixes):
            return line
    return None


def enroll(port: str, slot: int) -> int:
    with open_serial(port) as ser:
        time.sleep(2)  # allow the board to finish its boot banner
        ser.reset_input_buffer()
        ser.write(f"ENROLL {slot}\n".encode("ascii"))
        ser.flush()

        line = read_lines_until(ser, ("ENROLL_WAIT_FINGER_1",), 5)
        if not line:
            print("no response to ENROLL command — is the board running this firmware?", file=sys.stderr)
            return 1
        print(">>> place your finger on the sensor now")

        line = read_lines_until(ser, ("ENROLL_REMOVE_FINGER", "ENROLL_FAIL"), 15)
        if not line or line.startswith("ENROLL_FAIL"):
            print("first capture failed", file=sys.stderr)
            return 1
        print(">>> lift your finger off the sensor")

        line = read_lines_until(ser, ("ENROLL_WAIT_FINGER_2",), 6)
        if not line:
            print("did not reach second capture stage", file=sys.stderr)
            return 1
        print(">>> place the same finger on the sensor again")

        line = read_lines_until(ser, ("ENROLL_OK", "ENROLL_FAIL"), 15)
        if not line:
            print("timed out waiting for enroll result", file=sys.stderr)
            return 1
        if line.startswith("ENROLL_FAIL"):
            print("enrollment failed", file=sys.stderr)
            return 1

        print(f"enrolled slot {slot} successfully")
        return 0


def delete_slot(port: str, slot: int) -> int:
    with open_serial(port) as ser:
        time.sleep(2)
        ser.reset_input_buffer()
        ser.write(f"DELETE {slot}\n".encode("ascii"))
        ser.flush()
        line = read_lines_until(ser, ("DELETE_OK", "DELETE_FAIL"), 5)
        if not line:
            print("no response to DELETE command", file=sys.stderr)
            return 1
        if line.startswith("DELETE_FAIL"):
            print("delete failed", file=sys.stderr)
            return 1
        print(f"deleted slot {slot}")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="e.g. /dev/cu.usbmodem101")
    parser.add_argument("--slot", type=int, required=True, help="1-5, matches START_SLOT/END_SLOT in firmware")
    parser.add_argument("--delete", action="store_true", help="delete the slot instead of enrolling it")
    args = parser.parse_args()

    if args.delete:
        sys.exit(delete_slot(args.port, args.slot))
    else:
        sys.exit(enroll(args.port, args.slot))


if __name__ == "__main__":
    main()
