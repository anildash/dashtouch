import pytest
from dashtouch_helper import webui


@pytest.fixture(autouse=True)
def isolate_dashtouch_home(tmp_path, monkeypatch):
    """Isolate filesystem usage for tests and install a fake keychain module
    that uses the test token file under tmp_path. Tests may still set
    webui.TOKEN_PATH and the fake keychain will read/write that path, so
    per-test monkeypatching of TOKEN_PATH continues to work.
    """
    import sys
    import types

    monkeypatch.setattr(webui, "URL_PATH", tmp_path / "webui-url")
    monkeypatch.setattr(webui, "LABELS_PATH", tmp_path / "labels.json")
    monkeypatch.setattr(webui, "TOKEN_PATH", tmp_path / "token")

    # Create a tiny fake keychain module that reads/writes the file at
    # webui.TOKEN_PATH. Tests that change webui.TOKEN_PATH will affect this
    # fake keychain because it reads webui.TOKEN_PATH at call time.
    fake_kc = types.SimpleNamespace()

    def fake_get_session_token():
        try:
            return webui.TOKEN_PATH.read_text().strip()
        except Exception:
            raise Exception("no token")

    def fake_set_session_token(token):
        webui.TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        webui.TOKEN_PATH.write_text(token + "\n")
        try:
            webui.TOKEN_PATH.chmod(0o600)
        except OSError:
            pass

    fake_kc.get_session_token = fake_get_session_token
    fake_kc.set_session_token = fake_set_session_token
    fake_kc.KeychainError = Exception

    monkeypatch.setitem(sys.modules, 'dashtouch_helper.keychain', fake_kc)
