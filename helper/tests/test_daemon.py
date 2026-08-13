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
