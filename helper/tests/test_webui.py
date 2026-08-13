import http.client
import json
import threading
import time
from types import SimpleNamespace

from dashtouch_helper import webui


class FakeDaemon:
    def __init__(self):
        self.state = {"connected": True, "sensor": "ok", "fw": "dt-0.1.0",
                      "enroll_stage": "", "last_line": "", "cap": "200",
                      "slots_used": [1, 3]}
        self.sent = []
        self.events = []
        self._events_lock = threading.Lock()

    def send_command(self, line):
        self.sent.append(line)

    def log_event(self, direction, text):
        self.events.append({"t": time.time(), "dir": direction, "text": text})


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
    labels = json.loads((tmp_path / "labels.json").read_text())
    assert labels["2"] == "right index"


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
