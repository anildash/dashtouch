"""Localhost web UI. 127.0.0.1 only; mutating routes need the session
token, so a random browser tab can't quietly enroll a finger."""
from __future__ import annotations

import json
import pathlib
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WEB_ROOT = pathlib.Path(__file__).parents[1] / "web"
LABELS_PATH = pathlib.Path.home() / ".dashtouch" / "labels.json"
URL_PATH = pathlib.Path.home() / ".dashtouch" / "webui-url"

_TOKEN = secrets.token_urlsafe(24)
_labels_lock = threading.Lock()


def _load_labels() -> dict:
    try:
        return json.loads(LABELS_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_labels(labels: dict) -> None:
    LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LABELS_PATH.write_text(json.dumps(labels, indent=2) + "\n")


def _make_handler(daemon):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, status, obj):
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _static(self, name, ctype):
            try:
                body = (WEB_ROOT / name).read_bytes()
            except FileNotFoundError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                self._static("index.html", "text/html")
            elif path == "/app.js":
                self._static("app.js", "text/javascript")
            elif path == "/style.css":
                self._static("style.css", "text/css")
            elif path == "/api/status":
                st = dict(daemon.state)
                st["slots"] = _load_labels()
                self._json(200, st)
            elif path == "/api/log":
                if not secrets.compare_digest(self.headers.get("X-DT-Token") or "", _TOKEN):
                    self._json(403, {"error": "bad token"})
                    return
                with daemon._events_lock:
                    events = list(daemon.events)
                self._json(200, {"events": events})
            else:
                self.send_error(404)

        def do_POST(self):
            if not secrets.compare_digest(self.headers.get("X-DT-Token") or "", _TOKEN):
                daemon.log_event("web", "rejected: bad token")
                self._json(403, {"error": "bad token"})
                return
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                slot = int(body.get("slot", 0))
            except (ValueError, json.JSONDecodeError, AttributeError):
                daemon.log_event("web", "rejected: bad request")
                self._json(400, {"error": "bad request"})
                return
            if not (1 <= slot <= 200):
                daemon.log_event("web", "rejected: bad request")
                self._json(400, {"error": "slot out of range"})
                return
            with _labels_lock:
                labels = _load_labels()
                if self.path == "/api/enroll":
                    labels[str(slot)] = str(body.get("label", ""))[:64]
                    _save_labels(labels)
                    daemon.state["enroll_stage"] = ""
                    daemon.send_command(f"ENROLL {slot}")
                    daemon.log_event("web", f"enroll slot {slot} accepted")
                    self._json(202, {"ok": True})
                elif self.path == "/api/delete":
                    labels.pop(str(slot), None)
                    _save_labels(labels)
                    daemon.send_command(f"DELETE {slot}")
                    daemon.log_event("web", f"delete slot {slot} accepted")
                    self._json(202, {"ok": True})
                else:
                    self.send_error(404)

    return Handler


def start(daemon, port: int = 8737) -> str:
    server = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(daemon))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    actual = server.server_address[1]
    url = f"http://127.0.0.1:{actual}/?token={_TOKEN}"
    URL_PATH.parent.mkdir(parents=True, exist_ok=True)
    URL_PATH.write_text(url + "\n")
    URL_PATH.chmod(0o600)
    return url
