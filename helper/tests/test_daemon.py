import hashlib
import hmac as hmac_mod
import json
import pathlib
import time
from unittest import mock

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from dashtouch_helper import daemon, protocol

VECTORS = json.loads(
    (pathlib.Path(__file__).parents[2] / "docs" / "protocol-vectors.json").read_text()
)
KEY = bytes.fromhex(VECTORS["pairing_key"])


def make_ev_line(key: bytes, nonce_hex: str, counter: int, slot: int, score: int) -> str:
    """Build a validly-signed EV line for tests that need a second touch
    (the fixture vector only covers one counter value)."""
    canonical = f"EV {nonce_hex} {counter} {slot} {score}".encode()
    mac = hmac_mod.new(key, canonical, hashlib.sha256).hexdigest()
    return f"EV {nonce_hex} {counter} {slot} {score} {mac}"


def decrypt_pw_line(key: bytes, nonce: bytes, pw_line: str) -> str:
    _, gcm_hex, ct_hex = pw_line.split(" ")
    response_key = protocol.derive_response_key(key, nonce)
    pt = AESGCM(response_key).decrypt(bytes.fromhex(gcm_hex), bytes.fromhex(ct_hex), None)
    return pt.decode()


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
    # PAUSE 0 goes out first: a stale pause (page reload mid-naming, or this
    # helper restarting) must never survive a reconnect.
    assert d._ser.written == [b"PAUSE 0\n", b"STATUS\n", b"INDEX\n", b"SETTINGS\n"]


def test_on_connect_always_sends_pause_0():
    d = make_daemon()
    d._on_connect()
    assert b"PAUSE 0\n" in d._ser.written


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
    # Fixed placeholder, no byte count — the ciphertext length otherwise
    # discloses the password's length.
    assert host_events[0]["text"] == "PW <one-time encrypted password>"
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


def test_hmac_failure_counted_by_error_code():
    d = make_daemon()
    # Tamper with the vector EV by flipping the last hex character
    tampered = VECTORS["ev_line"][:-1] + ("0" if VECTORS["ev_line"][-1] != "0" else "1")
    d.handle_line(tampered)
    assert d.state["hmac_failures"] == 1


def test_crafted_line_with_hmac_string_does_not_crash():
    d = make_daemon()
    # Crafted line containing "HMAC" but not a valid EV — should not increment hmac_failures
    d.handle_line("EV HMACAAAA junk")
    assert d.state["hmac_failures"] == 0


def test_replayed_ev_does_not_count_as_hmac_failure():
    d = make_daemon()
    # Feed the valid vector EV twice — second should be rejected as replay, not HMAC failure
    d.handle_line(VECTORS["ev_line"])
    assert d.state["hmac_failures"] == 0
    d.handle_line(VECTORS["ev_line"])
    assert d.state["hmac_failures"] == 0


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


# -- Task 7k: per-row state string alongside ok --------------------------

def test_health_rows_carry_state_string():
    d = make_daemon()
    rows = {r["id"]: r for r in d.health()}
    for row in rows.values():
        assert "state" in row


def test_disconnected_device_reports_bad_state():
    d = daemon.Daemon("SER1")
    d._ser = FakeSerial()
    rows = {r["id"]: r for r in d.health()}
    assert rows["device"]["ok"] is False
    assert rows["device"]["state"] == "bad"


def test_autostart_off_reports_off_not_bad(monkeypatch):
    d = make_daemon()
    monkeypatch.setattr(daemon.pathlib.Path, "exists", lambda self: False)
    rows = {r["id"]: r for r in d.health()}
    assert rows["autostart"]["ok"] is None
    assert rows["autostart"]["state"] == "off"


def test_autostart_on_reports_ok_state(monkeypatch):
    d = make_daemon()
    monkeypatch.setattr(daemon.pathlib.Path, "exists", lambda self: True)
    rows = {r["id"]: r for r in d.health()}
    assert rows["autostart"]["state"] == "ok"


def test_failing_sensor_reports_bad_state():
    d = make_daemon()
    d.state["connected"] = True
    d.state["sensor"] = "fail"
    rows = {r["id"]: r for r in d.health()}
    assert rows["sensor"]["ok"] is False
    assert rows["sensor"]["state"] == "bad"


def test_valid_ev_records_last_match():
    d = make_daemon()
    d.handle_line(VECTORS["ev_line"])
    assert d.state["last_match"] == {"slot": VECTORS["slot"], "score": VECTORS["score"]}


def test_tampered_ev_does_not_record_last_match():
    d = make_daemon()
    bad = VECTORS["ev_line"][:-1] + ("0" if VECTORS["ev_line"][-1] != "0" else "1")
    d.handle_line(bad)
    assert d.state["last_match"] is None


