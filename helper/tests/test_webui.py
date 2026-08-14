import http.client
import json
import threading
import time
from types import SimpleNamespace

from dashtouch_helper import webui


CANNED_HEALTH = [
    {"id": "device", "label": "Device", "ok": True, "state": "ok",
     "detail": "Connected — firmware dt-0.1.0", "fix": "help-not-connected"},
    {"id": "password", "label": "Password", "ok": False, "state": "bad",
     "detail": "Not set up yet", "fix": "help-password"},
]


class FakeDaemon:
    def __init__(self):
        self.state = {"connected": True, "sensor": "ok", "fw": "dt-0.1.0",
                      "enroll_stage": "", "last_line": "", "cap": "200",
                      "slots_used": [1, 3], "last_match": None}
        self.sent = []
        self.events = []
        self._events_lock = threading.Lock()

    def send_command(self, line):
        self.sent.append(line)

    def log_event(self, direction, text):
        self.events.append({"t": time.time(), "dir": direction, "text": text})

    def health(self):
        return CANNED_HEALTH


def start():
    d = FakeDaemon()
    url = webui.start(d, port=0)  # 0 = ephemeral port for tests
    host, port = url.split("//")[1].split("/")[0].split(":")
    token = url.split("token=")[1]
    return d, host, int(port), token


def req(host, port, method, path, body=None, token=None):
    c = http.client.HTTPConnection(host, port, timeout=3)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-DT-Token"] = token
    c.request(method, path, json.dumps(body) if body else None, headers)
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")


def test_status_needs_no_token():
    d, host, port, token = start()
    status, body = req(host, port, "GET", "/api/status")
    assert status == 200 and body["connected"] is True


def test_status_carries_slots_used():
    d, host, port, token = start()
    status, body = req(host, port, "GET", "/api/status")
    assert status == 200
    assert body["slots_used"] == [1, 3]


def test_status_carries_health_rows():
    d, host, port, token = start()
    status, body = req(host, port, "GET", "/api/status")
    assert status == 200
    assert body["health"] == CANNED_HEALTH


def test_enroll_without_token_rejected():
    d, host, port, token = start()
    status, _ = req(host, port, "POST", "/api/enroll", {"slot": 1, "label": "x"})
    assert status == 403
    assert d.sent == []


def test_enroll_with_token_sends_command_and_saves_label(tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "LABELS_PATH", tmp_path / "labels.json")
    d, host, port, token = start()
    status, _ = req(host, port, "POST", "/api/enroll",
                    {"slot": 2, "label": "right index"}, token)
    assert status == 202
    assert d.sent == ["ENROLL 2"]
    # Label is stored in pending_label, not written yet
    assert d.pending_label == {"slot": 2, "label": "right index"}
    # Labels file should not exist
    assert not (tmp_path / "labels.json").exists()


def test_delete_with_token(tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "LABELS_PATH", tmp_path / "labels.json")
    d, host, port, token = start()
    req(host, port, "POST", "/api/enroll", {"slot": 2, "label": "x"}, token)
    status, _ = req(host, port, "POST", "/api/delete", {"slot": 2}, token)
    assert status == 202
    assert d.sent == ["ENROLL 2", "DELETE 2"]


def test_malformed_body_returns_400():
    d, host, port, token = start()
    c = http.client.HTTPConnection(host, port, timeout=3)
    c.request("POST", "/api/enroll", "not json{{{", {"Content-Type": "application/json", "X-DT-Token": token})
    assert c.getresponse().status == 400
    assert d.sent == []


def test_non_object_json_body_returns_400():
    d, host, port, token = start()
    c = http.client.HTTPConnection(host, port, timeout=3)
    c.request("POST", "/api/enroll", "[1,2,3]", {"Content-Type": "application/json", "X-DT-Token": token})
    assert c.getresponse().status == 400
    assert d.sent == []


def test_start_persists_tokened_url(tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "URL_PATH", tmp_path / "webui-url")
    d = FakeDaemon()
    url = webui.start(d, port=0)
    assert (tmp_path / "webui-url").read_text().strip() == url
    assert "token=" in url


def test_start_reuses_existing_token(tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "TOKEN_PATH", tmp_path / "token")
    # Pre-seed the token file
    seeded_token = "seededtoken12345678"
    (tmp_path / "token").write_text(seeded_token + "\n")
    d = FakeDaemon()
    url = webui.start(d, port=0)
    assert f"token={seeded_token}" in url


def test_start_creates_token_file(tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "TOKEN_PATH", tmp_path / "token")
    d = FakeDaemon()
    url = webui.start(d, port=0)
    assert (tmp_path / "token").exists()
    token_content = (tmp_path / "token").read_text().strip()
    assert len(token_content) >= 16
    assert f"token={token_content}" in url


