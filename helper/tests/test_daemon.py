import json
import pathlib
from unittest import mock

from dashtouch_helper import daemon, protocol

VECTORS = json.loads(
    (pathlib.Path(__file__).parents[2] / "docs" / "protocol-vectors.json").read_text()
)
KEY = bytes.fromhex(VECTORS["pairing_key"])


class FakeSerial:
    def __init__(self):
        self.written = []

    def write(self, b):
        self.written.append(b)

    def flush(self):
        pass


def make_daemon():
    with mock.patch.object(daemon.keychain, "get_pairing_key", return_value=KEY), \
         mock.patch.object(daemon.keychain, "get_password", return_value="pw123"):
        d = daemon.Daemon("SER1")
    d._ser = FakeSerial()
    return d


def test_boot_resets_counter():
    d = make_daemon()
    d._last_counter = 99
    d.handle_line("BOOT dashtouch dt-0.1.0 proto=1")
    assert d._last_counter == 0


def test_valid_ev_gets_pw_reply():
    d = make_daemon()
    d.handle_line(VECTORS["ev_line"])
    assert len(d._ser.written) == 1
    reply = d._ser.written[0].decode()
    assert reply.startswith("PW ")
    assert d._last_counter == VECTORS["counter"]


def test_replayed_ev_gets_no_reply():
    d = make_daemon()
    d.handle_line(VECTORS["ev_line"])
    d.handle_line(VECTORS["ev_line"])  # same counter again
    assert len(d._ser.written) == 1


def test_tampered_ev_gets_no_reply():
    d = make_daemon()
    bad = VECTORS["ev_line"][:-1] + ("0" if VECTORS["ev_line"][-1] != "0" else "1")
    d.handle_line(bad)
    assert d._ser.written == []


def test_enroll_stage_tracked_for_webui():
    d = make_daemon()
    d.handle_line("ENROLL_WAIT_FINGER_1")
    assert d.state["enroll_stage"] == "ENROLL_WAIT_FINGER_1"
    d.handle_line("ENROLL_OK 3")
    assert d.state["enroll_stage"] == "ENROLL_OK 3"


def test_new_session_resets_counter():
    d = make_daemon()
    d._last_counter = 99
    d._on_connect()
    assert d._last_counter == 0
    assert d._ser.written == [b"STATUS\n"]


def test_log_event_caps_at_400():
    d = make_daemon()
    for i in range(405):
        d.log_event("helper", f"event {i}")
    assert len(d.events) == 400
    assert d.events[0]["text"] == "event 5"
    assert d.events[-1]["text"] == "event 404"


def test_handle_line_logs_device_event():
    d = make_daemon()
    d.handle_line("TOUCH")
    assert d.events[-1] == {"t": d.events[-1]["t"], "dir": "device", "text": "TOUCH"}


def test_send_command_redacts_pw_payload():
    d = make_daemon()
    d.send_command("PW abc123")
    host_events = [e for e in d.events if e["dir"] == "host"]
    assert len(host_events) == 1
    assert host_events[0]["text"] == "PW <one-time encrypted password, 3 bytes>"
    assert "abc123" not in host_events[0]["text"]
