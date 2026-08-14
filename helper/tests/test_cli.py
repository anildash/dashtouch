import argparse
import pathlib
from unittest import mock

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
    webui.URL_PATH.write_text("http://127.0.0.1:3274/?token=abc\n")
    opened = []
    monkeypatch.setattr(cli.webbrowser, "open", lambda u: opened.append(u))
    assert cli.cmd_enroll(None) == 0
    assert opened == ["http://127.0.0.1:3274/?token=abc"]


def test_enroll_without_daemon_fails_friendly(tmp_path, monkeypatch, capsys):
    from dashtouch_helper import webui
    monkeypatch.setattr(webui, "URL_PATH", tmp_path / "missing")
    assert cli.cmd_enroll(None) == 1


# -- Task 7j: `dashtouch password` ---------------------------------------

def test_password_writes_only_password_entry(monkeypatch):
    monkeypatch.setattr(cli.getpass, "getpass", lambda *_: "newpw")
    set_password = mock.Mock()
    set_pairing = mock.Mock()
    monkeypatch.setattr(cli.keychain, "set_password", set_password)
    monkeypatch.setattr(cli.keychain, "set_pairing_key", set_pairing)

    args = argparse.Namespace(serial=None, password=None)
    assert cli.cmd_password(args) == 0

    set_password.assert_called_once_with(cli.daemon_mod.DEFAULT_SERIAL, "newpw")
    set_pairing.assert_not_called()


def test_password_rejects_argv_password(capsys):
    args = argparse.Namespace(serial=None, password="hunter2")
    assert cli.cmd_password(args) == 1
    out = capsys.readouterr().out
    assert "hunter2" not in out


def test_password_mismatch_reprompts_then_succeeds(monkeypatch):
    answers = iter(["one", "two", "three", "three"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda *_: next(answers))
    set_password = mock.Mock()
    monkeypatch.setattr(cli.keychain, "set_password", set_password)

    args = argparse.Namespace(serial=None, password=None)
    assert cli.cmd_password(args) == 0
    set_password.assert_called_once_with(cli.daemon_mod.DEFAULT_SERIAL, "three")


def test_password_gives_up_after_three_mismatches(monkeypatch):
    monkeypatch.setattr(cli.getpass, "getpass",
                        mock.Mock(side_effect=["a", "b", "c", "d", "e", "f"]))
    set_password = mock.Mock()
    monkeypatch.setattr(cli.keychain, "set_password", set_password)

    args = argparse.Namespace(serial=None, password=None)
    assert cli.cmd_password(args) == 1
    set_password.assert_not_called()


# -- Task 7j: `dashtouch pairing` -----------------------------------------

def test_pairing_writes_keychain_and_secrets_file(tmp_path, monkeypatch):
    secrets_path = tmp_path / "secrets.h"
    monkeypatch.setattr(cli, "SECRETS_PATH", secrets_path)
    monkeypatch.setattr("builtins.input", lambda *_: "y")
    set_pairing = mock.Mock()
    monkeypatch.setattr(cli.keychain, "set_pairing_key", set_pairing)
    monkeypatch.setattr(cli, "find_and_flash", lambda *_: "not_found")

    args = argparse.Namespace(serial=None)
    assert cli.cmd_pairing(args) == 0

    set_pairing.assert_called_once()
    assert set_pairing.call_args[0][0] == cli.daemon_mod.DEFAULT_SERIAL
    assert secrets_path.exists()
    assert "PAIRING_KEY[32]" in secrets_path.read_text()


def test_pairing_declining_confirmation_writes_nothing(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "n")
    set_pairing = mock.Mock()
    monkeypatch.setattr(cli.keychain, "set_pairing_key", set_pairing)

    args = argparse.Namespace(serial=None)
    assert cli.cmd_pairing(args) == 0
    set_pairing.assert_not_called()


def test_pairing_does_not_flash_when_declined(tmp_path, monkeypatch):
    secrets_path = tmp_path / "secrets.h"
    monkeypatch.setattr(cli, "SECRETS_PATH", secrets_path)
    # First prompt: confirm the rotation. Second prompt (inside find_and_flash):
    # decline the flash offer.
    answers = iter(["y", "n"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    monkeypatch.setattr(cli.keychain, "set_pairing_key", mock.Mock())
    monkeypatch.setattr(cli.serial_link, "find_port", lambda: "/dev/cu.usbmodem1")
    monkeypatch.setattr(cli.shutil, "which", lambda _: "/usr/local/bin/arduino-cli")
    run = mock.Mock()
    monkeypatch.setattr(cli.subprocess, "run", run)

    args = argparse.Namespace(serial=None)
    assert cli.cmd_pairing(args) == 0
    run.assert_not_called()
