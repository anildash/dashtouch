"""Password + pairing key storage in the macOS Keychain.

Entries are keyed on the board's serial number as the account, so two
boards can pair with one Mac without colliding.
"""
from __future__ import annotations

import subprocess

SERVICE_PASSWORD = "DashboardTouch"
SERVICE_PAIRING = "DashboardTouch-pairing"


class KeychainError(Exception):
    pass


def _run(args: list[str]) -> str:
    try:
        return subprocess.run(args, check=True, capture_output=True,
                              text=True).stdout
    except subprocess.CalledProcessError as e:
        raise KeychainError(f"{args[1]} failed: {e.stderr.strip()}") from e


def _set(service: str, account: str, value: str) -> None:
    _run(["security", "add-generic-password", "-U",
          "-s", service, "-a", account, "-w", value])


def _get(service: str, account: str) -> str:
    out = _run(["security", "find-generic-password",
                "-s", service, "-a", account, "-w"])
    return out.strip()


def set_password(serial: str, pw: str) -> None:
    _set(SERVICE_PASSWORD, serial, pw)


def get_password(serial: str) -> str:
    return _get(SERVICE_PASSWORD, serial)


def set_pairing_key(serial: str, key: bytes) -> None:
    _set(SERVICE_PAIRING, serial, key.hex())


def get_pairing_key(serial: str) -> bytes:
    return bytes.fromhex(_get(SERVICE_PAIRING, serial))