def test_start_with_token_path_as_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "TOKEN_PATH", tmp_path / "token")
    # Create a directory where the token file should be
    (tmp_path / "token").mkdir()
    d = FakeDaemon()
    url = webui.start(d, port=0)
    # Should still work with an in-memory token despite the directory in the way
    assert "token=" in url


def test_start_with_invalid_utf8_token(tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "TOKEN_PATH", tmp_path / "token")
    # Write invalid UTF-8 bytes to the token file
    (tmp_path / "token").write_bytes(b"\xff\xfe")
    d = FakeDaemon()
    url = webui.start(d, port=0)
    # Should generate a fresh token and overwrite the corrupted file
    assert "token=" in url
    token_content = (tmp_path / "token").read_text().strip()
    assert len(token_content) >= 16


def test_enroll_with_null_slot_returns_400():
    d, host, port, token = start()
    status, _ = req(host, port, "POST", "/api/enroll", {"slot": None, "label": "x"}, token)
    assert status == 400
    assert d.sent == []


def test_log_requires_token_then_returns_events():
    d, host, port, token = start()
    status, _ = req(host, port, "GET", "/api/log")
    assert status == 403
    d.log_event("device", "hello")
    status, body = req(host, port, "GET", "/api/log", token=token)
    assert status == 200
    assert any(e["text"] == "hello" for e in body["events"])


def test_rejected_post_appends_web_event():
    d, host, port, token = start()
    req(host, port, "POST", "/api/enroll", {"slot": 1, "label": "x"})  # no token
    status, body = req(host, port, "GET", "/api/log", token=token)
    assert status == 200
    assert any(e["text"] == "rejected: bad token" for e in body["events"])


def test_default_port_is_3274():
    """When no port argument is given, default is 3274 (or fallback if busy)."""
    d = FakeDaemon()
    url = webui.start(d)  # no port argument = use default
    # Extract port from URL
    actual_port = int(url.split(":")[2].split("/")[0])
    # Port should be 3274 unless it was busy (check daemon log for fallback message)
    if actual_port == 3274:
        # Normal case: port 3274 was available
        assert True
    else:
        # Fallback case: port 3274 was busy, check that we logged it
        assert any("was busy" in e.get("text", "") for e in d.events)


def test_dashtouch_port_env_override_ephemeral():
    """DASHTOUCH_PORT=0 env variable overrides default and uses ephemeral binding."""
    d = FakeDaemon()
    import os
    # Temporarily set env var
    old_val = os.environ.get("DASHTOUCH_PORT")
    try:
        os.environ["DASHTOUCH_PORT"] = "0"
        url = webui.start(d)  # no port argument, but env override = 0 (ephemeral)
        # Extract port from URL
        actual_port = int(url.split(":")[2].split("/")[0])
        # Should be ephemeral (non-zero, assigned by OS)
        assert actual_port > 0, "Ephemeral binding should assign a port > 0"
        assert actual_port != 3274, "With DASHTOUCH_PORT=0, should not use default port"
    finally:
        if old_val is None:
            os.environ.pop("DASHTOUCH_PORT", None)
        else:
            os.environ["DASHTOUCH_PORT"] = old_val


def test_api_status_carries_last_match():
    """Verify that /api/status includes last_match from daemon state."""
    d = FakeDaemon()
    d.state["last_match"] = {"slot": 5, "score": 150}
    host, port, token = start.__wrapped__(d, None, None) if hasattr(start, '__wrapped__') else (None, None, None)
    # Need to get host/port from actual start; use simpler approach
    url = webui.start(d, port=0)
    host, port = url.split("//")[1].split("/")[0].split(":")
    host = host.strip()
    port = int(port)
    token = url.split("token=")[1]

    status, body = req(host, port, "GET", "/api/status")
    assert status == 200
    assert body["last_match"] == {"slot": 5, "score": 150}


def test_enroll_stores_pending_label_not_labels_file(tmp_path, monkeypatch):
    """Enroll request stores pending_label but doesn't write labels.json."""
    from dashtouch_helper import webui
    monkeypatch.setattr(webui, "LABELS_PATH", tmp_path / "labels.json")
    d = FakeDaemon()
    url = webui.start(d, port=0)
    host, port = url.split("//")[1].split("/")[0].split(":")
    token = url.split("token=")[1]
    port = int(port)

    # Enroll a finger
    status, body = req(host, port, "POST", "/api/enroll",
                       {"slot": 5, "label": "right index"}, token=token)
    assert status == 202

    # Labels file should not exist yet
    assert not (tmp_path / "labels.json").exists()
    # Daemon should have pending_label
    assert d.pending_label == {"slot": 5, "label": "right index"}