def test_unconfigured_daemon_with_valid_ev_does_not_record_last_match():
    # No pairing key setup
    d = daemon.Daemon("SER1")
    d._ser = FakeSerial()
    d.handle_line(VECTORS["ev_line"])
    assert d.state["last_match"] is None


def test_enroll_ok_writes_pending_label(tmp_path, monkeypatch):
    """ENROLL_OK with pending_label writes the label."""
    from dashtouch_helper import webui
    monkeypatch.setattr(webui, "LABELS_PATH", tmp_path / "labels.json")
    d = make_daemon()
    d.pending_label = {"slot": 3, "label": "right index"}
    d.handle_line("ENROLL_OK 3")
    # After ENROLL_OK, label should be written in object form, with a
    # freshly-set `added` timestamp (this is a brand new entry).
    labels = json.loads((tmp_path / "labels.json").read_text())
    assert labels["3"]["label"] == "right index"
    assert labels["3"]["added"] > 0
    assert d.pending_label is None


def test_enroll_ok_with_blank_pending_label_does_not_write(tmp_path, monkeypatch):
    """ENROLL_OK with a blank pending label (naming happens after enrollment
    now) leaves the slot unlabeled instead of writing an empty name."""
    from dashtouch_helper import webui
    monkeypatch.setattr(webui, "LABELS_PATH", tmp_path / "labels.json")
    d = make_daemon()
    d.pending_label = {"slot": 3, "label": ""}
    d.handle_line("ENROLL_OK 3")
    assert not (tmp_path / "labels.json").exists()
    assert d.pending_label is None


def test_enroll_fail_clears_pending_label():
    """ENROLL_FAIL clears pending_label without writing."""
    d = make_daemon()
    d.pending_label = {"slot": 3, "label": "right index"}
    d.handle_line("ENROLL_FAIL slot_3_used")
    assert d.pending_label is None


def test_index_ok_prunes_orphan_labels(tmp_path, monkeypatch):
    """INDEX_OK prunes labels for slots not in the bitmap."""
    from dashtouch_helper import webui
    monkeypatch.setattr(webui, "LABELS_PATH", tmp_path / "labels.json")
    d = make_daemon()
    # Pre-populate labels with a non-existent slot
    labels = {"1": "thumb", "5": "ghost", "3": "index"}
    (tmp_path / "labels.json").write_text(json.dumps(labels))
    # INDEX_OK with only slots 1, 3 enrolled
    # Slot 1: bit 1 in byte 0 (0b00000010 = 0x02)
    # Slot 3: bit 3 in byte 0 (0b00001000 = 0x08)
    # Combined: 0x02 | 0x08 = 0x0A
    d.handle_line("INDEX_OK 0a")
    # Slot 5 should be pruned
    updated_labels = json.loads((tmp_path / "labels.json").read_text())
    assert "1" in updated_labels
    assert "3" in updated_labels
    assert "5" not in updated_labels
    # Should have logged pruning
    helper_events = [e for e in d.events if e["dir"] == "helper"]
    assert any("tidied up" in e["text"] for e in helper_events)


# -- Task 7j: rotation-aware credential cache ---------------------------------

def test_daemon_picks_up_rotated_password_after_ttl(monkeypatch):
    with mock.patch.object(daemon.keychain, "get_pairing_key", return_value=KEY), \
         mock.patch.object(daemon.keychain, "get_password", return_value="old"):
        d = daemon.Daemon("SER1")
    d._ser = FakeSerial()

    # First touch: within the TTL window, gets the "old" password.
    d.handle_line(VECTORS["ev_line"])
    assert len(d._ser.written) == 1
    reply1 = d._ser.written[0].decode()
    assert decrypt_pw_line(KEY, bytes.fromhex(VECTORS["nonce"]), reply1) == "old"

    # Rotate: Keychain now reports a new password, and the TTL has elapsed.
    real_time = time.time
    monkeypatch.setattr(daemon.time, "time", lambda: real_time() + 10)
    ev2 = make_ev_line(KEY, VECTORS["nonce"], VECTORS["counter"] + 1,
                       VECTORS["slot"], VECTORS["score"])
    with mock.patch.object(daemon.keychain, "get_pairing_key", return_value=KEY), \
         mock.patch.object(daemon.keychain, "get_password", return_value="new"):
        d.handle_line(ev2)

    assert len(d._ser.written) == 2
    reply2 = d._ser.written[1].decode()
    assert decrypt_pw_line(KEY, bytes.fromhex(VECTORS["nonce"]), reply2) == "new"


