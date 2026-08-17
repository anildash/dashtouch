import subprocess

import pytest

from dashtouch_helper import webui


@pytest.fixture(autouse=True)
def never_touch_the_real_keychain(monkeypatch):
    """Make any test that actually shells out to `security` fail loudly.

    This is not hypothetical. A test that seeded a session token was written
    one commit before the mocking that made it safe, and in that window it
    wrote its fixture string — "seededtoken12345678", a constant sitting in
    a public repo — into a real login Keychain. Nothing failed, nothing was
    logged, and it surfaced only weeks later when a helper read it back and
    started serving it as a live session token.

    The tests that legitimately exercise keychain.py patch `subprocess.run`
    themselves, so they never arrive here. Anything that does arrive here is
    a mocking gap, and the only safe outcome is a loud one. Note this guards
    the real subprocess module, not keychain._run — a gap in how keychain is
    patched is exactly the failure being defended against.
    """
    real_run = subprocess.run

    def guarded_run(args, *a, **kw):
        argv0 = args[0] if isinstance(args, (list, tuple)) and args else args
        if isinstance(argv0, str) and argv0.split("/")[-1] == "security":
            raise AssertionError(
                "a test tried to run the real `security` binary: "
                f"{args!r}\nThis would read or write the developer's actual "
                "login Keychain. Patch subprocess.run (see test_keychain.py) "
                "or the keychain function you're exercising."
            )
        return real_run(args, *a, **kw)

    monkeypatch.setattr(subprocess, "run", guarded_run)


@pytest.fixture(autouse=True)
def isolate_dashtouch_home(tmp_path, monkeypatch):
    """Keep tests off the real ~/.dashtouch and off the real Keychain.

    The session token lives in the macOS Keychain in production. Tests back
    it with a file under tmp_path instead, and they address that file
    through `webui.TOKEN_PATH` so a test can point the fake store somewhere
    of its own (several do, to set up a pre-seeded or unreadable token).

    Only the session-token pair is faked here. `get_password` and
    `get_pairing_key` are left alone: the tests that exercise those patch
    `subprocess.run` themselves, which keeps the real argv-construction and
    read-back logic under test — the part worth testing — while never
    reaching the `security` binary. That also means these tests pass on the
    Linux CI runners, where no such binary exists.
    """
    import dashtouch_helper.keychain as keychain

    monkeypatch.setattr(webui, "URL_PATH", tmp_path / "webui-url")
    monkeypatch.setattr(webui, "LABELS_PATH", tmp_path / "labels.json")
    monkeypatch.setattr(webui, "TOKEN_PATH", tmp_path / "token")

    def fake_get_session_token():
        try:
            return webui.TOKEN_PATH.read_text().strip()
        except Exception as e:
            # Match the real thing's failure mode, so production code takes
            # the same branch it would on a Keychain miss.
            raise keychain.KeychainError("no token") from e

    def fake_set_session_token(token):
        webui.TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        webui.TOKEN_PATH.write_text(token + "\n")
        try:
            webui.TOKEN_PATH.chmod(0o600)
        except OSError:
            pass

    monkeypatch.setattr(keychain, "get_session_token", fake_get_session_token)
    monkeypatch.setattr(keychain, "set_session_token", fake_set_session_token)
