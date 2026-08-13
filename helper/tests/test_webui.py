import http.client
import json
import time
from types import SimpleNamespace

from dashtouch_helper import webui


class FakeDaemon:
    def __init__(self):
        self.state = {"connected": True, "sensor": "ok", "fw": "dt-0.1.0",
                      "enroll_stage": "", "last_line": ""}
        self.sent = []

    def send_command(self, line):
        self.sent.append(line)


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
