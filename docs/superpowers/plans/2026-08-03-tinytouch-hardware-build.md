# tinyTouch Hardware Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get a QT Py ESP32-S3 + R503-compatible fingerprint sensor running
tinyTouch's HID ("red pill") firmware end-to-end on a breadboard —
fingerprint touch types the real macOS password — before any enclosure work
begins.

## ✅ WORKING END TO END as of 2026-08-13

The device does the whole job: touch an enrolled finger and the real macOS
password is typed. Observed repeatedly —

```
TOUCH → MATCH 1 142 → EV <nonce> <hmac> → sent encrypted password
      → EV_SENT → TYPED
```

**The blocker was never either sensor.** Two faults were stacked:

1. **GPIO 5 cannot carry UART transmit on this board.** Routed around by
   transmitting on GPIO 16 / receiving on GPIO 5, backwards vs. the
   silkscreen. Firmware constants updated accordingly.
2. **Sensor pin 6 (`3.3VT`, white wire) was never connected.** *This is the
   one that mattered.* Without it the module receives and executes commands
   (the ring visibly obeys) but cannot reply — indistinguishable from a dead
   part. This single wire is the entire "defective sensor" arc.

Also required: `USE_INT_PIN = false` in the firmware. On this module the
WAKEUP line sits permanently at the active level, so the INT path scanned
continuously and every scan returned `GENIMG_FAIL 2`. Polling `GenImg`
instead works reliably.

**Corrections to earlier records:** the R503 is not defective; the ZW111
verdict is unsafe for two independent reasons (see the design spec); and
`fp_sweep`'s `trailing_bytes=0` never meant "the sensor is silent" —
`verifyPassword()` eats the reply first. See `firmware/diagnostics/README.md`.

**Remaining:** launchd agent (Task 5 Steps 7-8) so the helper starts
automatically. Everything before that is done and verified on hardware.

---

**Status as of 2026-08-11 — historical, kept for the debugging record.**
(Superseded by the 2026-08-13 block above and the 2026-08-12 update below.)

Everything except the sensor is done and verified:

- QT Py soldered, flashed, talking over USB CDC (`PING` → `PONG`).
- Firmware pin mapping fixed for the QT Py's real GPIOs (TX=5, RX=16,
  INT=8/A3). Committed.
- Enrollment built into the firmware (`ENROLL`/`DELETE` serial commands plus
  `software/macos-helper/tinytouch_enroll.py`) — this did not exist upstream.
- Two Aura LED bugs fixed against a reference driver (wrong color codes,
  wrong parameter order). Compile-clean but **unverified on hardware**.
- Keychain password **and** pairing key both set; `secrets.h` verified to
  hold the same pairing key as the Keychain; `--self-test` passes. The whole
  crypto path is proven without the sensor.

**Update 2026-08-12 — the blocker was never the sensor.**

The R503 arrived and was wired up. It was silent on all 14 sweep
combinations, identically to the ZW111. A board-only UART loopback test then
found that **the QT Py pad labeled `TX` (GPIO 5) cannot carry UART
transmit** — so no command this project ever sent reached either sensor, and
neither could ever have replied.

- The build now transmits on GPIO 16 and receives on GPIO 5, backwards
  relative to the silkscreen. See the design spec, "GPIO 5 will not transmit
  on this board."
- The R503 has **not** been shown to be faulty; it has never had a fair test.
- The ZW111 "defective" verdict is no longer trustworthy for the same reason.
- Root cause of the GPIO 5 fault is still unconfirmed. Reflowing the joint
  did not change it.

Full investigation record, including the reusable test plan and every
hypothesis ruled in or out:
`docs/superpowers/references/2026-08-12-qtpy-uart-fault.md`.

**Also done 2026-08-12:** toolchain rebuilt on a second machine (`arduino-cli`
+ `esp32:esp32@3.3.11`); both sketches compile clean; observed R503 wire
colors recorded in the spec, replacing a guess that was wrong on four of six;
`PREFERRED_SERIAL` in the helper corrected from an upstream author's board
serial to this build's (`68EE8F6E7390`).

