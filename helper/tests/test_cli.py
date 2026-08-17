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


def test_render_plist_logs_go_under_library_not_shared_tmp(monkeypatch, tmp_path):
    # The launchd log used to sit in shared, world-readable /tmp and carry
    # the tokened web UI URL. It must now live under the user's own
    # Library, same as the plist itself.
    log_dir = tmp_path / "Logs" / "dashtouch"
    monkeypatch.setattr(cli, "LOG_DIR", log_dir)
    out = cli.render_plist("/usr/bin/python3", "/tmp/wd")
    assert str(log_dir / "helper.log") in out
    assert str(log_dir / "helper.err") in out
    assert "/tmp/dashtouch-helper.log" not in out
    assert "{logdir}" not in out


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


# -- Task 8: modern launchctl API -------------------------------------------

def test_install_agent_uses_modern_launchctl_api(tmp_path, monkeypatch):
    """install-agent uses bootstrap/bootout with verification."""
    plist_path = tmp_path / "LaunchAgents" / "com.dashtouch.helper.plist"
    monkeypatch.setattr(cli, "PLIST_PATH", plist_path)
    monkeypatch.setattr(cli, "LOG_DIR", tmp_path / "Logs" / "dashtouch")
    monkeypatch.setattr(cli, "REPO", tmp_path / "repo")

    run_calls = []
    def mock_run(cmd, **kwargs):
        run_calls.append((cmd, kwargs))
        # bootout (first call, when not loaded): exit 1
        if cmd[0:3] == ["launchctl", "bootout", "gui/501/com.dashtouch.helper"]:
            if len(run_calls) == 1:
                return mock.Mock(returncode=1)
        # bootstrap (second call): exit 0
        if cmd[0:2] == ["launchctl", "bootstrap", "gui/501"]:
            return mock.Mock(returncode=0)
        # print (third call): exit 0, verify it's there
        if cmd[0:2] == ["launchctl", "print", "gui/501/com.dashtouch.helper"]:
            return mock.Mock(returncode=0)
        return mock.Mock(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", mock_run)
    monkeypatch.setattr(cli.os, "getuid", lambda: 501)

    args = argparse.Namespace(serial=None)
    assert cli.cmd_install_agent(args) == 0

    # Verify the sequence: bootout, bootstrap, print
    assert len(run_calls) >= 3
    assert run_calls[0][0][1] == "bootout"  # First call is bootout
    assert run_calls[1][0][1] == "bootstrap"  # Second call is bootstrap
    assert run_calls[2][0][1] == "print"  # Third call is print (verify)


def test_install_agent_fails_if_bootstrap_fails(tmp_path, monkeypatch):
    """install-agent returns 1 if bootstrap fails."""
    plist_path = tmp_path / "LaunchAgents" / "com.dashtouch.helper.plist"
    monkeypatch.setattr(cli, "PLIST_PATH", plist_path)
    monkeypatch.setattr(cli, "LOG_DIR", tmp_path / "Logs" / "dashtouch")
    monkeypatch.setattr(cli, "REPO", tmp_path / "repo")

    def mock_run(cmd, **kwargs):
        if cmd[0:2] == ["launchctl", "bootstrap"]:
            raise cli.subprocess.CalledProcessError(1, cmd, stderr="Permission denied")
        return mock.Mock(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", mock_run)
    monkeypatch.setattr(cli.os, "getuid", lambda: 501)

    args = argparse.Namespace(serial=None)
    assert cli.cmd_install_agent(args) == 1


def test_install_agent_fails_if_verification_fails(tmp_path, monkeypatch):
    """install-agent returns 1 if launchctl print fails (not registered)."""
    plist_path = tmp_path / "LaunchAgents" / "com.dashtouch.helper.plist"
    monkeypatch.setattr(cli, "PLIST_PATH", plist_path)
    monkeypatch.setattr(cli, "LOG_DIR", tmp_path / "Logs" / "dashtouch")
    monkeypatch.setattr(cli, "REPO", tmp_path / "repo")

    def mock_run(cmd, **kwargs):
        if cmd[0:2] == ["launchctl", "print"]:
            # Verification fails: agent not registered
            return mock.Mock(returncode=1)
        return mock.Mock(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", mock_run)
    monkeypatch.setattr(cli.os, "getuid", lambda: 501)

    args = argparse.Namespace(serial=None)
    assert cli.cmd_install_agent(args) == 1


def test_uninstall_agent_boots_out_and_verifies(monkeypatch):
    """uninstall-agent uses bootout and confirms removal."""
    calls = []
    def mock_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0:2] == ["launchctl", "bootout"]:
            return mock.Mock(returncode=0)
        if cmd[0:2] == ["launchctl", "print"]:
            # After bootout, print should fail (agent is gone)
            return mock.Mock(returncode=1)
        return mock.Mock(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", mock_run)
    monkeypatch.setattr(cli.os, "getuid", lambda: 501)

    args = argparse.Namespace(serial=None)
    assert cli.cmd_uninstall_agent(args) == 0

    # Should have called bootout and print
    assert len(calls) >= 2
    assert calls[0][1] == "bootout"


# -- Task 7n: `dashtouch pins` --------------------------------------------

def _pins_args(swap=False, normal=False):
    return argparse.Namespace(swap=swap, normal=normal)


def test_pins_no_args_reports_default_orientation(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_daemon_status",
                        lambda: {"settings": {"fp_swap": False}})
    assert cli.cmd_pins(_pins_args()) == 0
    out = capsys.readouterr().out
    assert "default" in out.lower()
    assert "SWAPPED" not in out


def test_pins_no_args_reports_swapped_orientation(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_daemon_status",
                        lambda: {"settings": {"fp_swap": True}})
    assert cli.cmd_pins(_pins_args()) == 0
    out = capsys.readouterr().out
    assert "SWAPPED" in out


def test_pins_no_args_helper_not_running(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_daemon_status", lambda: None)
    assert cli.cmd_pins(_pins_args()) == 1
    out = capsys.readouterr().out
    assert "isn't running" in out
    assert "dashtouch run" in out


def test_pins_no_args_settings_not_seen_yet(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_daemon_status", lambda: {"settings": None})
    assert cli.cmd_pins(_pins_args()) == 1
    out = capsys.readouterr().out
    assert "try again" in out.lower()


def test_pins_swap_and_normal_together_rejected(capsys):
    assert cli.cmd_pins(_pins_args(swap=True, normal=True)) == 1
    out = capsys.readouterr().out
    assert "not both" in out.lower()


def test_pins_swap_sends_fp_swap_1_and_asks_for_a_power_cycle(monkeypatch, capsys):
    # The firmware can't verify a live pin-orientation change (real
    # hardware testing showed in-place UART re-init is unreliable and can
    # report success falsely) — so the CLI must not poll /api/status and
    # claim a verdict. It should just say what's actually true: a
    # power-cycle is needed before the new orientation can be trusted.
    monkeypatch.setattr(cli, "_daemon_post_setting", lambda key, value: (202, {"ok": True}))
    status_calls = []
    monkeypatch.setattr(cli, "_daemon_status", lambda: status_calls.append(1))
    assert cli.cmd_pins(_pins_args(swap=True)) == 0
    out = capsys.readouterr().out
    assert "swapped" in out.lower()
    assert "power-cycle" in out.lower()
    assert not status_calls  # no live verification attempted


def test_pins_normal_sends_fp_swap_0(monkeypatch, capsys):
    sent = []
    monkeypatch.setattr(cli, "_daemon_post_setting",
                        lambda key, value: sent.append((key, value)) or (202, {"ok": True}))
    assert cli.cmd_pins(_pins_args(normal=True)) == 0
    assert sent == [("fp_swap", 0)]
    out = capsys.readouterr().out
    assert "power-cycle" in out.lower()


def test_pins_swap_rejected_by_helper(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_daemon_post_setting",
                        lambda key, value: (400, {"error": "bad request"}))
    assert cli.cmd_pins(_pins_args(swap=True)) == 1
    out = capsys.readouterr().out
    assert "bad request" in out


def test_pins_swap_cannot_reach_helper(monkeypatch, capsys):
    def raise_it(key, value):
        raise OSError("connection refused")
    monkeypatch.setattr(cli, "_daemon_post_setting", raise_it)
    assert cli.cmd_pins(_pins_args(swap=True)) == 1
    out = capsys.readouterr().out
    assert "couldn't reach the helper" in out.lower()


def test_daemon_base_url_strips_token(tmp_path, monkeypatch):
    from dashtouch_helper import webui
    monkeypatch.setattr(webui, "URL_PATH", tmp_path / "webui-url")
    webui.URL_PATH.write_text("http://127.0.0.1:3274/?token=abc\n")
    assert cli._daemon_base_url() == "http://127.0.0.1:3274/"


def test_daemon_base_url_missing_file(tmp_path, monkeypatch):
    from dashtouch_helper import webui
    monkeypatch.setattr(webui, "URL_PATH", tmp_path / "missing")
    assert cli._daemon_base_url() is None


def test_bare_dashtouch_prints_the_url(tmp_path, monkeypatch, capsys):
    from dashtouch_helper import webui
    monkeypatch.setattr(webui, "URL_PATH", tmp_path / "webui-url")
    webui.URL_PATH.write_text("http://127.0.0.1:3274/?token=abc123\n")
    assert cli.cmd_where(None) == 0
    assert capsys.readouterr().out.strip() == "http://127.0.0.1:3274/?token=abc123"


def test_bare_dashtouch_without_helper_explains(tmp_path, monkeypatch, capsys):
    from dashtouch_helper import webui
    monkeypatch.setattr(webui, "URL_PATH", tmp_path / "missing")
    assert cli.cmd_where(None) == 1
    out = capsys.readouterr().out
    assert "isn't running" in out and "dashtouch run" in out


def test_bare_dashtouch_survives_a_corrupt_url_file(tmp_path, monkeypatch, capsys):
    from dashtouch_helper import webui
    monkeypatch.setattr(webui, "URL_PATH", tmp_path / "webui-url")
    webui.URL_PATH.write_bytes(b"\xff\xfe")
    assert cli.cmd_where(None) == 1
    assert "isn't running" in capsys.readouterr().out


def _flashable(monkeypatch, ports=("/dev/cu.usbmodem1",)):
    """Common stubs so find_and_flash gets as far as the flash itself."""
    seq = iter(ports)
    last = [ports[-1]]

    def next_port():
        try:
            return next(seq)
        except StopIteration:
            return last[0]

    monkeypatch.setattr(cli.serial_link, "find_port", next_port)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr("builtins.input", lambda *_: "y")


def test_find_and_flash_stops_the_agent_before_flashing_and_restarts_it(monkeypatch):
    # The launch agent holds the serial port open, so flashing over a live
    # one fails with "Resource busy". Order matters: stop, flash, restart.
    _flashable(monkeypatch)
    calls = []
    monkeypatch.setattr(cli, "agent_is_loaded", lambda: True)
    monkeypatch.setattr(cli, "stop_agent", lambda: calls.append("stop"))
    monkeypatch.setattr(cli, "start_agent", lambda: calls.append("start") or True)
    monkeypatch.setattr(cli, "wait_for_port_free", lambda port, **kw: [])
    monkeypatch.setattr(cli.subprocess, "run",
                        lambda *a, **k: calls.append("arduino-cli"))

    assert cli.find_and_flash() == "flashed"
    assert calls == ["stop", "arduino-cli", "arduino-cli", "start"]


def test_find_and_flash_leaves_launchd_alone_when_no_agent_installed(monkeypatch):
    _flashable(monkeypatch)
    touched = []
    monkeypatch.setattr(cli, "agent_is_loaded", lambda: False)
    monkeypatch.setattr(cli, "stop_agent", lambda: touched.append("stop"))
    monkeypatch.setattr(cli, "start_agent", lambda: touched.append("start") or True)
    monkeypatch.setattr(cli, "wait_for_port_free", lambda port, **kw: [])
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: None)

    assert cli.find_and_flash() == "flashed"
    assert touched == []


def test_find_and_flash_names_whoever_still_holds_the_port(monkeypatch, capsys):
    # A hand-started `dashtouch run` can't be stopped for the user, but
    # naming it beats esptool's bare "Resource busy".
    _flashable(monkeypatch)
    monkeypatch.setattr(cli, "agent_is_loaded", lambda: True)
    monkeypatch.setattr(cli, "stop_agent", lambda: None)
    restarted = []
    monkeypatch.setattr(cli, "start_agent", lambda: restarted.append(True) or True)
    monkeypatch.setattr(cli, "wait_for_port_free",
                        lambda port, **kw: [(4242, ".venv/bin/dashtouch run")])
    ran = []
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: ran.append(a))

    assert cli.find_and_flash() == "failed"
    assert ran == []            # never attempted the flash
    assert restarted == [True]  # agent still put back on the failure path
    out = capsys.readouterr().out
    assert "4242" in out and "dashtouch run" in out


def test_find_and_flash_redetects_the_port_after_the_helper_lets_go(monkeypatch):
    # Releasing the port drops DTR, which can reset the board onto a new
    # device node. Flashing the pre-release name then hits a port that no
    # longer exists.
    _flashable(monkeypatch, ports=("/dev/cu.usbmodem83402", "/dev/cu.usbmodem83401"))
    monkeypatch.setattr(cli, "agent_is_loaded", lambda: False)
    monkeypatch.setattr(cli, "wait_for_port_free", lambda port, **kw: [])
    captured = []
    monkeypatch.setattr(cli.subprocess, "run", lambda a, **k: captured.append(a))

    assert cli.find_and_flash() == "flashed"
    upload = [c for c in captured if "upload" in c][0]
    assert "/dev/cu.usbmodem83401" in upload
    assert "/dev/cu.usbmodem83402" not in upload
