"""The `dashtouch` command. Friendly on purpose — setup output is part of
the product."""
from __future__ import annotations

import argparse
import getpass
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

    port = None
    try:
        port = serial_link.find_port()
    except serial_link.AmbiguousPortError as e:
        print(f"   Heads up: {e}")
    if port and shutil.which("arduino-cli"):
        ans = input(f"4. Found your board at {port}. Flash the firmware now? [Y/n] ")
        if ans.strip().lower() in ("", "y", "yes"):
            try:
                subprocess.run(["arduino-cli", "compile", "--fqbn", FQBN,
                                str(REPO / "firmware" / "dashtouch")], check=True)
                subprocess.run(["arduino-cli", "upload", "--fqbn", FQBN, "-p", port,
                                str(REPO / "firmware" / "dashtouch")], check=True)
                print("   Flashed. Watch for the steady purple ring.")
            except subprocess.CalledProcessError:
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
    return 0


def cmd_install_agent(args) -> int:
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(render_plist(sys.executable, str(REPO)))
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)],
                   capture_output=True)
    try:
        subprocess.run(["launchctl", "load", str(PLIST_PATH)], check=True)
        print(f"Installed and started. It now runs whenever you're logged in.")
        print(f"Logs: /tmp/dashtouch-helper.log")
        return 0
    except subprocess.CalledProcessError:
        print("launchctl refused — try `launchctl unload` first, then re-run.")
        return 1


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
    args = p.parse_args()
    rc = {"setup": cmd_setup, "run": cmd_run, "enroll": cmd_enroll,
          "doctor": cmd_doctor, "install-agent": cmd_install_agent}[args.cmd](args)
    sys.exit(rc)