def test_daemon_does_not_reread_keychain_within_ttl(monkeypatch):
    """A touch within the TTL window must not shell out to `security` again
    — only the initial construction-time read should happen."""
    with mock.patch.object(daemon.keychain, "get_pairing_key", return_value=KEY) as gpk, \
         mock.patch.object(daemon.keychain, "get_password", return_value="old") as gp:
        d = daemon.Daemon("SER1")
        d._ser = FakeSerial()
        d.handle_line(VECTORS["ev_line"])
        assert gpk.call_count == 1
        assert gp.call_count == 1


def test_keychain_failure_at_match_time_is_graceful(monkeypatch):
    with mock.patch.object(daemon.keychain, "get_pairing_key", return_value=KEY), \
         mock.patch.object(daemon.keychain, "get_password", return_value="old"):
        d = daemon.Daemon("SER1")
    d._ser = FakeSerial()

    # Advance past the TTL so the next EV forces a fresh Keychain read.
    real_time = time.time
    monkeypatch.setattr(daemon.time, "time", lambda: real_time() + 10)
    ev2 = make_ev_line(KEY, VECTORS["nonce"], VECTORS["counter"] + 1,
                       VECTORS["slot"], VECTORS["score"])
    with mock.patch.object(daemon.keychain, "get_password",
                           side_effect=daemon.keychain.KeychainError("locked")):
        d.handle_line(ev2)

    assert d._ser.written == []  # no serial write
    helper_events = [e for e in d.events if e["dir"] == "helper"]
    assert any("Mac-side setup is incomplete" in e["text"] for e in helper_events)
    assert d.pairing_key is None
    assert d._password is None


# -- Task 7m: device settings (idle ring color/style, press_enter) -----------

def test_settings_defaults_to_none_until_seen():
    d = make_daemon()
    assert d.state["settings"] is None


def test_settings_ok_parses_all_three_keys():
    d = make_daemon()
    d.handle_line("SETTINGS_OK idle_color=3 idle_style=1 press_enter=1 fp_swap=0")
    assert d.state["settings"] == {
        "idle_color": 3, "idle_style": 1, "press_enter": True, "fp_swap": False}


def test_settings_ok_parses_press_enter_false():
    d = make_daemon()
    d.handle_line("SETTINGS_OK idle_color=0 idle_style=2 press_enter=0 fp_swap=0")
    assert d.state["settings"] == {
        "idle_color": 0, "idle_style": 2, "press_enter": False, "fp_swap": False}


def test_set_ok_updates_idle_color_in_existing_settings():
    d = make_daemon()
    d.handle_line("SETTINGS_OK idle_color=3 idle_style=1 press_enter=1 fp_swap=0")
    d.handle_line("SET_OK idle_color 6")
    assert d.state["settings"] == {
        "idle_color": 6, "idle_style": 1, "press_enter": True, "fp_swap": False}


def test_set_ok_updates_idle_style_in_existing_settings():
    d = make_daemon()
    d.handle_line("SETTINGS_OK idle_color=3 idle_style=1 press_enter=1 fp_swap=0")
    d.handle_line("SET_OK idle_style 2")
    assert d.state["settings"] == {
        "idle_color": 3, "idle_style": 2, "press_enter": True, "fp_swap": False}


def test_set_ok_updates_press_enter_in_existing_settings():
    d = make_daemon()
    d.handle_line("SETTINGS_OK idle_color=3 idle_style=1 press_enter=1 fp_swap=0")
    d.handle_line("SET_OK press_enter 0")
    assert d.state["settings"] == {
        "idle_color": 3, "idle_style": 1, "press_enter": False, "fp_swap": False}


def test_set_ok_before_any_settings_ok_starts_from_empty():
    d = make_daemon()
    d.handle_line("SET_OK idle_color 4")
    assert d.state["settings"] == {"idle_color": 4}


# -- Task 7n: fp_swap (device-stored sensor pin orientation) ----------------

def test_settings_ok_parses_fp_swap_true():
    d = make_daemon()
    d.handle_line("SETTINGS_OK idle_color=3 idle_style=1 press_enter=1 fp_swap=1")
    assert d.state["settings"] == {
        "idle_color": 3, "idle_style": 1, "press_enter": True, "fp_swap": True}


def test_settings_ok_parses_fp_swap_false():
    d = make_daemon()
    d.handle_line("SETTINGS_OK idle_color=3 idle_style=1 press_enter=1 fp_swap=0")
    assert d.state["settings"]["fp_swap"] is False


