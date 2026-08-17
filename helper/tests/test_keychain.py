import subprocess
from unittest import mock

import pytest

from dashtouch_helper import keychain


def ok(stdout=""):
    return subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")


def writes_then_reads(value):
    """subprocess.run stub for a healthy Keychain: the add succeeds and the
    read-back returns exactly what was written."""
    def run(args, *a, **kw):
        if args[1] == "add-generic-password":
            return ok()
        return ok(value + "\n")
    return run


def test_set_password_calls_security_add():
    with mock.patch("subprocess.run", side_effect=writes_then_reads("pw")) as run:
        keychain.set_password("SER1", "pw")
    args = run.call_args_list[0][0][0]
    kwargs = run.call_args_list[0][1]
    assert args[:2] == ["security", "add-generic-password"]
    assert "DashboardTouch" in args and "SER1" in args
    # The secret must never appear on the command line — only piped in via
    # stdin. "-w" is the last argument, with no value after it.
    assert args[-1] == "-w"
    assert "pw" not in args
    # security reads twice (password + retype confirmation) when -w is
    # given no argv value, so both copies go over stdin.
    assert kwargs.get("input") == "pw\npw\n"


def test_set_detaches_from_the_controlling_terminal():
    # security uses readpassphrase(), which prefers /dev/tty over stdin when
    # a controlling terminal exists. Run interactively without detaching and
    # it prompts the operator and stores their keystrokes instead of the
    # generated key — silently, and invisibly to tests, which have no TTY.
    with mock.patch("subprocess.run", side_effect=writes_then_reads("pw")) as run:
        keychain.set_password("SER1", "pw")
    write_kwargs = run.call_args_list[0][1]
    assert write_kwargs.get("start_new_session") is True


def test_set_raises_when_the_value_does_not_read_back():
    # The failure this guards against stored a 9-character shell input as a
    # 32-byte pairing key and only surfaced later as "the gadget and this
    # Mac disagree".
    def wrote_something_else(args, *a, **kw):
        if args[1] == "add-generic-password":
            return ok()
        return ok("something else\n")

    with mock.patch("subprocess.run", side_effect=wrote_something_else):
        with pytest.raises(keychain.KeychainError, match="read back"):
            keychain.set_password("SER1", "pw")


def test_get_password_parses_stdout():
    with mock.patch("subprocess.run", return_value=ok("pw\n")):
        assert keychain.get_password("SER1") == "pw"


def test_get_password_missing_raises():
    err = subprocess.CalledProcessError(44, ["security"], stderr="not found")
    with mock.patch("subprocess.run", side_effect=err):
        with pytest.raises(keychain.KeychainError):
            keychain.get_password("SER1")


def test_pairing_key_roundtrips_hex():
    key = bytes(range(32))
    with mock.patch("subprocess.run", side_effect=writes_then_reads(key.hex())) as run:
        keychain.set_pairing_key("SER1", key)
    args = run.call_args_list[0][0][0]
    kwargs = run.call_args_list[0][1]
    # Same argv-safety requirement as the password: the hex key must be
    # piped in via stdin, not passed as a CLI argument.
    assert args[-1] == "-w"
    assert key.hex() not in args
    assert kwargs.get("input") == f"{key.hex()}\n{key.hex()}\n"
    with mock.patch("subprocess.run", return_value=ok(key.hex() + "\n")):
        assert keychain.get_pairing_key("SER1") == key


def test_get_pairing_key_corrupt_hex_raises_keychain_error():
    # A corrupt Keychain entry must surface as KeychainError, not a bare
    # ValueError from bytes.fromhex — daemon.py only catches KeychainError,
    # and under launchd's KeepAlive an uncaught ValueError crash-loops the
    # helper with no diagnostic.
    with mock.patch("subprocess.run", return_value=ok("not valid hex!\n")):
        with pytest.raises(keychain.KeychainError):
            keychain.get_pairing_key("SER1")
