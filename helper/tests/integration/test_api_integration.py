import http.client
import json
import threading
import time

import pytest
from dashtouch_helper import webui


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
        return [{"id": "device", "label": "Device", "ok": True, "state": "ok", "detail": "Connected", "fix": "help"}]


def start():
    d = FakeDaemon()
    url = webui.start(d, port=0)
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


@pytest.mark.integration
def test_api_token_and_enroll_flow():
    d, host, port, token = start()

    # GET /api/token should return the same token that was embedded in the
    # returned URL for programmatic callers.
    status, body = req(host, port, "GET", "/api/token")
    assert status == 200
    assert body.get("token") == token

    # POST /api/enroll without token should be rejected
    status, _ = req(host, port, "POST", "/api/enroll", {"slot": 1, "label": "x"})
    assert status == 403

    # POST /api/enroll with token should be accepted and send command
    status, _ = req(host, port, "POST", "/api/enroll", {"slot": 2, "label": "right"}, token)
    assert status == 202
    assert d.sent == ["ENROLL 2"]