def test_settings_ok_missing_fp_swap_leaves_settings_none():
    # Mirrors the old-firmware guard: a reply missing any of the four
    # known keys shouldn't produce a half-populated settings dict.
    d = make_daemon()
    d.handle_line("SETTINGS_OK idle_color=3 idle_style=1 press_enter=1")
    assert d.state["settings"] is None


def test_set_ok_updates_fp_swap_in_existing_settings():
    d = make_daemon()
    d.handle_line("SETTINGS_OK idle_color=3 idle_style=1 press_enter=1 fp_swap=0")
    d.handle_line("SET_OK fp_swap 1")
    assert d.state["settings"] == {
        "idle_color": 3, "idle_style": 1, "press_enter": True, "fp_swap": True}


def test_set_ok_fp_swap_does_not_claim_a_fresh_status():
    # The firmware can't verify a live pin-orientation change (real
    # hardware testing showed in-place UART re-init is unreliable and can
    # report success falsely) — so the daemon has nothing trustworthy to
    # learn by asking again right now, and shouldn't pretend otherwise.
    d = make_daemon()
    d.handle_line("SETTINGS_OK idle_color=3 idle_style=1 press_enter=1 fp_swap=0")
    before = list(d._ser.written)
    d.handle_line("SET_OK fp_swap 1 reboot_required")
    after = d._ser.written
    assert after[len(before):] == []


def test_set_ok_fp_swap_marks_sensor_unverified_pending_reboot():
    d = make_daemon()
    d.state["connected"] = True
    d.state["sensor"] = "ok"  # describes the OLD orientation
    d.handle_line("SETTINGS_OK idle_color=3 idle_style=1 press_enter=1 fp_swap=0")
    d.handle_line("SET_OK fp_swap 1 reboot_required")
    assert d.state["sensor"] == "unknown"
    assert d.state["fp_swap_reboot_required"] is True
    rows = {r["id"]: r for r in d.health()}
    assert rows["sensor"]["state"] == "warn"
    assert rows["sensor"]["ok"] is None
    assert "power-cycle" in rows["sensor"]["detail"]


def test_boot_line_clears_fp_swap_reboot_required():
    d = make_daemon()
    d.state["connected"] = True
    d.handle_line("SETTINGS_OK idle_color=3 idle_style=1 press_enter=1 fp_swap=0")
    d.handle_line("SET_OK fp_swap 1 reboot_required")
    assert d.state["fp_swap_reboot_required"] is True
    d.handle_line("BOOT dashtouch 0.1.0 proto=1")
    assert d.state["fp_swap_reboot_required"] is False


def test_set_ok_idle_color_does_not_request_status():
    d = make_daemon()
    d.handle_line("SETTINGS_OK idle_color=3 idle_style=1 press_enter=1 fp_swap=0")
    before = list(d._ser.written)
    d.handle_line("SET_OK idle_color 5")
    after = d._ser.written
    assert after[len(before):] == []


def test_old_firmware_never_sends_settings_ok_state_stays_none():
    d = make_daemon()
    d.handle_line("STATUS_OK proto=1 fw=dt-0.1.0 sensor=ok cap=200")
    assert d.state["settings"] is None


# -- Task 7s: PAUSE (device stops matching while a naming field is open) -----

def test_state_defaults_to_unpaused():
    d = make_daemon()
    assert d.state["paused"] is False


def test_pause_ok_1_sets_paused_true():
    d = make_daemon()
    d.handle_line("PAUSE_OK 1")
    assert d.state["paused"] is True


def test_pause_ok_0_sets_paused_false():
    d = make_daemon()
    d.state["paused"] = True
    d.handle_line("PAUSE_OK 0")
    assert d.state["paused"] is False


def test_status_ok_parses_paused_true():
    d = make_daemon()
    d.handle_line("STATUS_OK proto=1 fw=dt-0.1.0 sensor=ok cap=200 paused=1")
    assert d.state["paused"] is True


def test_status_ok_parses_paused_false():
    d = make_daemon()
    d.state["paused"] = True
    d.handle_line("STATUS_OK proto=1 fw=dt-0.1.0 sensor=ok cap=200 paused=0")
    assert d.state["paused"] is False


def test_status_ok_without_paused_field_leaves_it_unchanged():
    # Old-firmware tolerance, same pattern as the settings fields: a reply
    # missing paused= doesn't get guessed at.
    d = make_daemon()
    d.state["paused"] = True
    d.handle_line("STATUS_OK proto=1 fw=dt-0.1.0 sensor=ok cap=200")
    assert d.state["paused"] is True


# -- security review fixes ---------------------------------------------------

