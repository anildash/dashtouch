import pytest
from dashtouch_helper import webui


@pytest.fixture(autouse=True)
def isolate_dashtouch_home(tmp_path, monkeypatch):
    """Isolate filesystem usage for tests and install a fake keychain module
    that uses the test token file under tmp_path. Tests may still set
    webui.TOKEN_PATH and the fake keychain will read/write that path, so
    per-test monkeypatching of TOKEN_PATH continues to work.
    """
    import dashtouch_helper.keychain as keychain

    monkeypatch.setattr(webui, "URL_PATH", tmp_path / "webui-url")
    monkeypatch.setattr(webui, "LABELS_PATH", tmp_path / "labels.json")
    monkeypatch.setattr(webui, "TOKEN_PATH", tmp_path / "token")

    # Instead of replacing the keychain module in sys.modules, directly
    # monkeypatch the keychain functions used by the application. This is a
    # more explicit mock and avoids messing with module resolution.
    def fake_get_session_token():
        try:
            return webui.TOKEN_PATH.read_text().strip()
        except Exception:
            # Mirror the KeychainError semantics by raising the module's
            # KeychainError so production code handles it the same way.
            raise keychain.KeychainError("no token")

    def fake_set_session_token(token):
        webui.TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        webui.TOKEN_PATH.write_text(token + "\n")
        try:
            webui.TOKEN_PATH.chmod(0o600)
        except OSError:
            pass

    monkeypatch.setattr(keychain, "get_session_token", fake_get_session_token)
    monkeypatch.setattr(keychain, "set_session_token", fake_set_session_token)

