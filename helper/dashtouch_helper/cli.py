"""The `dashtouch` command. Friendly on purpose — setup output is part of
the product."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import pathlib
import secrets as pysecrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

from . import daemon as daemon_mod
from . import keychain, serial_link, webui

REPO = pathlib.Path(__file__).parents[2]
SECRETS_PATH = REPO / "firmware" / "dashtouch" / "secrets.h"
FQBN = "esp32:esp32:adafruit_qtpy_esp32s3_nopsram:CDCOnBoot=cdc,USBMode=default"
PLIST_PATH = pathlib.Path.home() / "Library" / "LaunchAgents" / "com.dashtouch.helper.plist"
# Not shared, world-readable /tmp — launchd's stdout/stderr log for the
# helper (which includes the web UI's origin) lives under the user's own
# Library, same as the plist itself.
LOG_DIR = pathlib.Path.home() / "Library" / "Logs" / "dashtouch"


def write_secrets(key: bytes, path: pathlib.Path) -> None:
    rows = []
    for i in range(0, 32, 8):
        rows.append("  " + ", ".join(f"0x{b:02x}" for b in key[i:i + 8]) + ",")
    body = "\n".join(rows)[:-1]  # drop trailing comma
    path.write_text(
        "#pragma once\n"
        "// Written by `dashtouch setup`. Never commit this file.\n"
        "static const uint8_t PAIRING_KEY[32] = {\n" + body + "\n};\n")
    # Same plaintext pairing key that lives in the Keychain — keep this
    # third copy owner-readable only.
    path.chmod(0o600)


def render_plist(python: str, workdir: str) -> str:
    tmpl = (pathlib.Path(__file__).parent / "launchd_template.plist").read_text()
    return (tmpl.replace("{python}", python)
                .replace("{workdir}", workdir)
                .replace("{logdir}", str(LOG_DIR)))


AGENT_SERVICE = "com.dashtouch.helper"


def _agent_domain() -> str:
    return f"gui/{os.getuid()}"


def agent_is_loaded() -> bool:
    """True if the launch agent is currently registered with launchd."""
    result = subprocess.run(["launchctl", "print", f"{_agent_domain()}/{AGENT_SERVICE}"],
                            capture_output=True, check=False)
    return result.returncode == 0


def stop_agent() -> None:
    subprocess.run(["launchctl", "bootout", f"{_agent_domain()}/{AGENT_SERVICE}"],
                   capture_output=True, check=False)


def start_agent() -> bool:
    result = subprocess.run(["launchctl", "bootstrap", _agent_domain(), str(PLIST_PATH)],
                            capture_output=True, check=False)
    return result.returncode == 0


def port_holders(port: str) -> list:
    """(pid, command) for every process holding `port` open.

    Returns [] when lsof isn't installed — that's "we couldn't tell", not
    "definitely free", so callers should carry on and let the flash produce
    its own error rather than blocking on our ignorance.
    """
    if not shutil.which("lsof"):
        return []
    result = subprocess.run(["lsof", "-t", port], capture_output=True,
                            text=True, check=False)
    holders = []
    for token in result.stdout.split():
        try:
            pid = int(token)
        except ValueError:
            continue
        ps = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                            capture_output=True, text=True, check=False)
        holders.append((pid, ps.stdout.strip() or "unknown"))
    return holders


def wait_for_port_free(port: str, timeout: float = 5.0) -> list:
    """Poll until nothing holds `port`, returning whatever still does (empty
    on success). `launchctl bootout` returns before the process has actually
    exited, so checking once immediately after it is a race."""
    deadline = time.monotonic() + timeout
    while True:
        holders = port_holders(port)
        if not holders:
            return []
        if time.monotonic() >= deadline:
            return holders
        time.sleep(0.25)


def find_and_flash(prompt_prefix: str = "") -> str:
    """Detect the board and, if found, offer to compile+upload the current
    firmware/dashtouch/ sources to it. Shared by `setup` and `pairing` so
    there's exactly one flash code path.

    Returns one of "flashed", "declined", "not_found", "failed".
    `prompt_prefix` is prepended to the confirmation prompt (e.g. step
    numbering) so each caller keeps its own voice.
    """
    port = None
    try:
        port = serial_link.find_port()
    except serial_link.AmbiguousPortError as e:
        print(f"   Heads up: {e}")
    if not (port and shutil.which("arduino-cli")):
        return "not_found"
    ans = input(f"{prompt_prefix}Found your board at {port}. Flash the firmware now? [Y/n] ")
    if ans.strip().lower() not in ("", "y", "yes"):
        return "declined"

    # The helper keeps the serial port open, so flashing on top of a running
    # one dies with "Resource busy" — and because the launch agent sets
    # KeepAlive, killing it just brings it back. Stop it properly, flash,
    # then put it back exactly as we found it.
    agent_was_loaded = agent_is_loaded()
    if agent_was_loaded:
        print("   Stopping the background helper so it lets go of the port...")
        stop_agent()

    try:
        holders = wait_for_port_free(port)
        if holders:
            print("   Something still has the serial port open:")
            for pid, command in holders:
                print(f"     pid {pid}  {command}")
            print("   That's usually a `dashtouch run` in another terminal.")
            print("   Stop it and try again.")
            return "failed"

        # Releasing the port drops DTR, which can reset the board and bring
        # it back on a different device node. Re-detect instead of trusting
        # the name captured before the helper let go.
        try:
            port = serial_link.find_port() or port
        except serial_link.AmbiguousPortError:
            pass

        subprocess.run(["arduino-cli", "compile", "--fqbn", FQBN,
                        str(REPO / "firmware" / "dashtouch")], check=True)
        subprocess.run(["arduino-cli", "upload", "--fqbn", FQBN, "-p", port,
                        str(REPO / "firmware" / "dashtouch")], check=True)
        # Erase the plaintext secrets file on the Mac now that flashing
        # completed successfully so a pairing key isn't sitting on disk.
        try:
            if SECRETS_PATH.exists():
                SECRETS_PATH.unlink()
        except OSError:
            # If erase fails for any reason, leave the file — better to let
            # user recover than to crash the workflow. The file was mode 0600.
            pass
        return "flashed"
    except subprocess.CalledProcessError:
        return "failed"
    finally:
        if agent_was_loaded:
            if start_agent():
                print("   Background helper restarted.")
            else:
                print("   Couldn't restart the background helper — run:")
                print("     dashtouch install-agent")


def cmd_setup(args) -> int:
    print("Let's get Dashboard Touch talking to your Mac.\n")

    serial_no = args.serial or daemon_mod.DEFAULT_SERIAL

    print("1. Making a pairing key (a shared secret between the gadget and")
    print("   your Mac — it lives in your Keychain).")
    key = pysecrets.token_bytes(32)
    keychain.set_pairing_key(serial_no, key)

    print("2. Your Mac password. It goes straight into the Keychain — it is")
    print("   never shown, logged, or sent anywhere.")
    pw = getpass.getpass("   Password: ")
    keychain.set_password(serial_no, pw)
    del pw

    print("3. Writing the key into the firmware's secrets file.")
    write_secrets(key, SECRETS_PATH)

    result = find_and_flash("4. ")
    if result == "flashed":
        print("   Flashed. Watch for the steady purple ring.")
    elif result == "failed":
        print("   That didn't work — the full error is above. Fix and re-run")
        print("   ./setup; it picks up where it left off.")
        return 1
    else:
        print("4. (Hmm — no board found. Plug it in over USB and run ./setup")
        print("   again; it's safe to re-run. Or flash by hand with the commands")
        print("   in the README.)")

    print("\nAll set. Run `.venv/bin/dashtouch run`, then `.venv/bin/dashtouch enroll`")
    print("to add your first finger.")
    return 0


def cmd_password(args) -> int:
    if getattr(args, "password", None):
        print("dashtouch password never takes the new password as an argument")
        print("— anything on the command line ends up in your shell history")
        print("and process list. Just run `dashtouch password` with no flags")
        print("and it'll ask you.")
        return 1

    serial_no = args.serial or daemon_mod.DEFAULT_SERIAL

    print("Let's update the password Dashboard Touch types.\n")
    print("This only updates the copy in your Keychain — it can't change your")
    print("actual Mac password. If you haven't already, change it first in")
    print("System Settings, then come back and run this.\n")

    for attempt in range(3):
        pw1 = getpass.getpass("New password: ")
        pw2 = getpass.getpass("Type it again: ")
        if pw1 == pw2:
            keychain.set_password(serial_no, pw1)
            del pw1, pw2
            print("\nSaved. It takes effect on your next touch — if the helper")
            print("is already running, it'll pick this up on its own, no")
            print("restart needed. Your fingerprints and pairing are untouched.")
            return 0
        del pw1, pw2
        print("Those two didn't match — let's try again.\n")

    print("\nThree tries, no match — stopping here so nothing gets saved by")
    print("mistake. Run `dashtouch password` again when you're ready.")
    return 1


def _print_secrets_cleanup_note() -> None:
    """A successful flash deletes secrets.h on its way out; the failure paths
    deliberately leave it so a by-hand retry can compile. Say so, since that
    leaves a plaintext copy of the pairing key sitting on disk until the
    person does something about it."""
    print("\nHeads up: firmware/dashtouch/secrets.h is still on disk, because")
    print("the flash didn't finish — a by-hand compile needs it. It's a")
    print("plaintext copy of your pairing key, so delete it once you're done:")
    print(f"  rm {SECRETS_PATH}")


def cmd_pairing(args) -> int:
    serial_no = args.serial or daemon_mod.DEFAULT_SERIAL

    print("Let's rotate your pairing key — the shared secret the gadget and")
    print("this Mac use to trust each other.\n")
    print("Before you say yes: this writes a brand-new key to your Keychain")
    print("and to firmware/dashtouch/secrets.h, and the gadget's firmware")
    print("MUST be reflashed afterward. Until it is, the gadget and this Mac")
    print("will disagree — the Checkup's Pairing row goes red and touches")
    print("stop working.\n")
    ans = input("Continue? [y/N] ")
    if ans.strip().lower() not in ("y", "yes"):
        print("Nothing changed.")
        return 0

    print("\nGenerating a new key and saving it to your Keychain and to")
    print("firmware/dashtouch/secrets.h...")
    key = pysecrets.token_bytes(32)
    keychain.set_pairing_key(serial_no, key)
    write_secrets(key, SECRETS_PATH)
    print("Done.\n")

    result = find_and_flash("")
    if result == "flashed":
        print("\nFlashed. Watch for the steady purple ring.")
        return 0
    elif result == "failed":
        print("\nThat didn't work — the full error is above. The new key is")
        print("saved on the Mac side, but the gadget still has the old one,")
        print("so it won't work until you flash. Fix the error above and run:")
        print(f"  arduino-cli compile --fqbn {FQBN} firmware/dashtouch")
        print("  arduino-cli upload --fqbn " + FQBN + " -p <port> firmware/dashtouch")
        _print_secrets_cleanup_note()
        return 1
    else:
        print("\nThe gadget still has the OLD key and won't work until it's")
        print("reflashed. When you're ready, plug it in and run:")
        print(f"  arduino-cli compile --fqbn {FQBN} firmware/dashtouch")
        print("  arduino-cli upload --fqbn " + FQBN + " -p <port> firmware/dashtouch")
        _print_secrets_cleanup_note()
        return 0


def cmd_run(args) -> int:
    daemon_mod.main(args.serial or daemon_mod.DEFAULT_SERIAL)
    return 0


def _webui_url() -> str | None:
    """The full link to the helper's page (no session token in the URL),
    or None if the helper has never run (that file is written on startup)."""
    try:
        url = webui.URL_PATH.read_text().strip()
    except (OSError, UnicodeDecodeError):
        return None
    return url or None


def _no_helper_note() -> None:
    print("The helper isn't running yet. Start it with:")
    print("  .venv/bin/dashtouch run")
    print("or have it start on its own at login:")
    print("  .venv/bin/dashtouch install-agent")


def cmd_where(args) -> int:
    """Bare `dashtouch` — hand back the address of the helper's page.

    Printed on its own line so it can be piped, e.g. `open $(dashtouch)`.
    The link carries the session key, so it's as sensitive as a password —
    the note goes to stderr to keep stdout clean for that pipe.
    """
    url = _webui_url()
    if not url:
        _no_helper_note()
        return 1
    print(url)
    if sys.stderr.isatty():
        print("\nThis link opens the helper's page on localhost; the session token is handled locally and is not included in the URL.\n"
              "Use `dashtouch enroll` to open it for you.", file=sys.stderr)
    return 0


def cmd_enroll(args) -> int:
    url = _webui_url()
    if not url:
        _no_helper_note()
        return 1

    webbrowser.open(url)
    print("Opening the helper's page in your browser.")
    return 0


def _daemon_base_url() -> str | None:
    """The running helper's base URL (with a trailing slash, no token),
    read from the file `dashtouch run` writes on startup. None if the
    helper has never run or that file is missing."""
    try:
        url = webui.URL_PATH.read_text().strip()
    except FileNotFoundError:
        return None
    if not url:
        return None
    return url.split("?")[0]


def _daemon_status() -> dict | None:
    """GET /api/status from the running helper. None if the helper isn't
    reachable — that file existing doesn't guarantee it's still running."""
    base = _daemon_base_url()
    if not base:
        return None
    try:
        with urllib.request.urlopen(base + "api/status", timeout=3) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _daemon_post_setting(key: str, value: int) -> tuple[int, dict]:
    """POST /api/settings against the running helper. Raises on any
    transport failure — callers decide how to report that."""
    base = _daemon_base_url()
    # Use the Keychain-stored session token. If Keychain access fails,
    # the operation cannot proceed securely and we fail with a clear message.
    try:
        from . import keychain
        token = keychain.get_session_token()
    except Exception as e:
        raise RuntimeError("Session token unavailable in Keychain. Ensure the helper is running and can access the Keychain.") from e

    req = urllib.request.Request(
        base + "api/settings",
        data=json.dumps({"key": key, "value": value}).encode(),
        headers={"Content-Type": "application/json", "X-DT-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=3) as resp:
        return resp.status, json.loads(resp.read())


def cmd_pins(args) -> int:
    """Check or change which pair of pins the sensor UART uses. Some
    boards' QT Py can't transmit on the default pad (see
    docs/history/2026-08-12-qtpy-uart-fault.md) — this used to mean
    hand-editing firmware/dashtouch/config.h, a change that was easy to
    lose and once nearly bricked a sensor on reflash. Now it's a setting
    stored on the device itself. Only the sensor wiring is affected; the
    USB link to this Mac never changes, so it's always safe to try."""
    if args.swap and args.normal:
        print("Pick one: --swap or --normal, not both.")
        return 1

    if not (args.swap or args.normal):
        status = _daemon_status()
        if status is None:
            print("The helper isn't running — start it with `.venv/bin/dashtouch run`,")
            print("then run `dashtouch pins` again to see the current orientation.")
            return 1
        settings = status.get("settings") or {}
        if "fp_swap" not in settings:
            print("Still waiting on the device's own settings reply — try again in a")
            print("moment.")
            return 1
        if settings["fp_swap"]:
            print("Sensor pins are SWAPPED: the gadget transmits on the pad labeled RX")
            print("and receives on the pad labeled TX.")
        else:
            print("Sensor pins are at their default orientation: transmit on TX,")
            print("receive on RX (the silkscreen labels).")
        print()
        print("Some boards can't transmit on the default TX pad. `dashtouch pins")
        print("--swap` moves the sensor UART to the other pair, on the spot, no")
        print("reflash needed.")
        return 0

    want_swap = bool(args.swap)
    print("Some boards can't transmit on the default TX pad — this moves the sensor")
    print("UART to the other pair. Only the sensor wiring changes; the USB link to")
    print("this Mac never does, so it's always safe to try.\n")

    try:
        status_code, body = _daemon_post_setting("fp_swap", 1 if want_swap else 0)
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"Couldn't reach the helper: {e}")
        print("Is it running? `.venv/bin/dashtouch run` starts it.")
        return 1
    if status_code != 202:
        print(f"The helper turned that down: {body.get('error', body)}")
        return 1

    print(f"Set — pins are now {'swapped' if want_swap else 'at their default orientation'}.")
    print()
    # The firmware can't verify this live: real hardware testing showed an
    # in-place UART re-init is unreliable and can report success even when
    # the sensor isn't actually reachable. Don't check and don't guess —
    # tell the person the one thing that's actually true.
    print("This needs a power-cycle before it can be trusted: unplug the gadget")
    print("and plug it back in (or run `dashtouch doctor` after), then check")
    print("`dashtouch pins` or the web UI to see whether that orientation works.")
    return 0