def test_api_label_requires_token(tmp_path, monkeypatch):
    """POST /api/label without token returns 403."""
    from dashtouch_helper import webui
    monkeypatch.setattr(webui, "LABELS_PATH", tmp_path / "labels.json")
    d = FakeDaemon()
    url = webui.start(d, port=0)
    host, port = url.split("//")[1].split("/")[0].split(":")
    token = url.split("token=")[1]
    port = int(port)

    status, body = req(host, port, "POST", "/api/label",
                       {"slot": 3, "label": "middle"}, token=None)
    assert status == 403


def test_api_label_updates_labels(tmp_path, monkeypatch):
    """POST /api/label with token updates labels.json."""
    from dashtouch_helper import webui
    monkeypatch.setattr(webui, "LABELS_PATH", tmp_path / "labels.json")
    d = FakeDaemon()
    url = webui.start(d, port=0)
    host, port = url.split("//")[1].split("/")[0].split(":")
    token = url.split("token=")[1]
    port = int(port)

    status, body = req(host, port, "POST", "/api/label",
                       {"slot": 3, "label": "middle"}, token=token)
    assert status == 202

    # Check that label was written in object form with a fresh timestamp
    labels = json.loads((tmp_path / "labels.json").read_text())
    assert labels["3"]["label"] == "middle"
    assert labels["3"]["added"] > 0


def test_api_label_slot_out_of_range(tmp_path, monkeypatch):
    """POST /api/label with slot 0 or 201 returns 400."""
    from dashtouch_helper import webui
    monkeypatch.setattr(webui, "LABELS_PATH", tmp_path / "labels.json")
    d = FakeDaemon()
    url = webui.start(d, port=0)
    host, port = url.split("//")[1].split("/")[0].split(":")
    token = url.split("token=")[1]
    port = int(port)

    status, body = req(host, port, "POST", "/api/label",
                       {"slot": 0, "label": "invalid"}, token=token)
    assert status == 400

    status, body = req(host, port, "POST", "/api/label",
                       {"slot": 201, "label": "invalid"}, token=token)
    assert status == 400


def test_old_format_string_label_loads_and_is_readable(tmp_path, monkeypatch):
    """A bare slot->string entry (the pre-Task-7i format) is tolerated: the
    loader upgrades it to {"label": str, "added": 0.0} in memory without
    requiring the user's on-disk file to be migrated first."""
    from dashtouch_helper import webui
    monkeypatch.setattr(webui, "LABELS_PATH", tmp_path / "labels.json")
    (tmp_path / "labels.json").write_text(json.dumps({"3": "right index"}))
    d = FakeDaemon()
    d.state["slots_used"] = [3]
    url = webui.start(d, port=0)
    host, port = url.split("//")[1].split("/")[0].split(":")
    port = int(port)

    status, body = req(host, port, "GET", "/api/status")
    assert status == 200
    assert body["slots"]["3"] == {"label": "right index", "added": 0.0}


def test_rename_preserves_added_timestamp(tmp_path, monkeypatch):
    """Renaming an already-labeled slot keeps its original `added` value —
    only the label text changes."""
    from dashtouch_helper import webui
    monkeypatch.setattr(webui, "LABELS_PATH", tmp_path / "labels.json")
    webui.save_label(3, "right index")
    original = json.loads((tmp_path / "labels.json").read_text())["3"]["added"]

    d = FakeDaemon()
    url = webui.start(d, port=0)
    host, port = url.split("//")[1].split("/")[0].split(":")
    token = url.split("token=")[1]
    port = int(port)

    status, _ = req(host, port, "POST", "/api/label",
                    {"slot": 3, "label": "right index finger"}, token=token)
    assert status == 202
    labels = json.loads((tmp_path / "labels.json").read_text())
    assert labels["3"]["label"] == "right index finger"
    assert labels["3"]["added"] == original


def test_enrolled_but_unlabeled_slot_still_appears_in_status(tmp_path, monkeypatch):
    """A slot enrolled outside the page (e.g. over serial) has no
    labels.json entry at all, but must still show up via slots_used so the
    page can render it as an "Unnamed" tile."""
    from dashtouch_helper import webui
    monkeypatch.setattr(webui, "LABELS_PATH", tmp_path / "labels.json")
    webui.save_label(1, "thumb")
    d = FakeDaemon()
    d.state["slots_used"] = [1, 7]  # slot 7 has no label entry
    url = webui.start(d, port=0)
    host, port = url.split("//")[1].split("/")[0].split(":")
    port = int(port)

    status, body = req(host, port, "GET", "/api/status")
    assert status == 200
    assert body["slots_used"] == [1, 7]
    assert "7" not in body["slots"]
    assert body["slots"]["1"]["label"] == "thumb"
