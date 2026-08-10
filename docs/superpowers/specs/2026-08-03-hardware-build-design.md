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
| Fingerprint sensor (primary) | ZW101 capacitive semiconductor sensor (spec'd) — actual part received was a **ZW111** | Same sensing-tech family as Touch ID (capacitive, not optical/lensed). Tiny bare module (~1x1x1cm, φ21mm bezel, 1.0mm-pitch 6-pin connector), suited to flush-mounting. This is the sensor family the firmware's UART protocol (`0xEF01` header, 57600 baud) was written against. The ZW111 differs from the ZW101 in pinout — see Firmware section — but shares the same `0xEF01` command protocol family (confirmed compatible with the Adafruit Fingerprint Sensor library, which is hardcoded to that header/checksum format), so no firmware protocol rewrite is expected. **No cable ships with the sensor** — source a separate 1.0mm-pitch 6-pin cable (search "1.0mm pitch 6 pin cable", not "JST-PH", which is a different 2.0mm-pitch series some listings mislabel it as). In stock on Amazon (JMT ZW101, EC Buying ZW101), ships in ~4-5 days — actual part received may vary by listing/batch. |
| Fingerprint sensor (fallback) | R503 capacitive sensor | Same `0xEF01` protocol family, so also a firmware drop-in. Panel-mounts via a threaded M25 metal body and nut rather than sitting flush — fine in a drilled wood recess, but leaves a visible metal ring. Use only if ZW101/ZW111 sourcing becomes unreliable. In stock on Amazon and other electronics resellers. |
| Enclosure | Custom wood, built by the user | Not designed here. Mounting constraints to carry into that design: ZW101/ZW111 has a flat bezel (no threaded collar), so it mounts into a stepped recess (Forstner bit or CNC pocket sized to the bezel OD and body height) and is secured with flexible adhesive (E6000, hot glue) or a friction-fit/printed retaining ring — not screwed down. **The sensing pad should stay exposed or be covered only by a thin glass/acrylic window, not a wood veneer** — capacitive sensing is validated against uniform dielectric covers (glass/sapphire, ~0.3-0.5mm) in every commercial implementation; wood's grain inconsistency and moisture sensitivity make it a poor, unvalidated capacitive window, likely to cause unreliable or grain-position-dependent matching. R503 needs a drilled through-hole sized for its M25 threaded body plus the retaining nut. |
| Case STL files in repo | Not used | `hardware/case/case_top.stl` / `case_bottom.stl` were sized for the original author's Seeed ESP32-S3 board and are superseded by the custom wood enclosure. |

## Cost (BOM) vs. buying Touch ID

Prices checked live (Adafruit/Amazon/Apple/eBay) as of this spec's date.

| Item | Price | Source |
| --- | --- | --- |
| QT Py ESP32-S3 (#5426) | $12.50 | [adafruit.com](https://www.adafruit.com/product/5426) |
| ZW101 sensor (JMT, Combo A) | $11.58 | [Amazon](https://www.amazon.com/JMT-Fingerprint-Identification-Capacitive-Semiconductor/dp/B0CWTR6MND) |
| **Core electronics total** | **~$24** | |
| Apple Magic Keyboard with Touch ID, new (no numpad) | $149.00 | [apple.com](https://www.apple.com/shop/product/mxck3ll/a/) |
| Apple Magic Keyboard with Touch ID, used (no numpad) | ~$55-65 | live eBay listings; numpad versions run $110-180 used |

The core electronics land around $24, roughly 84% below new retail and
roughly 60% below the going used price. Enclosure cost (wood, hardware) is
not counted, since the user is sourcing/building that independently.

Adafruit does not currently stock a round fingerprint sensor (#4651 R503 and
#4750 Ultra-Slim Round are both out of stock at spec time; their only
in-stock sensor, #4690, is a $19.95 rectangular optical module that would
push the total to ~$32 and drop the Touch-ID-round aesthetic). Given the
cost and shape goals, the ZW101 (sourced via Amazon, not Adafruit) is the
call for the sensor; the MCU remains Adafruit-sourced.

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
static const int FP_INT_PIN = 8;  // labeled A3
```

(An earlier draft of this spec used A0/GPIO18 for the interrupt pin. The
committed firmware and the physical build both use A3/GPIO8 instead — either
free pin works electrically, but A3 is what's actually soldered and what
`tiny_touch_keyboard.ino` now hardcodes, so treat A3 as authoritative.)

Apply the same remap to `firmware/tiny_touch_smartcard/main/fingerprint.c`
if the PIV/PAM firmware is ever revisited later — it hardcodes the identical
three constants.

### ZW111 pinout (differs from firmware's 3-wire assumption)

The firmware only wires TX/RX/INT. The ZW111's connector exposes 6
functionally distinct pins. Confirmed against the manufacturer's own
datasheet (Shenzhen Hi-Link, "ZW111 Semiconductor Fingerprint Processing
Module Specification" V1.2, §4 — supersedes the earlier Amazon-reviewer pin
guess, which had VCC and Enable/VCC swapped):

| Pin | Signal | Note | QT Py pin | Wire color |
| --- | --- | --- | --- | --- |
| 1 | V_SENSOR | 3.3V, **must stay powered at all times** | `3V` | Red |
| 2 | TOUCH_OUT | wake IRQ (1 = touch true, 0 = false) | `A3` (GPIO 8) | White |
| 3 | VCC | fingerprint module VCC — this is the pin to gate for low-power control | `3V` (separate wire from pin 1, same header pin) | Red |
| 4 | TX | module → MCU | `RX` (GPIO 16) | White |
| 5 | RX | MCU → module | `TX` (GPIO 5) | Green |
| 6 | GND | | `GND` | Black |

The firmware has no code path for V_SENSOR. Tie pin 1 to a constant 3.3V
rail; VCC (pin 3) is the one the datasheet's own low-power reference design
gates via a client MCU I/O pin (R1/R2/Q1/Tr1 level-shift circuit, §5) if
power-gating is ever wanted — not required for this build. TOUCH_OUT (wake
IRQ) connects to A3 since that's the interrupt pin `tiny_touch_keyboard.ino`
now hardcodes (`FP_INT_PIN = 8`) and polls via `fingerPresent()`.

The "Wire color" column is not vendor-specified — the sourced wiring kit is
generic crimp-pin stock with no datasheet color code. This build's
convention is to color each sensor-side wire to match the color of the QT
Py header pin it lands on (already soldered per the header's own scheme:
black=ground/spare, red=power, blue=SDA, yellow=SCL, green=TX, white=RX/INT),
so the whole electrical path reads as one consistent color end to end
rather than inventing a second, disconnected color code for the sensor
harness. Two wires land on the QT Py's single `3V` pin (V_SENSOR and VCC) —
that's intentional, not a wiring error to consolidate down to one wire.
Regardless of color choice, physically label pin 1 vs. pin 6 on the
connector housing, since the sensor's connector is keyed/directional and
colors alone won't self-document the pinout to someone reading the finished
build later.

**Protocol confirmed, not just likely-compatible:** Hi-Link's companion
document, "Fingerprint module product user communication protocol" V1.1,
is the vendor's own protocol spec (not Adafruit-library-inferred) and
describes the exact framing this firmware hand-rolls in `scanMatch()`:
`0xEF01` 2-byte header, 4-byte device address defaulting to `0xFFFFFFFF`,
1-byte package ID (01=command, 02=data, 08=end-data), 57600 baud default
(settable 9600-115200), and the same confirmation-code table (`00H`=OK,
`08H`=mismatch, `09H`=not found, etc.). This lines up with the firmware's
protocol assumptions closely enough that command-level compatibility is
expected, not just likely — but still confirm with a real enroll/match cycle
before spending more time on the enclosure, since minor command-set gaps
between sensor SKUs are still possible.

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