def cmd_doctor(args) -> int:
    print("Dashboard Touch check-up\n")
    try:
        port = serial_link.find_port()
    except serial_link.AmbiguousPortError as e:
        print(f"• More than one board is plugged in: {e}")
        return 1
    if port is None:
        print("• No board found. Check the USB cable — some cables are")
        print("  power-only and can't carry data.")
        return 1
    print(f"• Board found at {port}. Good.")
    print("• Ring colors: purple = ready · white = reading · green = match")
    print("  · red = device-side problem · yellow = can't reach your Mac")
    print("  · cyan = lift your finger (enrolling)")
    print("• Ring never purple? Check all six wires — the white one matters")
    print("  more than it looks. Full guide: docs/troubleshooting.md")
    print("• Suspect the board itself? firmware/diagnostics/ has the tools.")
    print("• Changed your Mac password? `.venv/bin/dashtouch password` updates")
    print("  the Keychain copy — no reflash, no re-provisioning.")
    print("• Pairing gone stale (red Pairing row)? `.venv/bin/dashtouch pairing`")
    print("  makes a fresh key and walks you through reflashing it.")
    return 0


def cmd_install_agent(args) -> int:
    """Install the helper as a launch agent using the modern launchctl API."""
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(render_plist(sys.executable, str(REPO)))

    uid = os.getuid()
    domain = f"gui/{uid}"
    service_name = "com.dashtouch.helper"

    # 1. Tear down first, tolerating absence
    subprocess.run(["launchctl", "bootout", f"{domain}/{service_name}"],
                   capture_output=True, check=False)

    # 2. Load with the modern API
    try:
        result = subprocess.run(["launchctl", "bootstrap", domain, str(PLIST_PATH)],
                                capture_output=True, check=True, text=True)
    except subprocess.CalledProcessError as e:
        print("launchctl bootstrap failed:")
        if e.stderr:
            print(e.stderr.strip())
        return 1

    # 3. Verify it took
    result = subprocess.run(["launchctl", "print", f"{domain}/{service_name}"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print("launchctl accepted it but the helper isn't registered — something's off")
        return 1

    print("Installed and started. It now runs whenever you're logged in.")
    print(f"Logs: {LOG_DIR / 'helper.log'}")
    print()
    print("To stop it later, run:")
    print(f"  launchctl bootout gui/$(id -u)/com.dashtouch.helper")
    print("Or use the `dashtouch uninstall-agent` command.")
    return 0


def cmd_uninstall_agent(args) -> int:
    """Remove the launch agent."""
    uid = os.getuid()
    domain = f"gui/{uid}"
    service_name = "com.dashtouch.helper"

    # Bootout and confirm it's gone
    result = subprocess.run(["launchctl", "bootout", f"{domain}/{service_name}"],
                            capture_output=True, text=True)

    # Verify it's gone
    verify = subprocess.run(["launchctl", "print", f"{domain}/{service_name}"],
                            capture_output=True, text=True)
    if verify.returncode == 0:
        print("Couldn't unload the helper — something's off")
        return 1

    print("Uninstalled. The helper won't start on your next login.")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(
        prog="dashtouch",
        description="Your fingerprint, your Mac. "
                    "Run with no command to print the link to the helper's page.")
    p.add_argument("--serial", help="board serial (default: this build's)")
    # Not required: bare `dashtouch` prints the web UI address.
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("setup", help="first-time setup, start to finish")
    sub.add_parser("run", help="run the helper (launchd uses this)")
    sub.add_parser("enroll", help="open the enrollment page")
    sub.add_parser("doctor", help="quick health check")
    sub.add_parser("install-agent", help="run the helper automatically at login")
    sub.add_parser("uninstall-agent", help="stop running the helper at login")
    p_password = sub.add_parser("password", help="change the password Dashboard Touch types")
    p_password.add_argument("--password", help=argparse.SUPPRESS)
    sub.add_parser("pairing", help="rotate the pairing key (needs a reflash)")
    p_pins = sub.add_parser("pins", help="check or change the sensor's TX/RX pin orientation")
    p_pins.add_argument("--swap", action="store_true",
                        help="swap the sensor UART pins (for boards that can't transmit on the default one)")
    p_pins.add_argument("--normal", action="store_true",
                        help="use the default (silkscreen) pin orientation")
    args = p.parse_args()
    if args.cmd is None:
        sys.exit(cmd_where(args))
    rc = {"setup": cmd_setup, "run": cmd_run, "enroll": cmd_enroll,
          "doctor": cmd_doctor, "install-agent": cmd_install_agent,
          "uninstall-agent": cmd_uninstall_agent,
          "password": cmd_password, "pairing": cmd_pairing,
          "pins": cmd_pins}[args.cmd](args)
    sys.exit(rc)