def test_send_command_write_failure_marks_disconnected():
    # A serial write failure must clear both `_ser` AND `connected` — leaving
    # `connected` True while `_ser` is None used to send the next read_line
    # call straight into an uncaught AttributeError.
    d = make_daemon()
    d.state["connected"] = True

    class BoomSerial:
        def write(self, b):
            raise OSError("gone")

        def flush(self):
            pass

    d._ser = BoomSerial()
    d.send_command("STATUS")
    assert d._ser is None
    assert d.state["connected"] is False


def test_run_forever_prints_bare_url_when_not_a_tty(monkeypatch, capsys):
    # Under launchd, stdout is a log file, not a terminal — the tokened URL
    # must never land there. Only the bare origin should be printed.
    d = make_daemon()
    monkeypatch.setattr(daemon.webui, "start",
                        lambda self: "http://127.0.0.1:3274/?token=SECRETTOKEN")
    monkeypatch.setattr(daemon.serial_link, "find_port", lambda: "/dev/fake")
    monkeypatch.setattr(daemon.serial_link, "open_port", lambda port: mock.Mock())
    monkeypatch.setattr(daemon.sys.stdout, "isatty", lambda: False)

    def boom(ser):
        raise RuntimeError("stop test loop")

    monkeypatch.setattr(daemon.serial_link, "read_line", boom)
    with pytest.raises(RuntimeError):
        d.run_forever()
    out = capsys.readouterr().out
    assert "SECRETTOKEN" not in out
    assert "http://127.0.0.1:3274" in out
    assert str(daemon.webui.URL_PATH) in out


def test_run_forever_prints_full_url_when_a_tty(monkeypatch, capsys):
    d = make_daemon()
    monkeypatch.setattr(daemon.webui, "start",
                        lambda self: "http://127.0.0.1:3274/?token=SECRETTOKEN")
    monkeypatch.setattr(daemon.serial_link, "find_port", lambda: "/dev/fake")
    monkeypatch.setattr(daemon.serial_link, "open_port", lambda port: mock.Mock())
    monkeypatch.setattr(daemon.sys.stdout, "isatty", lambda: True)

    def boom(ser):
        raise RuntimeError("stop test loop")

    monkeypatch.setattr(daemon.serial_link, "read_line", boom)
    with pytest.raises(RuntimeError):
        d.run_forever()
    out = capsys.readouterr().out
    assert "SECRETTOKEN" in out


def test_run_forever_survives_exception_in_handle_line(monkeypatch):
    # A bug anywhere in handle_line used to escape run_forever's narrow
    # (OSError, SerialException) handler and kill the daemon outright —
    # a crash-loop under launchd's KeepAlive. It must now be caught, logged,
    # and the loop must keep reading.
    d = make_daemon()
    monkeypatch.setattr(daemon.webui, "start", lambda self: "http://127.0.0.1:3274/?token=T")
    monkeypatch.setattr(daemon.serial_link, "find_port", lambda: "/dev/fake")
    monkeypatch.setattr(daemon.serial_link, "open_port", lambda port: mock.Mock())

    lines = iter(["BOGUS", None])

    def fake_read_line(ser):
        try:
            return next(lines)
        except StopIteration:
            raise RuntimeError("stop test loop")

    monkeypatch.setattr(daemon.serial_link, "read_line", fake_read_line)

    def boom(line):
        raise ValueError("kaboom")

    monkeypatch.setattr(d, "handle_line", boom)
    with pytest.raises(RuntimeError):
        d.run_forever()
    helper_events = [e for e in d.events if e["dir"] == "helper"]
    assert any("kaboom" in e["text"] for e in helper_events)


def test_run_forever_stops_reading_when_ser_dropped_mid_loop(monkeypatch):
    # Mirrors the scenario a write failure creates: `_ser` goes to None
    # mid-session. The inner loop must notice and hand control back to the
    # outer reconnect loop instead of calling read_line(None).
    d = make_daemon()
    monkeypatch.setattr(daemon.webui, "start", lambda self: "http://127.0.0.1:3274/?token=T")

    ports = iter(["/dev/fake", None])
    monkeypatch.setattr(daemon.serial_link, "find_port",
                        lambda: next(ports, "STOP"))
    monkeypatch.setattr(daemon.serial_link, "open_port", lambda port: mock.Mock())

    def fake_read_line(ser):
        d._ser = None  # simulate a write failure nulling it out
        return None

    monkeypatch.setattr(daemon.serial_link, "read_line", fake_read_line)

    def boom(*a, **k):
        raise RuntimeError("stop test loop")

    monkeypatch.setattr(daemon.time, "sleep", boom)
    with pytest.raises(RuntimeError):
        d.run_forever()
