import subprocess
from unittest import mock

import pytest

from dashtouch_helper import keychain


def ok(stdout=""):
    return subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")


def test_set_password_calls_security_add():
    with mock.patch("subprocess.run", return_value=ok()) as run:
        keychain.set_password("SER1", "pw")
    args = run.call_args[0][0]
    assert args[:2] == ["security", "add-generic-password"]
    assert "DashboardTouch" in args and "SER1" in args and "pw" in args


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
    with mock.patch("subprocess.run", return_value=ok()) as run:
        keychain.set_pairing_key("SER1", key)
    assert key.hex() in run.call_args[0][0]
    with mock.patch("subprocess.run", return_value=ok(key.hex() + "\n")):
        assert keychain.get_pairing_key("SER1") == key