**Next:** confirm the R503 responds in the swapped pin configuration, then
re-verify the connector orientation with a meter (pullup test, see spec).

**Setup needed on a fresh machine:**

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r software/macos-helper/requirements.txt
brew install arduino-cli
arduino-cli config init
arduino-cli config set board_manager.additional_urls \
  https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
arduino-cli core update-index && arduino-cli core install esp32:esp32
arduino-cli lib install "Adafruit Fingerprint Sensor Library"
```

`secrets.h` is gitignored and will need recreating from
`secrets.example.h` with the pairing key from Keychain. The Keychain entries
themselves are per-machine, so `--set-pairing-key` and `--set-password` must
be re-run there (and the same pairing key written into `secrets.h`).

`reference/` is gitignored (~16MB of cloned repos) — re-clone with the
commands in `docs/superpowers/references/r503-reference.md`.

**See also:** that same reference doc for driver libraries, prior-art
projects, and gotchas; `firmware/diagnostics/` for the two bring-up sketches
and how to read their output; and the design spec's "Enclosure design"
section for the woodworking.

**Architecture:** Existing `tiny_touch_keyboard.ino` firmware talks to the
fingerprint sensor over UART using the `0xEF01` packet protocol and to macOS
over USB HID (as a keyboard) plus USB CDC (serial link to a Python helper
daemon that holds the real password in Keychain). Fingerprint templates
live on the sensor's own flash, not the ESP32; enrollment is done via
`ENROLL`/`DELETE` serial commands built into the same firmware (see Task 4)
rather than a separate sketch.

**Tech Stack:** Arduino IDE (ESP32 board package), C/C++ (`.ino`), Python 3
(macOS helper), macOS Keychain.

## Global Constraints

- Board: Adafruit QT Py ESP32-S3, 8MB flash / no PSRAM (#5426).
- Arduino IDE board settings: `USB CDC on Boot: Enabled`, `USB Mode: USB-OTG`
  (from `firmware/tiny_touch_keyboard/README.md`).
- Fingerprint sensor: R503-compatible module, UART at 57600 baud (`9600×N`,
  N=6 default), `0xEF01` packet header. Ships with its own factory-crimped
  6-pin MX1.0 cable.
- Never commit `firmware/tiny_touch_keyboard/secrets.h` (already covered by
  the repo's existing guidance; verify `.gitignore` before creating it).
- Do not enable secure boot / flash encryption during this plan — those are
  one-way eFuse burns and are explicitly deferred until after the full
  enroll-match-type cycle is verified working (see design spec).

## Prerequisites

Before starting Task 1, have in hand: an Adafruit QT Py ESP32-S3 (#5426), an
R503-compatible fingerprint sensor (ships with its own 6-pin MX1.0 cable
attached), and a USB-C cable. These are purchasing steps (see the design
spec's Cost/BOM section for sourcing links), not engineering tasks, so they
aren't broken out below.

---

### Task 1: macOS helper environment and Keychain secrets

**Files:**
- No new files. Uses existing `software/macos-helper/tinytouch_helper.py`
  and `software/macos-helper/requirements.txt`.
- Creates local (untracked) state: macOS Keychain entries, and later
  `firmware/tiny_touch_keyboard/secrets.h`.

**Interfaces:**
- Produces: a 32-byte pairing key (hex string) that Task 4 copies byte-for-
  byte into `secrets.h`'s `PAIRING_KEY` array.

- [x] **Step 1: Create the venv and install dependencies** — DONE

```bash
cd /Users/anildash/Developer/dashtouch
python3 -m venv .venv
. .venv/bin/activate
pip install -r software/macos-helper/requirements.txt
```

Expected: `cryptography` and `pyserial` install with no errors.

- [x] **Step 2: Generate a pairing key and record it** — DONE

```bash
openssl rand -hex 32 | tee /tmp/tinytouch-pairing-key.txt
```

Expected: a 64-character hex string printed and saved to
`/tmp/tinytouch-pairing-key.txt`. Keep this terminal/file open — Task 4
needs these exact bytes.

- [x] **Step 3: Store the pairing key in Keychain** — DONE (verified present
  in Keychain under service `tinyTouch-pairing`)

```bash
.venv/bin/python software/macos-helper/tinytouch_helper.py \
  --set-pairing-key "$(cat /tmp/tinytouch-pairing-key.txt)"
