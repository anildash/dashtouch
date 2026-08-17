"""Localhost web UI. 127.0.0.1 only; mutating routes need the session
token, so a random browser tab can't quietly enroll a finger."""
from __future__ import annotations

import json
import os
import pathlib
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__

WEB_ROOT = pathlib.Path(__file__).parents[1] / "web"
LABELS_PATH = pathlib.Path.home() / ".dashtouch" / "labels.json"
URL_PATH = pathlib.Path.home() / ".dashtouch" / "webui-url"
# NOTE: session tokens are stored in the macOS Keychain in production.
# Tests may still set webui.TOKEN_PATH (see tests/conftest.py) for their
# fake keychain backing; production code does not read/write TOKEN_PATH.
TOKEN_PATH = pathlib.Path.home() / ".dashtouch" / "token"  # retained for tests; production uses Keychain only

# The one and only outbound network call this software ever makes, and only
# when a person clicks the "check for updates" button — see docs/security.md.
# A static file, fetched and compared locally; nothing is sent but the GET.
VERSION_URL = "https://raw.githubusercontent.com/anildash/dashtouch/main/version.json"
UPDATE_CHECK_TIMEOUT = 5.0

_labels_lock = threading.Lock()


def _parse_version(version: str) -> tuple:
    """Dot-separated numeric parts as a tuple of ints, so 0.10.0 > 0.9.0
    (plain string comparison gets that backwards). Raises ValueError on
    anything that isn't all-numeric parts."""
    parts = str(version).strip().split(".")
    if not parts:
        raise ValueError("empty version")
    return tuple(int(p) for p in parts)


def compare_versions(a: str, b: str) -> int:
    """-1 if a < b, 0 if equal, 1 if a > b — tuple-of-ints comparison, not
    string comparison."""
    ta, tb = _parse_version(a), _parse_version(b)
    if ta < tb:
        return -1
    if ta > tb:
        return 1
    return 0


