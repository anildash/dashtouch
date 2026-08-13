"""The long-running Mac-side half of Dashboard Touch.

Owns the serial port exclusively. Everything else (web UI, CLI) talks to
this process, never to the port directly.
"""
from __future__ import annotations

import sys
import threading
import time

from . import keychain, protocol, serial_link
from . import webui

DEFAULT_SERIAL = "68EE8F6E7390"


class Daemon:
    def __init__(self, serial_number: str, port: str | None = None):
        self.serial_number = serial_number
        self.port = port
        self.pairing_key = keychain.get_pairing_key(serial_number)
        self._password = keychain.get_password(serial_number)
        self._last_counter = 0
        self._ser = None
        self._write_lock = threading.Lock()
        self._events_lock = threading.Lock()
        self.events: list[dict] = []
        self.state = {"connected": False, "last_line": "", "sensor": "unknown",
                      "fw": "unknown", "enroll_stage": "", "cap": "",
                      "slots_used": []}

    # -- connection lifecycle -----------------------------------------------
    def _on_connect(self) -> None:
        """New serial session: counter restarts per protocol.md replay rules."""
        self._last_counter = 0
        self.state["connected"] = True
        self.send_command("STATUS")
        self.send_command("INDEX")

    # -- activity log (backs the web UI's debug view) ------------------------
    def log_event(self, direction: str, text: str) -> None:
        """Append to the bounded in-memory event log; oldest entries drop first."""
        with self._events_lock:
            self.events.append({"t": time.time(), "dir": direction, "text": text})
            if len(self.events) > 400:
                del self.events[: len(self.events) - 400]

    # -- pure logic (unit-tested) ------------------------------------
    def handle_line(self, line: str) -> None:
        self.state["last_line"] = line
        if line.startswith("BOOT "):
            self._last_counter = 0
            parts = line.split()
            if len(parts) >= 3:
                self.state["fw"] = parts[2]
            print(f"device: {line}")
            self.log_event("device", line)
        elif line.startswith("EV "):
            # Nonce/counter/hmac aren't secrets without the pairing key.
            self.log_event("device", line)
            try:
                ev = protocol.verify_ev(self.pairing_key, line, self._last_counter)
            except protocol.ProtocolError as e:
                print(f"rejected EV: {e}", file=sys.stderr)
                self.log_event("helper", f"rejected EV: {e}")
                return
            self._last_counter = ev.counter
            reply = protocol.encrypt_password(self.pairing_key, ev.nonce,
                                              self._password)
            self.send_command(reply)
            print(f"match slot={ev.slot} score={ev.score} -> sent encrypted password")
            self.log_event("helper", f"match slot={ev.slot} score={ev.score} -> sent encrypted password")
        elif line.startswith(("ENROLL_", "DELETE_")):
            self.state["enroll_stage"] = line
            print(f"device: {line}")
            self.log_event("device", line)
            if line.startswith(("ENROLL_OK", "DELETE_OK")):
                self.send_command("INDEX")
        elif line.startswith("STATUS_OK"):
            for tok in line.split():
                if tok.startswith("sensor="):
                    self.state["sensor"] = tok.split("=", 1)[1]
                if tok.startswith("fw="):
                    self.state["fw"] = tok.split("=", 1)[1]
                if tok.startswith("cap="):
                    self.state["cap"] = tok.split("=", 1)[1]
        elif line.startswith("INDEX_OK "):
            print(f"device: {line}")
            self.log_event("device", line)
            hex_str = line[len("INDEX_OK "):].strip()
            try:
                bitmap = bytes.fromhex(hex_str)
            except ValueError:
                return
            used = [b * 8 + i for b, byte in enumerate(bitmap) for i in range(8)
                    if byte >> i & 1]
            self.state["slots_used"] = sorted(s for s in used if 1 <= s <= 200)
        elif line:
            print(f"device: {line}")
            self.log_event("device", line)

    # -- I/O ----------------------------------------------------------
    def send_command(self, line: str) -> None:
        if line.startswith("PW "):
            n = len(line[3:]) // 2
            self.log_event("host", f"PW <one-time encrypted password, {n} bytes>")
        else:
            self.log_event("host", line)
        with self._write_lock:
            if self._ser is not None:
                try:
                    self._ser.write((line + "\n").encode())
                    self._ser.flush()
                except (OSError, serial_link.serial.SerialException):
                    self._ser = None

    def run_forever(self) -> None:
        url = webui.start(self)
        print(f"web UI: {url}")
        while True:
            port = self.port or serial_link.find_port()
            if port is None:
                self.state["connected"] = False
                time.sleep(1.0)
                continue
            try:
                with self._write_lock:
                    self._ser = serial_link.open_port(port)
                print(f"helper listening on {port}")
                self.log_event("helper", f"helper listening on {port}")
                self._on_connect()
                while True:
                    line = serial_link.read_line(self._ser)
                    if line is not None:
                        self.handle_line(line)
            except (OSError, serial_link.serial.SerialException):
                self.state["connected"] = False
                with self._write_lock:
                    self._ser = None
                print("port lost; waiting for the board to come back...")
                self.log_event("helper", "port lost; waiting for the board to come back...")
                time.sleep(1.0)


def main(serial_number: str = DEFAULT_SERIAL) -> None:
    Daemon(serial_number).run_forever()


if __name__ == "__main__":
    main()
