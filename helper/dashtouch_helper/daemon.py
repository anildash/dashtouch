"""The long-running Mac-side half of Dashboard Touch.

Owns the serial port exclusively. Everything else (web UI, CLI) talks to
this process, never to the port directly.
"""
from __future__ import annotations

import pathlib
import sys
import threading
import time

from . import keychain, protocol, serial_link
from . import webui

DEFAULT_SERIAL = "68EE8F6E7390"


class Daemon:
    # How long a cached password/pairing key is trusted before a match
    # forces a fresh Keychain read. Long enough that a touch doesn't shell
    # out to `security` on every poll; short enough that `dashtouch
    # password`/`dashtouch pairing` take effect within one blink of the
    # helper's ring, no restart required.
    _CREDENTIAL_TTL = 5.0

    def __init__(self, serial_number: str, port: str | None = None):
        self.serial_number = serial_number
        self.port = port
        self.pairing_key = None
        self._password = None
        self._creds_loaded_at = 0.0
        # Tolerant: a fresh checkout (or a setup that never finished) has
        # nothing in the Keychain yet. Run anyway — health() surfaces the
        # gap instead of the process refusing to start.
        self._refresh_credentials()
        self._last_counter = 0
        self._ser = None
        self._write_lock = threading.Lock()
        self._events_lock = threading.Lock()
        self.events: list[dict] = []
        self.pending_label = None
        self.state = {"connected": False, "last_line": "", "sensor": "unknown",
                      "fw": "unknown", "enroll_stage": "", "cap": "",
                      "slots_used": [], "event_seq": 0, "hmac_failures": 0,
                      "last_match": None}

    # -- connection lifecycle -----------------------------------------------
    def _on_connect(self) -> None:
        """New serial session: counter restarts per protocol.md replay rules.
        Event seq is NOT reset — it's monotonic across reconnects so the web page's
        polling logic remains simple."""
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

    # -- credentials (rotation-aware) ----------------------------------
    def _refresh_credentials(self) -> bool:
        """Re-read the pairing key and password from the Keychain if the
        cached copies are older than _CREDENTIAL_TTL (or have never been
        loaded). Called at construction and again at the moment a match
        needs them, so `dashtouch password`/`dashtouch pairing` take
        effect without a helper restart.

        On a Keychain read failure, both values are cleared to None —
        the same "setup incomplete" state a fresh checkout starts in —
        rather than silently trusting a stale cached secret. Returns
        True if both values are available after the call.
        """
        now = time.time()
        if self._creds_loaded_at and now - self._creds_loaded_at < self._CREDENTIAL_TTL:
            return self.pairing_key is not None and self._password is not None
        try:
            self.pairing_key = keychain.get_pairing_key(self.serial_number)
            self._password = keychain.get_password(self.serial_number)
        except keychain.KeychainError:
            self.pairing_key = None
            self._password = None
        self._creds_loaded_at = now
        return self.pairing_key is not None and self._password is not None

    # -- pure logic (unit-tested) ------------------------------------
    def handle_line(self, line: str) -> None:
        # Event-type lines: update last_line and bump sequence number.
        # All other lines (BOOT, INDEX_OK, STATUS_OK, etc.) are logged but don't
        # update the "latest event" or trigger page re-renders.
        event_types = ("TOUCH", "TYPED", "NO_MATCH", "ERR ", "ENROLL_", "DELETE_")
        is_event = line.startswith(event_types)

        if is_event:
            self.state["last_line"] = line
            self.state["event_seq"] += 1

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
            if not self._refresh_credentials():
                # Setup never finished on this Mac, or a Keychain read just
                # failed. Don't even try to verify — the device's own
                # yellow-ring timeout is the designed symptom.
                msg = "match arrived, but Mac-side setup is incomplete — run ./setup"
                print(msg, file=sys.stderr)
                self.log_event("helper", msg)
                return
            try:
                ev = protocol.verify_ev(self.pairing_key, line, self._last_counter)
            except protocol.ProtocolError as e:
                print(f"rejected EV: {e}", file=sys.stderr)
                self.log_event("helper", f"rejected EV: {e}")
                if getattr(e, "code", "") == "hmac":
                    self.state["hmac_failures"] += 1
                    self.log_event("helper",
                        f"pairing check failed ({self.state['hmac_failures']} rejected "
                        "signature(s) so far) — the gadget and this Mac may hold "
                        "different keys")
                return
            self._last_counter = ev.counter
            reply = protocol.encrypt_password(self.pairing_key, ev.nonce,
                                              self._password)
            self.send_command(reply)
            print(f"match slot={ev.slot} score={ev.score} -> sent encrypted password")
            self.log_event("helper", f"match slot={ev.slot} score={ev.score} -> sent encrypted password")
            self.state["last_match"] = {"slot": ev.slot, "score": ev.score}
        elif line.startswith(("ENROLL_", "DELETE_")):
            self.state["enroll_stage"] = line
            print(f"device: {line}")
            self.log_event("device", line)
            if line.startswith("ENROLL_OK"):
                # Save pending label if it matches this slot. A blank label
                # means the page's own naming step hasn't run yet (naming
                # happens after enrollment now) — leave the slot unlabeled
                # rather than writing an empty name.
                if self.pending_label and self.pending_label.get("label"):
                    # Extract slot from line: "ENROLL_OK <slot>"
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            enrolled_slot = int(parts[1])
                            if self.pending_label["slot"] == enrolled_slot:
                                webui.save_label(enrolled_slot, self.pending_label["label"])
                        except (ValueError, IndexError):
                            pass
                self.pending_label = None
                self.send_command("INDEX")
            elif line.startswith("ENROLL_FAIL"):
                # Discard pending label on failure
                self.pending_label = None
                self.send_command("INDEX")
            elif line.startswith("DELETE_OK"):
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

            # Clean up orphan labels: drop any label for a slot not in slots_used and not pending
            labels_to_check = set(self.state["slots_used"])
            if self.pending_label:
                labels_to_check.add(self.pending_label["slot"])
            orphan_count = webui.prune_labels(labels_to_check)
            if orphan_count > 0:
                self.log_event("helper", f"tidied up {orphan_count} leftover name(s)")
        elif line:
            print(f"device: {line}")
            self.log_event("device", line)

    # -- health snapshot (backs the web UI's Checkup list) -------------------
    def health(self) -> list[dict]:
        """Computed fresh on every call — cheap checks, no caching needed."""
        connected = self.state["connected"]
        rows = []

        rows.append({
            "id": "device",
            "label": "Device",
            "ok": connected,
            "detail": f"Connected — firmware {self.state['fw']}" if connected
                      else "Not connected",
            "fix": "help-not-connected",
        })

        if not connected:
            sensor_ok, sensor_detail = None, "Can't check — connect the device first"
        elif self.state["sensor"] == "ok":
            sensor_ok, sensor_detail = True, "Sensor's talking"
        else:
            sensor_ok, sensor_detail = False, "Not answering — check the wiring"
        rows.append({
            "id": "sensor",
            "label": "Sensor",
            "ok": sensor_ok,
            "detail": sensor_detail,
            "fix": "help-no-purple",
        })

        rows.append({
            "id": "password",
            "label": "Password",
            "ok": self._password is not None,
            "detail": "In your Keychain" if self._password is not None
                      else "Not set up yet",
            "fix": "help-rotate",
        })

        n = self.state["hmac_failures"]
        if n > 0:
            pairing_ok = False
            pairing_detail = f"{n} rejected signatures — the gadget and this Mac disagree"
        elif self.pairing_key is not None:
            pairing_ok, pairing_detail = True, "Paired"
        else:
            pairing_ok, pairing_detail = False, "Key missing"
        rows.append({
            "id": "pairing",
            "label": "Pairing",
            "ok": pairing_ok,
            "detail": pairing_detail,
            "fix": "help-pairing",
        })

        plist = pathlib.Path.home() / "Library" / "LaunchAgents" / "com.dashtouch.helper.plist"
        rows.append({
            "id": "autostart",
            "label": "Autostart",
            "ok": None,  # info row, never red — running by hand is a fine choice
            "detail": "Runs automatically at login" if plist.exists()
                      else "Only while you run it by hand",
            "fix": "help-autostart",
        })

        return rows

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