```

Expected: command exits 0 with no error output.

- [x] **Step 4: Store your real macOS password in Keychain** — DONE
  (2026-08-13, set by the user directly).
  Previously recorded as: Verified absent: `security find-generic-password -a
  tinyTouch -s tinyTouch` returns nothing. Task 5's end-to-end test cannot
  pass until this is set. **Run this yourself in your own terminal** — it
  takes your real login password as an argument, so it should not be run
  through an agent session or pasted into any shared context.

```bash
.venv/bin/python software/macos-helper/tinytouch_helper.py \
  --set-password 'your-actual-mac-login-password'
```

Expected: command exits 0. Immediately clear this command from your shell
history (`history -d <line>` in zsh, or just don't worry about it if your
shell history isn't persisted/shared).

- [x] **Step 5: Delete the plaintext pairing-key scratch file** — DONE

```bash
rm /tmp/tinytouch-pairing-key.txt
```

You already have the key in Keychain (Step 3); Task 4 will re-derive it from
there if needed, or you can re-run Step 2 and re-set it — the key only needs
to match between Keychain and `secrets.h`.

---

### Task 2: Remap fingerprint sensor pins for the QT Py ESP32-S3

**Files:**
- Modify: `firmware/tiny_touch_keyboard/tiny_touch_keyboard.ino:14-16`

**Interfaces:**
- Produces: `FP_TX_PIN`, `FP_RX_PIN`, `FP_INT_PIN` constants used by
  `Finger.begin(...)` (line 431) and `pinMode(FP_INT_PIN, ...)` (line 427)
  later in the same file — no other task touches these.

- [x] **Step 1: Confirm current values** — DONE

```bash
grep -n "FP_TX_PIN\|FP_RX_PIN\|FP_INT_PIN" firmware/tiny_touch_keyboard/tiny_touch_keyboard.ino
```

Expected output includes:
```
14:static const int FP_TX_PIN = 43;
15:static const int FP_RX_PIN = 44;
16:static const int FP_INT_PIN = 2;
```

- [ ] **Step 2: Edit the pin constants**

In `firmware/tiny_touch_keyboard/tiny_touch_keyboard.ino`, change lines
14-16 from:

```cpp
static const int FP_TX_PIN = 43;
static const int FP_RX_PIN = 44;
static const int FP_INT_PIN = 2;
```

to:

```cpp
static const int FP_TX_PIN = 5;   // QT Py ESP32-S3 pin labeled TX
static const int FP_RX_PIN = 16;  // QT Py ESP32-S3 pin labeled RX
static const int FP_INT_PIN = 8;  // QT Py ESP32-S3 pin labeled A3
```

(This step is done — already committed as `2d16fe0`, using A3/GPIO8 rather
than the A0/GPIO18 an earlier draft of this plan specified. Both are valid
free pins; A3 is what's actually soldered and hardcoded now, so it's
authoritative. Steps 3-4 below are kept for reference.)

- [x] **Step 3: Verify the edit** — DONE

```bash
grep -n "FP_TX_PIN\|FP_RX_PIN\|FP_INT_PIN" firmware/tiny_touch_keyboard/tiny_touch_keyboard.ino
```

Expected output includes:
```
14:static const int FP_TX_PIN = 5;   // QT Py ESP32-S3 header pin labeled "TX"
15:static const int FP_RX_PIN = 16;  // QT Py ESP32-S3 header pin labeled "RX"
16:static const int FP_INT_PIN = 8;  // QT Py ESP32-S3 header pin labeled "A3"
```

- [x] **Step 4: Commit** — DONE

Already done in `2d16fe0` ("Fix QT Py ESP32-S3 pin mapping and add
fingerprint enrollment").

---

### Task 3: Wire the sensor and verify boot-time sensor detection

**Files:** None (hardware wiring + Arduino Serial Monitor observation only).

**Interfaces:**
- Consumes: pin assignments from Task 2 (`FP_TX_PIN=5`, `FP_RX_PIN=16`,
  `FP_INT_PIN=8`).

- [x] **Step 1: Wire on a breadboard (power off)** — DONE (all SIX wires; 3.3VT is mandatory)

The sensor now in use is an **R503-compatible module** (Amazon ASIN
B08HM8QDVW). Its pin order is **different from the ZW111's** — do not reuse
any earlier ZW111 wiring notes. Full table and sourcing in the design spec's
"R503 pinout" section.

This sensor ships with a factory-crimped cable, so identify each wire by its
**position at the connector** (the housing is printed with `1` at one end
and `6` at the other), not by guessing from color. Record the actual colors
once in hand and update the spec's table.

Connect, with the QT Py ESP32-S3 unpowered:

| Sensor pin | Signal | → QT Py pin |
| --- | --- | --- |
| 1 | Power Supply (3.3V) | `3V` |
| 2 | GND | `GND` |
| 3 | TXD (module → MCU) | `RX` (GPIO 16) |
| 4 | RXD (MCU → module) | `TX` (GPIO 5) |
| 5 | WAKEUP (finger detect) | `A3` (GPIO 8) |
| 6 | 3.3VT (always-on touch power) | `3V`, second wire |

Two things that look like mistakes but aren't: sensor TXD goes to the
board's `RX` (and RXD to `TX`) — standard UART crossover; and **two wires
land on the single `3V` pin** (pins 1 and 6), because the touch-detection
circuit needs power even when the main sensor rail is idle.

Lesson carried over from the ZW111 debugging: if using alligator clips or
temporary leads, **continuity-check each one through the clip** (probe from
the wire to the destination pin) before trusting any result. Clips that look
attached but don't pass continuity cost several hours last time.

- [x] **Step 2: Toolchain and board setup** — DONE

`arduino-cli` is installed (via Homebrew) with the ESP32 core, and the board
is auto-detected as `esp32:esp32:adafruit_qtpy_esp32s3_nopsram`. The full
FQBN with the required USB settings baked in:

```
esp32:esp32:adafruit_qtpy_esp32s3_nopsram:CDCOnBoot=cdc,USBMode=default
```

(That's the CLI equivalent of `USB CDC on Boot: Enabled` + `USB Mode:
USB-OTG` in the IDE. Arduino IDE is not required — everything below uses
`arduino-cli`.)

- [x] **Step 3: Create secrets.h** — DONE, with the real pairing key already
  written in (not a placeholder). Confirmed gitignored.

- [x] **Step 4: Flash the firmware** — DONE

```bash
arduino-cli board list
```

Note the `/dev/cu.usbmodemXXX` port (it changes between resets — often
`101` or `102`), then:

```bash
arduino-cli upload --fqbn esp32:esp32:adafruit_qtpy_esp32s3_nopsram:CDCOnBoot=cdc,USBMode=default -p /dev/cu.usbmodemXXX firmware/tiny_touch_keyboard
```

- [x] **Step 5: Verify sensor detection** — DONE (purple ring = READY)

The boot banner only prints once, right at reset, so catch it by watching
the port while pressing the physical reset button:

```bash
.venv/bin/python - <<'EOF'
import serial, time, glob
while glob.glob('/dev/cu.usbmodem*'): time.sleep(0.2)   # wait for reset
while not glob.glob('/dev/cu.usbmodem*'): time.sleep(0.2)  # wait for reconnect
port = glob.glob('/dev/cu.usbmodem*')[0]
time.sleep(0.3)
ser = serial.Serial(port, 115200, timeout=1)
end = time.time() + 6
while time.time() < end:
    line = ser.readline()
    if line: print(line.decode('utf-8','replace').strip())
