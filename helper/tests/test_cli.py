import pathlib

from dashtouch_helper import cli


def test_write_secrets_renders_key_bytes(tmp_path):
    key = bytes(range(32))
    path = tmp_path / "secrets.h"
    cli.write_secrets(key, path)
    text = path.read_text()
    assert "0x00, 0x01" in text and "0x1f" in text
    assert text.count("0x") == 32
    assert "PAIRING_KEY[32]" in text


def test_render_plist_substitutes_paths():
    out = cli.render_plist("/usr/bin/python3", "/tmp/wd")
    assert "/usr/bin/python3" in out
    assert "com.dashtouch.helper" in out
    assert "/tmp/wd" in out


def test_enroll_uses_persisted_url(tmp_path, monkeypatch):
    from dashtouch_helper import webui
    monkeypatch.setattr(webui, "URL_PATH", tmp_path / "webui-url")
    webui.URL_PATH.write_text("http://127.0.0.1:8737/?token=abc\n")
    opened = []
    monkeypatch.setattr(cli.webbrowser, "open", lambda u: opened.append(u))
    assert cli.cmd_enroll(None) == 0
    assert opened == ["http://127.0.0.1:8737/?token=abc"]


def test_enroll_without_daemon_fails_friendly(tmp_path, monkeypatch, capsys):
    from dashtouch_helper import webui
    monkeypatch.setattr(webui, "URL_PATH", tmp_path / "missing")
    assert cli.cmd_enroll(None) == 1
