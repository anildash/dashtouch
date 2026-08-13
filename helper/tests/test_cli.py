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
