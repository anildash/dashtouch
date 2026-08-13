# Checkpoint — 2026-08-13

Written immediately before a planned refactor that will re-found this project
on different base assumptions than the upstream tinyTouch code it was forked
from. Purpose: capture everything true right now, and — more importantly —
**separate what is durable hardware/protocol fact from what is an inherited
tinyTouch design assumption that the refactor is free to discard.**

Read §4 and §5 together. That split is the whole point of this document.

---

## 1. Status in one paragraph

**The device works end to end.** Touching an enrolled finger to the sensor
types the real macOS login password via USB HID. This was achieved on
2026-08-13 after a multi-session debugging arc in which two different
fingerprint sensors were wrongly diagnosed as defective. Everything in the
"red pill" (HID) path is verified on real hardware. The "blue pill"
(PIV/PAM) path is untouched upstream code and has never been exercised in
this build. The enclosure is fully designed on paper and not yet built.

Verified chain, observed repeatedly:

```
TOUCH → MATCH 1 142 → EV <nonce> <ctr> <slot> <score> <hmac>
      → sent encrypted password → EV_SENT → TYPED
```

---

## 2. Hardware state (as physically wired right now)

| Item | Value |
| --- | --- |
| MCU | Adafruit QT Py ESP32-S3, 8MB flash / **no PSRAM** (#5426) |
| Sensor | Unbranded R503-class capacitive module |
| Sensor sourcing | Amazon ASIN `B08HM8QDVW`, internal SKU `X003GFZ101`, ~$29.91 |
| Sensor self-report | capacity **200** templates, security level 3, packet size 128, baud reg 6 (57600), address `0xFFFFFFFF` |
| UART | 57600 8N1 |
| Connection | Breadboard + clip leads (not soldered, not enclosed) |
| Enrolled | Slot 1, one finger |

### Authoritative wiring table

**All six wires are required.** Pin 6 is not optional — see §6.1.

| Sensor pin | Signal | Wire | → QT Py pad | GPIO | Our role |
| --- | --- | --- | --- | --- | --- |
| 1 | Power 3.3V | red | `3V` | — | — |
| 2 | GND | black | `GND` | — | — |
| 3 | TXD | yellow | **`TX`** | 5 | our **receive** |
| 4 | RXD | brown | **`RX`** | 16 | our **transmit** |
| 5 | WAKEUP | blue | `A3` | 8 | wired but **unused** |
| 6 | 3.3VT | white | `3V` (2nd wire) | — | **mandatory** |

Two things that look like errors and are not:

- **Yellow and brown land on pads whose silkscreen labels contradict their
  function.** GPIO 5 cannot carry UART transmit on this board (§6.3), so the
  roles are deliberately swapped. Do not "fix" this to match the labels.
- **Two wires share the single `3V` pad** (pins 1 and 6).

### Build settings

```
FQBN: esp32:esp32:adafruit_qtpy_esp32s3_nopsram:CDCOnBoot=cdc,USBMode=default
```

(CLI equivalent of `USB CDC on Boot: Enabled` + `USB Mode: USB-OTG`.)

### Firmware constants that matter

```c
static const int FP_TX_PIN = 16;   // pad labeled RX — deliberate
static const int FP_RX_PIN = 5;    // pad labeled TX — deliberate
static const int FP_INT_PIN = 8;   // pad labeled A3 — wired, unused
static const bool USE_INT_PIN = false;  // poll GenImg instead
```

---

## 3. Software / host state

| Piece | State |
| --- | --- |
| Helper daemon | `software/macos-helper/tinytouch_helper.py`, runs in foreground, works |
| launchd agent | plist exists at `software/macos-helper/launchd/`, **not installed** |
| Keychain — password | present (service `tinyTouch`) |
| Keychain — pairing key | present (service `tinyTouch-pairing`) |
| Keychain account name | `PREFERRED_SERIAL` = `68EE8F6E7390` (the board's serial, **not** the string `tinyTouch`) |
| `secrets.h` | present, gitignored, pairing key matches Keychain (`--self-test ok`) |
| Enrollment tool | `tinytouch_enroll.py`, works |

**Gotcha worth keeping:** the Keychain entries are keyed on the *board
serial*, so `security find-generic-password -a tinyTouch ...` returns nothing
and looks like the entry is missing. Query with the serial as the account.

**Gotcha worth keeping:** only one process may hold the serial port. The
helper, the enroll script, and `capture.py` are mutually exclusive.

---

## 4. Durable knowledge — survives any refactor

This is hardware and protocol truth. It is independent of tinyTouch's
architecture and should carry forward verbatim.

### 4.1 `3.3VT` (sensor pin 6) must be powered

With it unconnected, the module powers up, receives commands, and **executes**
them — the aura ring visibly obeys `OFF` and `RED` — but cannot reply to
anything. Every diagnostic then reads as a dead sensor. This single wire
accounts for this project's entire "defective sensor" history. ESPHome's Grow
component documents the same requirement.

### 4.2 This QT Py cannot transmit UART on GPIO 5

Proven by board-only loopback with a single `TX`↔`RX` jumper and no sensor:

```
rx=16 tx=5   sent=8  received=256  bytes=0000...   (line held low)
rx=5  tx=16  sent=8  received=8    bytes=ef01a55a00ff427e
```

GPIO 5 receives fine and drives fine at DC. Root cause unconfirmed; a reflow
of the joint changed nothing. **Routed around, not fixed.** Reproduced again
on a second machine on 2026-08-13.

### 4.3 `ReadSysPara` (0x0F) is the only model ID an unbranded module gives

```
ef01 ffffffff 07 0013 00  0004 0000 00c8 0003 ffffffff 0002 0006  04ed
                          status  id  cap  sec   addr   pkt  baud
```

`cap=0x00c8` = 200 templates. Run this first on any new sensor.

### 4.4 The `0xEF01` protocol works, hand-rolled

Raw packet construction (header `EF01`, 4-byte address, type, length,
payload, 16-bit checksum) is verified against this module for `VerifyPassword`
(0x13), `ReadSysPara` (0x0F), `AuraLedConfig` (0x35), `GenImg` (0x01),
`Img2Tz` (0x02), `RegModel` (0x05), `Store` (0x06), `Search` (0x04),
`LoadChar` (0x07), `Match` (0x03). No library required.

This module accepts **both** `0x35` and the legacy `0x3c` for LED control.

### 4.5 The board only transmits when the host asserts DTR

ESP32-S3 native USB CDC stays mute otherwise. A board with DTR low is
indistinguishable from a dead one. `capture.py` always asserts it; `screen`
and `cat` may not.

### 4.6 Diagnostic method that actually worked

1. Wire **all six** sensor wires before diagnosing anything.
2. `fp_loopback` — board UART sane? (no sensor involved)
3. `fp_probe` — raw `0xEF01`, no library. **Most trustworthy test.**
4. `fp_led` — does the sensor obey? (isolates host→sensor)
5. `fp_sweep` — baud/orientation sweep. **Positive results only.**

---

## 5. Inherited tinyTouch assumptions — all revisable

None of the following is load-bearing hardware fact. Each is a design choice
made upstream that this build adopted without re-deciding. The refactor should
treat every line here as an open question.

| Assumption | Where it lives | Note for the refactor |
| --- | --- | --- |
| **Password-typing over HID** is the auth mechanism | `tiny_touch_keyboard.ino` | The core security tradeoff. Types a real credential into whatever has focus. |
| **A host daemon holds the secret** in macOS Keychain | `tinytouch_helper.py` | Couples the device to macOS specifically. |
| **Shared-key HMAC pairing** between ESP32 and host | `secrets.h` + Keychain | Reasonable, but key lives in plaintext flash absent eFuse hardening. |
| **Templates live on the sensor's flash**, slots 1–5 | firmware `START_SLOT`/`END_SLOT` | Caps at 5 fingers arbitrarily; module holds 200. |
| **HID vs PIV as a either/or "red/blue pill"** | README, two firmware trees | The PIV tree is untouched and unverified here. |
| **Enrollment via serial commands** in the same firmware | `ENROLL`/`DELETE` | *Our addition*, not upstream. Works well. |
| **macOS-only** | helper, launchd, Keychain | Nothing in the hardware requires this. |
| **Arduino/`.ino` toolchain** for the HID path | `firmware/tiny_touch_keyboard/` | The PIV path uses ESP-IDF instead — the repo is already split-toolchain. |

---

## 6. Dead ends and corrected records

Documented so nobody re-walks them. Several of these were recorded as
*conclusions* in earlier docs and were wrong.

### 6.1 "The sensor is defective" — WRONG, twice

Both the ZW111 and the R503 were diagnosed as dead. The R503 is now proven
working. The ZW111 verdict is unsafe for two independent reasons: it was
tested through the dead GPIO 5 pad, *and* likely without its `V_SENSOR` pin
powered. **Set aside deliberately — not being retested now.**

### 6.2 "`trailing_bytes=0` proves the sensor never transmitted" — WRONG

`fp_sweep` calls `verifyPassword()`, which **consumes the reply internally**;
`trailing_bytes` counts only what arrived afterward. Zero is normal whether
the sensor answered or not. This metric is what condemned the ZW111.

A working sensor was observed returning `confirm=0x00` to a raw
`VerifyPassword` via `fp_probe` while `fp_sweep` simultaneously reported
`verifyPassword=fail trailing_bytes=0` on **all 14** combinations.

### 6.3 "Low idle voltage on sensor TX proves a damaged output stage" — WRONG

The working R503 measured **2.65V** on its TX line while `3.3VT` was unwired,
and was perfect once connected. The ZW111's 2.08V reading — the one piece of
evidence thought to independently condemn it — is no longer meaningful on its
own. Low idle voltage indicates an *unpowered* output stage.

### 6.4 The connector-orientation pullup test — did not work

The design spec prescribed measuring red↔brown vs white↔yellow for an
internal `RXD` pullup. **Both pairs read open.** The theory may not hold for
this module (the pullup likely sits behind the module's internal regulator).
Barrel-continuity fallback was also inconclusive.

**Orientation was ultimately settled by inference, not measurement:** the
sensor obeyed commands sent to the brown wire, so brown is RXD (pin 4), which
fixes the whole ribbon order. Cheaper and more reliable than the meter.

### 6.5 The WAKEUP/INT pin — abandoned

`USE_INT_PIN = true` made the firmware scan nonstop, every scan returning
`GENIMG_FAIL 2` ("can't detect finger"), because WAKEUP sat permanently at
the configured active level. Rather than chase polarity, the build switched to
`USE_INT_PIN = false`, polling `GenImg` — which uses the sensor itself as the
detector and is immune to that pin's behavior. Revisit only if idle power
draw matters.

### 6.6 The `0x55` power-on handshake — inconclusive, and moot

Prior art says `0x55` at power-on proves the sensor's TX is alive. We observed
scattered `0x55` bytes mixed with `0x00`s during hand power-cycling, argued
both "genuine handshake" and "contact-bounce noise," and never settled it.
It stopped mattering once `3.3VT` was connected and every command got a clean
ACK. **Don't spend time here.**

### 6.7 Stale pin assignments in diagnostics — silently tested nothing

`fp_boot_listen` and `fp_led` both hardcoded the pre-swap orientation
(transmit on the dead GPIO 5), so they were exercising nothing for an entire
session. Fixed. **Any sketch that hardcodes a single orientation must use
`rx=5, tx=16`.**

### 6.8 Amazon listing claims are not evidence

The listing's product photos were the basis for claiming the housing is
printed `1`/`6` — the actual part has no such markings. The same listing
claims 500-template capacity; the module self-reports 200. The physical label
says only "Capacitive Fingerprint Modul…" with no model number or brand.

---

## 7. Open items

| Item | Status |
| --- | --- |
| launchd agent install | Not done — helper needs a foreground terminal (plan Task 5 Steps 7–8) |
| Enclosure build | Designed in detail, **not built**. Two-piece plywood "L", 15° face, under-desk |
| Enclosure dimensions | Sensor figures still need caliper confirmation |
| Soldering / permanence | Everything is clip leads on a breadboard |
| Secure boot / flash encryption | Deliberately deferred — **one-way eFuse burn** |
| GPIO 5 root cause | Unconfirmed, routed around |
| ZW111 retest | **Deliberately set aside** |
| PIV/PAM path | Untouched upstream code, never exercised here |

---

## 8. Repo map — ours vs. upstream

Fork point: this build's work begins at `ba503cf` ("Add hardware build design
spec"). Everything before that is upstream tinyTouch.

**Written by this build:**

```
docs/history/2026-08-03-hardware-build-design.md   design + enclosure
docs/history/2026-08-03-tinytouch-hardware-build.md build plan
docs/history/r503-reference.md                prior art, driver libs
docs/history/2026-08-12-qtpy-uart-fault.md    UART fault investigation
firmware/diagnostics/                                        6 sketches + capture.py
software/macos-helper/tinytouch_enroll.py                    enrollment (not upstream)
```

**Upstream, modified by this build:**

```
firmware/tiny_touch_keyboard/tiny_touch_keyboard.ino   pins, LED bugs, ENROLL/DELETE
software/macos-helper/tinytouch_helper.py              PREFERRED_SERIAL corrected
```

**Upstream, untouched and unverified here:**

```
firmware/tiny_touch_smartcard/    PIV/PAM ("blue pill"), ESP-IDF, never built here
hardware/case/*.stl               sized for upstream author's board — superseded
README.md                         upstream's, describes both pills
```

---

## 9. Reproducing on a fresh machine

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

Per-machine, not in git:

- `firmware/tiny_touch_keyboard/secrets.h` — from `secrets.example.h`, pairing
  key must match Keychain.
- Keychain entries — `--set-pairing-key` and `--set-password`. **Run
  `--set-password` yourself**; it takes the real login password as an argument.
- `reference/` — ~16MB of cloned prior-art repos, gitignored. Re-clone per
  `docs/history/r503-reference.md`.

Verify with `--self-test`, then flash and look for a **purple ring**
(= `READY`, sensor handshake passed). Red = `ERR fingerprint_verify`.
