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


def _run(args: list[str], input_value: str | None = None,
         detach_tty: bool = False) -> str:
    try:
        return subprocess.run(args, check=True, capture_output=True,
                              text=True, input=input_value,
                              start_new_session=detach_tty).stdout
    except subprocess.CalledProcessError as e:
        raise KeychainError(f"{args[1]} failed: {e.stderr.strip()}") from e


def _set(service: str, account: str, value: str) -> None:
    # The secret is deliberately NOT on the argv line — anything passed to
    # `-w` directly would sit in `ps` output, readable by any local process,
    # for as long as `security` runs. With `-w` as the LAST argument and no
    # value after it, `security` reads the value instead of taking it from
    # argv. It reads twice — password, then a retype confirmation — so both
    # copies go over stdin, newline-terminated, or the confirmation read
    # hits EOF and the write fails.
    #
    # start_new_session is load-bearing. `security` uses readpassphrase(),
    # which opens /dev/tty when a controlling terminal exists and only falls
    # back to stdin when one doesn't. Under launchd and in tests there is no
    # TTY, so stdin worked and this looked correct. Run interactively —
    # which is exactly how `dashtouch setup` and `dashtouch pairing` are
    # run — and `security` prompted the operator instead, storing whatever
    # they typed and discarding the generated key. Detaching from the
    # session removes the TTY so the stdin path is taken every time.
    _run(["security", "add-generic-password", "-U",
          "-s", service, "-a", account, "-w"],
         input_value=f"{value}\n{value}\n", detach_tty=True)

    # Read back and compare. A silent mismatch here means the Keychain and
    # firmware/dashtouch/secrets.h hold different pairing keys, which shows
    # up much later as "the gadget and this Mac disagree" with nothing
    # pointing at the write that caused it.
    if _get(service, account) != value:
        raise KeychainError(
            f"wrote {service} but it didn't read back correctly — the "
            "Keychain stored something other than what was sent")


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
    raw = _get(SERVICE_PAIRING, serial)
    try:
        return bytes.fromhex(raw)
    except ValueError as e:
        # A corrupt Keychain entry must not escape as a bare ValueError:
        # daemon.py only catches KeychainError, and under launchd's
        # KeepAlive an uncaught exception here means the helper crash-loops
        # with no useful diagnostic.
        raise KeychainError(
            "the pairing key in your Keychain is corrupt (not valid hex) — "
            "run `dashtouch pairing` to make a fresh one") from e