ser.close()
EOF
```

Expected:
```
BOOT tinyTouch HID
READY
```

`READY` means the sensor answered `VerifyPassword` — UART is working.

If you instead see `ERR fingerprint_verify`, the sensor isn't responding.
Debug order, learned the hard way on the ZW111:
1. Confirm the board didn't brown out (does `/dev/cu.usbmodem*` disappear
   when the sensor is plugged in? → power short, unplug immediately).
2. Continuity-check GND, both `3V` wires, TXD, and RXD — *through* whatever
   connector or clip is in the path, not just end to end.
3. Try swapping TXD/RXD (harmless, and a crossed pair gives silence).
4. Watch the raw bytes: the firmware's `DEBUG_FP_RAW_ON_FAIL` flag prints
   `FP_RAW instr=.. bytes_seen=.. data=..` on every failed command. Zero
   bytes = nothing arriving at all; garbage bytes that never start with
   `ef01` = wrong baud, crosstalk, or a bad unit.

- [x] **Step 6: Sanity-check the serial link** — DONE (PING/PONG)

```bash
.venv/bin/python -c "
import serial,time
s=serial.Serial('/dev/cu.usbmodemXXX',115200,timeout=1); s.reset_input_buffer()
s.write(b'PING\n'); s.flush(); time.sleep(1)
print(s.readline().decode().strip()); s.close()"
```

Expected: `PONG`. (This only proves the ESP32↔Mac link, not the sensor —
it answered `PONG` fine throughout the entire ZW111 failure.)

---

### Task 4: Enroll a fingerprint

tinyTouch's own firmware originally had no enrollment routine — it only
matched against slots 1-5 (`START_SLOT`/`END_SLOT` in the `.ino`). Rather
than swap in a temporary separate sketch (this task's original approach),
`ENROLL <slot>` / `DELETE <slot>` serial commands were added directly to
`tiny_touch_keyboard.ino` (commit `2d16fe0`), implementing the standard
AS608/ZW101/ZW111 GenImg → Img2Tz → RegModel → Store sequence. This means
enrollment now works with the *same* firmware you flash for normal use — no
reflashing between enrolling and running.

**Files:**
- Already created: `software/macos-helper/tinytouch_enroll.py` drives the
  `ENROLL`/`DELETE` commands interactively over serial.

**Interfaces:**
- Produces: a fingerprint template stored in the sensor's onboard flash at
  the chosen slot (1-5), which `tiny_touch_keyboard.ino`'s `scanMatch()`
  will match against in Task 5.

- [x] **Step 1: Make sure nothing else has the serial port open** — DONE

Close Arduino IDE's Serial Monitor (or any other process using the port) —
`tinytouch_enroll.py` needs exclusive access, same as `tinytouch_helper.py`
does later.

- [x] **Step 2: Run the enroll script** — DONE (ENROLL_OK 1)

```bash
cd /Users/anildash/Developer/dashtouch
. .venv/bin/activate
.venv/bin/python software/macos-helper/tinytouch_enroll.py --port /dev/cu.usbmodemXXXX --slot 1
```

(Substitute the actual port; `arduino-cli board list` or Task 3's Serial
Monitor session shows it.)

Follow the printed prompts: place finger, lift it off, place the same
finger again.

Expected final output:
```
esp: ENROLL_OK 1
enrolled slot 1 successfully
```

- [ ] **Step 3: If it fails**

`esp: ENROLL_FAIL capture1` / `capture2` means the sensor didn't get a clean
read in time — retry, make sure the finger fully covers the sensing pad.
`esp: ENROLL_FAIL regmodel` means the two captures didn't match closely
enough — retry with more consistent finger placement. `no response to
ENROLL command` means the board isn't running this firmware, or the wiring
from Task 3 is off — recheck TX/RX aren't swapped.

---

### Task 5: Flash tinyTouch firmware with real secrets and verify end-to-end match

**Files:**
- Modify (untracked, git-ignored): `firmware/tiny_touch_keyboard/secrets.h`

**Interfaces:**
- Consumes: pairing key from Task 1 Step 3 (Keychain), pin remap from
  Task 2, enrolled fingerprint from Task 4 (slot 1).

- [x] **Step 1: Confirm secrets.h is git-ignored** — DONE

```bash
git check-ignore -v firmware/tiny_touch_keyboard/secrets.h
```

Expected: prints a matching `.gitignore` rule. If it prints nothing, STOP
and add `firmware/tiny_touch_keyboard/secrets.h` to `.gitignore` before
proceeding, so the real password/pairing-key-adjacent file is never
committed.

- [x] **Step 2: Write the real pairing key into secrets.h** — DONE

Edit `firmware/tiny_touch_keyboard/secrets.h`, replacing the all-zero
`PAIRING_KEY` array with the 32 bytes from the hex string generated in
Task 1 Step 2 (each pair of hex characters becomes one `0xNN` entry, in
order). Example if the generated key started `a1b2c3...`:

```cpp
static const uint8_t PAIRING_KEY[32] = {
  0xa1, 0xb2, 0xc3, /* ...remaining 29 bytes... */
};
```

- [x] **Step 3: Re-flash tiny_touch_keyboard.ino** — DONE

In Arduino IDE, re-open `tiny_touch_keyboard.ino` (from Task 2's edits),
Upload again. Open Serial Monitor at 115200 baud.

Expected:
```
BOOT tinyTouch HID
READY
```

- [x] **Step 4: Start the macOS helper** — DONE

In a terminal:

```bash
cd /Users/anildash/Developer/dashtouch
. .venv/bin/activate
.venv/bin/python software/macos-helper/tinytouch_helper.py
```

Expected: the helper starts and connects to the ESP32's serial port without
error (leave it running).

- [x] **Step 5: Touch the enrolled finger to the sensor** — DONE (TYPED)

Expected sequence in the ESP32's Serial Monitor:
```
TOUCH
MATCH 1 <score>
TYPED
```

(`<score>` is a match-confidence number; any non-zero `TYPED` result means
success.)

Expected effect: click into any text field on the Mac (e.g. Notes, or a
password prompt) before touching the sensor — the real password should be
typed into it. Immediately clear that field.

- [ ] **Step 6: Verify a non-enrolled finger is rejected**

Touch a different finger (not enrolled in Task 4). Expected:
```
TOUCH
NO_MATCH
```
No password should be typed.

- [ ] **Step 7: Install the helper as a launchd agent**

```bash
mkdir -p ~/Library/LaunchAgents
cp software/macos-helper/launchd/com.tinytouch.helper.plist ~/Library/LaunchAgents/
```

Edit `~/Library/LaunchAgents/com.tinytouch.helper.plist` so any path
references point at `/Users/anildash/Developer/dashtouch` and your `.venv`
python binary, then:

```bash
launchctl unload ~/Library/LaunchAgents/com.tinytouch.helper.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.tinytouch.helper.plist
```

- [ ] **Step 8: Verify the launchd agent works**

Disconnect and reconnect the ESP32 (or unplug/replug USB), then touch the
enrolled finger again without manually running the helper script. Expected:
same `TOUCH` / `MATCH` / `TYPED` sequence as Step 5, driven by the
background agent. Check logs if it doesn't work:

```bash
cat /tmp/tinytouch-helper.log
cat /tmp/tinytouch-helper.err
```

---

## Deferred (explicitly not part of this plan)

- Secure boot / flash encryption (design spec: one-way eFuse burn, do only
  after the above is fully working and stable — not part of this build
  cycle).
- Wood enclosure design/build (user-driven, out of scope per design spec).
- PIV/PAM firmware, composite HID+PIV firmware, DFRobot flush-sensor route
  (all explicitly deferred in the design spec).
