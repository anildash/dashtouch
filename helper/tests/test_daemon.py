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
    assert d._ser.written == [b"STATUS\n", b"INDEX\n"]


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


def test_index_ok_parses_bitmap_into_slots_used():
    d = make_daemon()
    bitmap_hex = "0a" + "00" * 31  # byte 0 = 0b00001010: slots 1 and 3 set
    d.handle_line(f"INDEX_OK {bitmap_hex}")
    assert d.state["slots_used"] == [1, 3]
    assert d.events[-1] == {"t": d.events[-1]["t"], "dir": "device",
                            "text": f"INDEX_OK {bitmap_hex}"}


def test_enroll_ok_triggers_index_refresh():
    d = make_daemon()
    d.handle_line("ENROLL_OK 3")
    assert d._ser.written[-1] == b"INDEX\n"


def test_index_ok_does_not_update_last_line_or_event_seq():
    d = make_daemon()
    d.handle_line("TOUCH")
    initial_seq = d.state["event_seq"]
    initial_last_line = d.state["last_line"]
    d.handle_line("INDEX_OK 00" + "00" * 31)
    assert d.state["last_line"] == initial_last_line
    assert d.state["event_seq"] == initial_seq


def test_event_types_bump_seq():
    d = make_daemon()
    assert d.state["event_seq"] == 0
    d.handle_line("TOUCH")
    assert d.state["event_seq"] == 1
    assert d.state["last_line"] == "TOUCH"
    d.handle_line("TYPED")
    assert d.state["event_seq"] == 2
    assert d.state["last_line"] == "TYPED"


# -- Task 7e: tolerant init + health() ---------------------------------------

def test_construct_survives_missing_keychain_entries():
    with mock.patch.object(daemon.keychain, "get_pairing_key",
                            side_effect=daemon.keychain.KeychainError("not found")), \
         mock.patch.object(daemon.keychain, "get_password",
                            side_effect=daemon.keychain.KeychainError("not found")):
        d = daemon.Daemon("SER1")
    assert d.pairing_key is None
    assert d._password is None
    rows = {r["id"]: r for r in d.health()}
    assert rows["password"]["ok"] is False
    assert rows["pairing"]["ok"] is False


def test_unconfigured_ev_writes_nothing_and_logs_helper_event():
    d = make_daemon()
    d.pairing_key = None
    d.handle_line(VECTORS["ev_line"])
    assert d._ser.written == []
    helper_events = [e for e in d.events if e["dir"] == "helper"]
    assert any("Mac-side setup is incomplete" in e["text"] for e in helper_events)


def test_tampered_ev_counts_hmac_failure_and_fails_pairing_health():
    d = make_daemon()
    bad = VECTORS["ev_line"][:-1] + ("0" if VECTORS["ev_line"][-1] != "0" else "1")
    d.handle_line(bad)
    assert d.state["hmac_failures"] == 1
    rows = {r["id"]: r for r in d.health()}
    assert rows["pairing"]["ok"] is False
