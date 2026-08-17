"""End-to-end: the CLI talking to a live helper over HTTP.

The unit tests in test_webui.py already drive a real server over real
sockets, so re-testing the HTTP surface here would buy nothing. What isn't
covered anywhere else is the seam *between* the two halves — the helper
mints a session token and stores it in the Keychain, and later a separate
`dashtouch` process reads it back out to authenticate. Nothing in either
half's own tests notices when that handoff breaks.

It has broken: a duplicated `token_freshly_generated = token is None` in
webui.start() left the flag permanently False, so the token was never
written to the Keychain and `dashtouch pins` failed with "Session token
unavailable in Keychain" — while every unit test stayed green.
"""
import threading
import time

import pytest

from dashtouch_helper import cli, webui


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
        return [{"id": "device", "label": "Device", "ok": True,
                 "state": "ok", "detail": "Connected", "fix": "help"}]


@pytest.mark.integration
def test_cli_reaches_live_helper_using_the_stored_session_token(monkeypatch):
    """`dashtouch pins` in miniature: start the helper, then authenticate to
    it from the CLI side using only what the helper left in the Keychain."""
    d = FakeDaemon()
    webui.start(d, port=0)

    # The CLI finds the helper the same way the real command does — via the
    # link the helper persisted — and gets its token from the Keychain, not
    # from anything this test hands it.
    monkeypatch.setattr(cli, "webui", webui)

    status_code, _ = cli._daemon_post_setting("fp_swap", 1)

    assert status_code == 202
    assert d.sent == ["SET fp_swap 1"]


@pytest.mark.integration
def test_cli_fails_clearly_when_no_token_was_ever_stored(monkeypatch):
    """The other half of the seam: if the helper never stored a token, the
    CLI must say so plainly rather than sending an empty header and getting
    an opaque 403 back."""
    from dashtouch_helper import keychain

    d = FakeDaemon()
    webui.start(d, port=0)

    def no_token():
        raise keychain.KeychainError("nothing stored")

    monkeypatch.setattr(keychain, "get_session_token", no_token)

    with pytest.raises(RuntimeError, match="Session token unavailable"):
        cli._daemon_post_setting("fp_swap", 1)
