# tinyTouch hardware build — design

## Goal

Build a working tinyTouch device: fingerprint unlock that types the user's
macOS password after a match, in HID ("red pill") mode. The device will live
in a custom wooden enclosure (built by the user, out of scope for this spec),
mounted on their desk, aiming for a Touch ID-inspired look rather than a
visibly "kit parts" build. Parts are chosen to ship fast and be in stock now,
since this build will be written up as a blog post.

Out of scope for this design: PIV/PAM ("blue pill") mode, a combined
HID+PIV composite firmware, and enclosure/CAD design itself.

## Hardware

| Part | Choice | Why |
| --- | --- | --- |
| Microcontroller | [Adafruit QT Py ESP32-S3, 8MB flash / no PSRAM (#5426)](https://www.adafruit.com/product/5426) | Native USB and hardware UART, in stock, small footprint suits a custom wood enclosure. Does **not** expose the same GPIO pins the firmware currently hardcodes (see Firmware section). |
| Fingerprint sensor (primary) | ZW101 capacitive semiconductor sensor | Same sensing-tech family as Touch ID (capacitive, not optical/lensed). Tiny bare module (~1x1x1cm, 6-pin MX1.0 connector), suited to flush-mounting under a thin non-metal cover. This is the sensor the firmware's UART protocol (`0xEF01` header, 57600 baud) was written against — no protocol code changes needed. In stock on Amazon (JMT ZW101, EC Buying ZW101), ships in ~4-5 days. |
| Fingerprint sensor (fallback) | R503 capacitive sensor | Same `0xEF01` protocol family, so also a firmware drop-in. Panel-mounts via a threaded M25 metal body and nut rather than sitting flush — fine in a drilled wood recess, but leaves a visible metal ring. Use only if ZW101 sourcing becomes unreliable. In stock on Amazon and other electronics resellers. |
| Enclosure | Custom wood, built by the user | Not designed here. Mounting constraints to carry into that design: ZW101 needs a recess plus a thin non-metal cover over the sensing pad; R503 needs a drilled through-hole sized for its M25 threaded body plus the retaining nut. |
| Case STL files in repo | Not used | `hardware/case/case_top.stl` / `case_bottom.stl` were sized for the original author's Seeed ESP32-S3 board and are superseded by the custom wood enclosure. |

## Firmware

Use `firmware/tiny_touch_keyboard/tiny_touch_keyboard.ino` (HID/"red pill"
mode), built and flashed via Arduino IDE.

Board settings (from `firmware/tiny_touch_keyboard/README.md`, applies
regardless of which ESP32-S3 board is selected in Arduino IDE):

```text
USB CDC on Boot: Enabled
USB Mode: USB-OTG
```

### Required pin remap

The firmware hardcodes three pin constants for the fingerprint sensor's UART
and interrupt line:

```c
static const int FP_TX_PIN = 43;
static const int FP_RX_PIN = 44;
static const int FP_INT_PIN = 2;
```

GPIO 43, 44, and 2 are **not broken out** on the QT Py ESP32-S3 — that board
exposes a different pin set (labeled `A0`-`A3`, `SCK`, `MO`, `MI`, `RX`, `TX`,
`SDA`, `SCL`, `SCL1`, `SDA1`, `SS`, mapped to GPIO 18, 17, 9, 8, 36, 35, 37,
16, 5, 7, 6, 40, 41, 42 respectively). This is a mismatch from whatever board
the original author used (their README's wiring section, which itself
disagrees with their own firmware, references still other pins — see Known
discrepancies below).

Since the ESP32-S3's UART peripheral is routable to any GPIO via the internal
GPIO matrix, this is a small constant edit, not a redesign. Remap to the QT
Py's labeled pins:

```c
static const int FP_TX_PIN = 5;   // labeled TX
static const int FP_RX_PIN = 16;  // labeled RX
static const int FP_INT_PIN = 18; // labeled A0
```

Apply the same remap to `firmware/tiny_touch_smartcard/main/fingerprint.c`
if the PIV/PAM firmware is ever revisited later — it hardcodes the identical
three constants.

### Known discrepancies in the upstream repo

The top-level `README.md`'s wiring section says to wire the sensor to pins 6
and 7 (TX/RX) with the interrupt on pin 1. This does not match either
firmware file, which both hardcode TX=43, RX=44, INT=2. The firmware source
is authoritative; wire (and now remap) according to the code, not the README
table.

### Security hardening (explicitly deferred)

The README recommends enabling secure boot v2 and flash encryption on the
ESP32-S3, since the pairing key lives in `secrets.h` on the device. These are
chip-level (eFuse) features and work identically on the QT Py ESP32-S3 as on
any other ESP32-S3 board. However, burning these eFuses is **one-way and
irreversible** — do this only after the firmware is fully working and tested,
not while iterating on pin/wiring changes.

## Software

`software/macos-helper/tinytouch_helper.py`:

- Python 3 venv, dependencies from `software/macos-helper/requirements.txt`.
- Stores a pairing key and the user's real macOS password in the macOS
  Keychain (`--set-pairing-key`, `--set-password`).
- Same pairing key must be copied into `firmware/tiny_touch_keyboard/secrets.h`
  (created from `secrets.example.h`, never committed).
- Run persistently via `launchd`, using
  `software/macos-helper/launchd/com.tinytouch.helper.plist` (edit local
  paths before installing).

## Build sequence

1. Order QT Py ESP32-S3 and ZW101 sensor (R503 as fallback if ZW101 sourcing
   fails).
2. Set up the macOS helper: generate pairing key, store password in
   Keychain, create `secrets.h`.
3. Edit `tiny_touch_keyboard.ino` pin constants per the remap above.
4. Wire the sensor to the QT Py per the remapped pins, breadboard first
   (before any enclosure work).
5. Flash firmware via Arduino IDE with the board settings above, run the
   helper, verify a full enroll + fingerprint-match + password-type cycle.
6. Only after step 5 is fully working: consider enabling secure boot / flash
   encryption.
7. Design and build the wood enclosure around the validated electronics,
   using the mounting constraints noted in the Hardware table.

## Deferred / not in scope for this build

- PIV/PAM ("blue pill") smartcard mode.
- A combined HID+PIV composite USB firmware (technically possible via
  TinyUSB on ESP32-S3, but is new firmware engineering, not a documented
  path in this repo).
- DFRobot SEN0542/SEN0348 (ID809-protocol) flush sensor route — would
  require writing a new sensor driver to replace the `0xEF01` protocol
  layer; only worth it if ZW101's flush mounting turns out insufficient.
- Enclosure/CAD design — the user is building this themselves.
