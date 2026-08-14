"""The `dashtouch` command. Friendly on purpose — setup output is part of
the product."""
from __future__ import annotations

import argparse
import getpass
import os
import pathlib
import secrets as pysecrets
import shutil
import subprocess
import sys
import webbrowser

from . import daemon as daemon_mod
from . import keychain, serial_link, webui

REPO = pathlib.Path(__file__).parents[2]
SECRETS_PATH = REPO / "firmware" / "dashtouch" / "secrets.h"
FQBN = "esp32:esp32:adafruit_qtpy_esp32s3_nopsram:CDCOnBoot=cdc,USBMode=default"
PLIST_PATH = pathlib.Path.home() / "Library" / "LaunchAgents" / "com.dashtouch.helper.plist"


def write_secrets(key: bytes, path: pathlib.Path) -> None:
    rows = []
    for i in range(0, 32, 8):
        rows.append("  " + ", ".join(f"0x{b:02x}" for b in key[i:i + 8]) + ",")
    body = "\n".join(rows)[:-1]  # drop trailing comma
    path.write_text(
        "#pragma once\n"
        "// Written by `dashtouch setup`. Never commit this file.\n"
        "static const uint8_t PAIRING_KEY[32] = {\n" + body + "\n};\n")


def render_plist(python: str, workdir: str) -> str:
    tmpl = (pathlib.Path(__file__).parent / "launchd_template.plist").read_text()
    return tmpl.replace("{python}", python).replace("{workdir}", workdir)


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
    try:
        subprocess.run(["arduino-cli", "compile", "--fqbn", FQBN,
                        str(REPO / "firmware" / "dashtouch")], check=True)
        subprocess.run(["arduino-cli", "upload", "--fqbn", FQBN, "-p", port,
                        str(REPO / "firmware" / "dashtouch")], check=True)
        return "flashed"
    except subprocess.CalledProcessError:
        return "failed"


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
        return 1
    else:
        print("\nThe gadget still has the OLD key and won't work until it's")
        print("reflashed. When you're ready, plug it in and run:")
        print(f"  arduino-cli compile --fqbn {FQBN} firmware/dashtouch")
        print("  arduino-cli upload --fqbn " + FQBN + " -p <port> firmware/dashtouch")
        return 0


def cmd_run(args) -> int:
    daemon_mod.main(args.serial or daemon_mod.DEFAULT_SERIAL)
    return 0


def cmd_enroll(args) -> int:
    try:
        url = webui.URL_PATH.read_text().strip()
    except FileNotFoundError:
        url = None

    if not url:
        print("The helper isn't running yet — start it with `.venv/bin/dashtouch run`, then")
        print("try again (or just open the link it prints).")
        return 1

    webbrowser.open(url)
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
    print("Logs: /tmp/dashtouch-helper.log")
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
    p = argparse.ArgumentParser(prog="dashtouch",
                                description="Your fingerprint, your Mac.")
    p.add_argument("--serial", help="board serial (default: this build's)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup", help="first-time setup, start to finish")
    sub.add_parser("run", help="run the helper (launchd uses this)")
    sub.add_parser("enroll", help="open the enrollment page")
    sub.add_parser("doctor", help="quick health check")
    sub.add_parser("install-agent", help="run the helper automatically at login")
    sub.add_parser("uninstall-agent", help="stop running the helper at login")
    p_password = sub.add_parser("password", help="change the password Dashboard Touch types")
    p_password.add_argument("--password", help=argparse.SUPPRESS)
    sub.add_parser("pairing", help="rotate the pairing key (needs a reflash)")
    args = p.parse_args()
    rc = {"setup": cmd_setup, "run": cmd_run, "enroll": cmd_enroll,
          "doctor": cmd_doctor, "install-agent": cmd_install_agent,
          "uninstall-agent": cmd_uninstall_agent,
          "password": cmd_password, "pairing": cmd_pairing}[args.cmd](args)
    sys.exit(rc)