def check_update(current_version: str = __version__, url: str = VERSION_URL,
                  timeout: float = UPDATE_CHECK_TIMEOUT) -> dict:
    """Fetch version.json from GitHub and compare it to the running
    version. Never raises — every failure mode (offline, DNS, timeout, bad
    JSON, non-200, malformed version) collapses to a friendly
    {"checked": False, "error": ...} instead of propagating."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dashtouch-helper"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except Exception:
        # Offline, DNS failure, timeout, connection reset, TLS error — all
        # collapse to the same friendly reason. Never crash the daemon.
        return {"checked": False, "error": "Couldn't reach GitHub just now."}

    try:
        data = json.loads(raw)
        latest = str(data["version"])
        update_available = compare_versions(latest, current_version) > 0
    except Exception:
        return {"checked": False, "error": "Got something unexpected back from GitHub."}

    # version.json is fetched over the network; its "url" field is remote
    # content rendered as a link on the token-bearing page. escapeHtml on
    # the client only neutralizes & < > " — a "javascript:" URL survives
    # that and would execute. Reject anything that isn't a plain http(s)
    # link here, server-side, rather than trusting the client alone.
    release_url = str(data.get("url", ""))
    if not (release_url.startswith("https://") or release_url.startswith("http://")):
        release_url = ""

    return {
        "checked": True,
        "current": current_version,
        "latest": latest,
        "update_available": update_available,
        "security": bool(data.get("security", False)),
        "headline": str(data.get("headline", "")),
        "url": release_url,
    }


def _normalize_entry(value) -> dict:
    """A bare string (the old labels.json format) becomes an object with
    added=0.0, so legacy entries sort to the front, oldest-first."""
    if isinstance(value, dict):
        return {"label": str(value.get("label", "")), "added": float(value.get("added", 0.0) or 0.0)}
    return {"label": str(value), "added": 0.0}


def _load_labels() -> dict:
    """Tolerant of the old slot->string format; always returns the object
    form {"label": str, "added": float} so callers never branch on shape."""
    try:
        raw = json.loads(LABELS_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: _normalize_entry(v) for k, v in raw.items()}


def _save_labels(labels: dict) -> None:
    LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LABELS_PATH.write_text(json.dumps(labels, indent=2) + "\n")


def save_label(slot: int, label: str) -> None:
    """Save a label for a slot (called by daemon on ENROLL_OK, and by
    /api/label endpoint). Preserves the entry's original `added` timestamp
    on rename; sets it fresh only when the entry is first created."""
    with _labels_lock:
        labels = _load_labels()
        existing = labels.get(str(slot))
        added = existing["added"] if existing else time.time()
        labels[str(slot)] = {"label": label, "added": added}
        _save_labels(labels)


def prune_labels(allowed_slots: set) -> int:
    """Remove labels for slots not in allowed_slots. Returns count of pruned labels."""
    with _labels_lock:
        labels = _load_labels()
        before_count = len(labels)
        # Keep only labels whose slot (as int) is in allowed_slots
        labels = {k: v for k, v in labels.items()
                  if int(k) in allowed_slots}
        _save_labels(labels)
        return before_count - len(labels)


def _make_handler(daemon, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, status, obj):
            body = json.dumps(obj).encode()
            self.send_response(status)
            # Security headers: CSP limits where resources can be loaded from,
            # X-Frame-Options prevents embedding, Referrer-Policy avoids leaking
            # the local URL in Referer headers, and nosniff stops MIME sniffing.
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none';")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
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
            # Same security headers on static responses.
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none';")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _host_allowed(self):
            """Reject any request whose Host header isn't the loopback origin
            we're actually serving on.

            Binding to 127.0.0.1 stops remote *packets*, not remote *pages*.
            A site on the public internet can point a hostname it controls at
            127.0.0.1 (DNS rebinding); the browser then treats
            http://evil.example:3274 as same-origin with us, which is enough
            to GET /api/token and use it to drive the mutating routes. The
            token can't defend against that on its own — /api/token hands it
            to anything the browser considers same-origin. The Host header is
            what distinguishes the two cases: a real local page sends the
            literal loopback address, a rebound one sends its own name."""
            host = (self.headers.get("Host") or "").lower()
            port = self.server.server_address[1]
            return host in (f"127.0.0.1:{port}", f"localhost:{port}")

        def do_GET(self):
            if not self._host_allowed():
                self._json(403, {"error": "bad host"})
                return
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
                st["health"] = daemon.health()
                st["last_update_check"] = getattr(daemon, "last_update_check", None)
                self._json(200, st)
            elif path == "/api/log":
                if not secrets.compare_digest(self.headers.get("X-DT-Token") or "", token):
                    self._json(403, {"error": "bad token"})
                    return
                with daemon._events_lock:
                    events = list(daemon.events)
                self._json(200, {"events": events})
            elif path == "/api/token":
                # The page fetches its token here, since the URL no longer
                # carries one. Two things keep this from being a giveaway:
                # no CORS headers, so an ordinary cross-origin page can't read
                # the response, and the Host check above, which is what closes
                # the DNS-rebinding path around same-origin policy.
                self._json(200, {"token": token})
            else:
                self.send_error(404)

        def do_POST(self):
            if not self._host_allowed():
                daemon.log_event("web", "rejected: bad host")
                self._json(403, {"error": "bad host"})
                return
            if not secrets.compare_digest(self.headers.get("X-DT-Token") or "", token):
                daemon.log_event("web", "rejected: bad token")
                self._json(403, {"error": "bad token"})
                return

            if self.path == "/api/check-update":
                # Token-gated like the other mutating routes: it causes a
                # network request, so it isn't a plain GET. This is the one
                # code path in the whole product that talks to the
                # internet, and only because someone just clicked a button.
                result = check_update(__version__)
                daemon.last_update_check = result
                if result.get("checked"):
                    daemon.log_event("helper",
                        f"update check: current={result['current']} "
                        f"latest={result['latest']} "
                        f"available={result['update_available']}")
                else:
                    daemon.log_event("helper", f"update check failed: {result.get('error')}")
                self._json(200, result)
                return

            if self.path == "/api/pause":
                # Token-gated like every other mutating route. Sent while a
                # naming/renaming field is focused, so the device stops
                # matching and can't type a password into a text box. See
                # docs/protocol.md (PAUSE) and docs/security.md.
                try:
                    n = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(n) or b"{}")
                    paused = body["paused"]
                except (ValueError, json.JSONDecodeError, AttributeError,
                        TypeError, KeyError):
                    daemon.log_event("web", "rejected: bad request")
                    self._json(400, {"error": "bad request"})
                    return
                if not isinstance(paused, bool):
                    daemon.log_event("web", "rejected: bad paused value")
                    self._json(400, {"error": "paused must be a boolean"})
                    return

                daemon.send_command(f"PAUSE {1 if paused else 0}")
                daemon.log_event("web", f"pause: set to {paused}")
                self._json(202, {"ok": True})
                return

            if self.path == "/api/settings":
                try:
                    n = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(n) or b"{}")
                    key = body["key"]
                    raw_value = body["value"]
                except (ValueError, json.JSONDecodeError, AttributeError,
                        TypeError, KeyError):
                    daemon.log_event("web", "rejected: bad request")
                    self._json(400, {"error": "bad request"})
                    return

                if key == "idle_color":
                    try:
                        n_val = int(raw_value)
                    except (TypeError, ValueError):
                        n_val = None
                    if n_val is None or not (0 <= n_val <= 7):
                        daemon.log_event("web", "rejected: bad idle_color")
                        self._json(400, {"error": "idle_color must be 0-7"})
                        return
                elif key == "idle_style":
                    try:
                        n_val = int(raw_value)
                    except (TypeError, ValueError):
                        n_val = None
                    if n_val is None or not (1 <= n_val <= 2):
                        daemon.log_event("web", "rejected: bad idle_style")
                        self._json(400, {"error": "idle_style must be 1-2"})
                        return
                elif key == "press_enter":
                    n_val = 1 if raw_value in (True, 1, "1") else 0
                elif key == "fp_swap":
                    n_val = 1 if raw_value in (True, 1, "1") else 0
                else:
                    daemon.log_event("web", f"rejected: unknown settings key '{key}'")
                    self._json(400, {"error": "unknown key"})
                    return

                daemon.send_command(f"SET {key} {n_val}")
                daemon.log_event("web", f"settings: set {key} to {n_val}")
                self._json(202, {"ok": True})
                return

            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                slot = int(body.get("slot", 0))
            except (ValueError, json.JSONDecodeError, AttributeError, TypeError):
                daemon.log_event("web", "rejected: bad request")
                self._json(400, {"error": "bad request"})
                return
            if not (1 <= slot <= 200):
                daemon.log_event("web", "rejected: bad request")
                self._json(400, {"error": "slot out of range"})
                return

            if self.path == "/api/label":
                # Rename endpoint: update label immediately (no sensor change)
                label_text = str(body.get("label", ""))[:64]
                save_label(slot, label_text)
                daemon.log_event("web", f"renamed slot {slot} to '{label_text}'")
                self._json(202, {"ok": True})
            else:
                with _labels_lock:
                    labels = _load_labels()
                    if self.path == "/api/enroll":
                        # Store pending_label; commit only on ENROLL_OK
                        label_text = str(body.get("label", ""))[:64]
                        daemon.pending_label = {"slot": slot, "label": label_text}
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


def _probe_helper_alive(url: str, timeout: float = 1.0) -> bool:
    """Best-effort check that some other process is actually answering at
    the origin encoded in `url` (as saved in webui-url). GETs /api/status
    with a short timeout, stdlib only. Any response at all — including a
    non-2xx one — counts as "alive": we only care whether something is
    listening and speaking HTTP, not whether it's happy. Any failure
    (refused, timeout, DNS, garbage URL) means "not alive"."""
    try:
        parsed = urllib.parse.urlsplit(url)
        if not parsed.netloc:
            return False
        status_url = f"{parsed.scheme}://{parsed.netloc}/api/status"
        req = urllib.request.Request(status_url, headers={"User-Agent": "dashtouch-helper"})
        with urllib.request.urlopen(req, timeout=timeout):
            pass
        return True
    except Exception:
        return False


def start(daemon, port: int = 3274) -> str:
    # Allow env override: DASHTOUCH_PORT
    if port == 3274:  # if using the default, check env
        env_port = os.environ.get("DASHTOUCH_PORT", "").strip()
        if env_port:
            try:
                port = int(env_port)
            except ValueError:
                # Invalid env value: ignore, use default
                pass
    # Reuse existing token from the macOS Keychain if available; otherwise
    # generate a fresh one. In production we store the token only in Keychain
    # (no on-disk token file) to avoid leaking it via the filesystem.
    token = None
    # Production: always use the macOS Keychain as the persistent
    # storage for the session token. If Keychain access fails, keep the
    # token in memory for the running process but do not persist to disk.
    try:
        from . import keychain
        try:
            existing = keychain.get_session_token()
        except Exception:
            existing = None
        if existing and len(existing) >= 16:
            token = existing
    except Exception:
        # Keychain import failed (non-macOS environment) — do not persist to disk.
        existing = None

    token_freshly_generated = token is None
    if token is None:
        token = secrets.token_urlsafe(24)

    # Create handler with captured token
    Handler = _make_handler(daemon, token)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        # Port is busy — almost always because another Dashboard Touch
        # helper is already running. Fall back to an ephemeral port; the
        # link-file check below decides whether we get to publish it.
        msg = (f"port {port} was busy — another Dashboard Touch helper is "
               "probably already running; this instance moved to an ephemeral port")
        daemon.log_event("helper", msg)
        print(msg)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)

    threading.Thread(target=server.serve_forever, daemon=True).start()
    actual = server.server_address[1]
    # Publish a token-less URL so the session token is not leaked in the
    # browser address bar, history, or Referer. The page fetches the token
    # from /api/token (same-origin) after it loads. For programmatic callers
    # (and tests) we still return the full token-bearing URL, but the
    # persisted link on disk intentionally omits the token.
    serve_url = f"http://127.0.0.1:{actual}/"
    returned_url = f"http://127.0.0.1:{actual}/?token={token}"

    # Don't blindly overwrite the shared link/token files: if they already
    # point at a DIFFERENT port and something is actually answering there,
    # that's the helper holding the real hardware. Leave its link alone and
    # just keep serving on our own (ephemeral) port.
    other_helper_live = False
    try:
        existing_link = URL_PATH.read_text().strip()
    except (OSError, UnicodeDecodeError):
        existing_link = ""

    if existing_link:
        try:
            existing_port = int(urllib.parse.urlsplit(existing_link).netloc.rsplit(":", 1)[1])
        except (IndexError, ValueError):
            existing_port = None
        if existing_port is not None and existing_port != actual \
                and _probe_helper_alive(existing_link):
            other_helper_live = True
            this_origin = f"http://127.0.0.1:{actual}"
            existing_origin = f"http://127.0.0.1:{existing_port}"
            msg = (f"Another Dashboard Touch helper is already running at "
                   f"{existing_origin}; leaving the saved link pointing there. "
                   f"This instance is at {this_origin}.")
            daemon.log_event("helper", msg)
            print(msg)

    if token_freshly_generated and not other_helper_live:
        # Persist the token to the macOS Keychain. If Keychain write fails,
        # do not persist to disk — keep the new token in memory only.
        try:
            from . import keychain
            try:
                keychain.set_session_token(token)
            except Exception:
                # Can't write to Keychain — intentionally do not persist to disk
                pass
        except Exception:
            # Keychain not available — intentionally keep token in-memory
            pass

    if not other_helper_live:
        URL_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Persist the token-less serve URL so the filesystem/stored link can't
        # leak the session token; return the token-bearing URL to the caller.
        URL_PATH.write_text(serve_url + "\n")
        URL_PATH.chmod(0o600)

    return returned_url
