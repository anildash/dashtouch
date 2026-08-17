import pytest

from dashtouch_helper import webui


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
