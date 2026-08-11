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
| Fingerprint sensor (in use) | **R503-compatible module**, brand "Simlug" ([Amazon, ASIN B08HM8QDVW](https://www.amazon.com/dp/B08HM8QDVW), ~$29.91) | Switched to after the originally-sourced ZW111 unit (see below) was diagnosed as defective/DOA. Same `0xEF01` command protocol family as the ZW101/ZW111 and identical pin table/connector to the genuine GROW R503 (confirmed from this listing's own product images: `Connector: MX1.0-6P`, pins 1-6 = Power Supply/GND/TXD/RXD/WAKEUP/3.3VT, exactly matching the GROW R503 manual) — so the R503 pinout table below applies as-is, no firmware changes needed. Ships with its own attached 6-pin cable, no separate cable sourcing needed (unlike the ZW111). |
| Fingerprint sensor (superseded) | ZW101 capacitive semiconductor sensor (spec'd) — actual part received was a **ZW111** | Originally chosen for its flush, bezel-less mounting. After extensive hardware debugging (see "ZW111 unit found defective" below), this specific unit never produced a valid protocol response under any wiring, baud rate, or connector tested, despite the firmware's protocol implementation being verified byte-for-byte correct against two independent reference implementations (Adafruit's Fingerprint Sensor Library and a ZW111-specific driver). Kept here for reference since the pin/wiring information may be useful if a replacement ZW111 is tried later. **No cable ships with the sensor** — source a separate 1.0mm-pitch 6-pin cable (search "1.0mm pitch 6 pin cable", not "JST-PH", which is a different 2.0mm-pitch series some listings mislabel it as). |
| Enclosure | Custom wood, built by the user | Not designed here. Mounting constraint for the R503-compatible module (now in use): it has a threaded metal body, so it needs a **drilled through-hole** sized for the threaded body plus a retaining nut on the back side — not a stepped recess. This produces a visible metal bezel around the sensing pad, similar in spirit to Touch ID's own metal ring, rather than a flush hidden mount. **Dimensions, from this exact listing's own product photos** (not the genuine GROW R503 datasheet — see discrepancy note below): front bezel/face diameter **27.8mm (1.1")**, body height **19mm (0.7")**, threaded shank diameter **16.5mm (0.6")** — drill the through-hole to the shank diameter (16.5mm plus a small clearance fit, confirm against the actual part with calipers before committing, since these figures are read off a marketing photo, not a certified drawing) and countersink/recess the front face by roughly the bezel-to-shank height difference if a flush-ish front is wanted. **The sensing pad should stay exposed or be covered only by a thin glass/acrylic window, not a wood veneer** — capacitive sensing is validated against uniform dielectric covers (glass/sapphire, ~0.3-0.5mm) in every commercial implementation; wood's grain inconsistency and moisture sensitivity make it a poor, unvalidated capacitive window, likely to cause unreliable or grain-position-dependent matching. (If a ZW101/ZW111 is used instead: flat bezel, no threaded collar, mounts into a stepped recess sized to the bezel OD and body height, secured with flexible adhesive or a friction-fit/printed retaining ring.) |
| Case STL files in repo | Not used | `hardware/case/case_top.stl` / `case_bottom.stl` were sized for the original author's Seeed ESP32-S3 board and are superseded by the custom wood enclosure. |

## Cost (BOM) vs. buying Touch ID

Prices checked live (Adafruit/Amazon/Apple/eBay) as of this spec's date.

| Item | Price | Source |
| --- | --- | --- |
| QT Py ESP32-S3 (#5426) | $12.50 | [adafruit.com](https://www.adafruit.com/product/5426) |
| R503 sensor | ~$10-20 depending on listing | Amazon / electronics resellers |
| **Core electronics total** | **~$23-33** | |
| ZW101/ZW111 sensor (JMT, Combo A) — superseded, unit received was defective | $11.58 | [Amazon](https://www.amazon.com/JMT-Fingerprint-Identification-Capacitive-Semiconductor/dp/B0CWTR6MND) |
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

### R503 pinout (sensor currently in use)

Confirmed two ways: against the genuine vendor's manual (Hangzhou Grow
Technology, "R503 Fingerprint Module User Manual" Ver 1.1), and
independently against the actual ordered listing's own product images
(Amazon ASIN B08HM8QDVW, brand "Simlug") — both show an identical pin table,
so this module is a compatible clone, not a different pinout. Connector is
MX1.0-6P — same family as the ZW111's, but **pin order is different, do not
reuse the ZW111 table above**:

| Pin | Signal | Note | QT Py pin | Wire color |
| --- | --- | --- | --- | --- |
| 1 | Power Supply | DC 3.3V | `3V` | Red |
| 2 | GND | Power supply and signal ground | `GND` | Black |
| 3 | TXD | Data output (module → MCU), TTL logic level | `RX` (GPIO 16) | White |
| 4 | RXD | Data input (MCU → module), TTL logic level | `TX` (GPIO 5) | Green |
| 5 | WAKEUP | Finger detection signal | `A3` (GPIO 8) | White |
| 6 | 3.3VT | Touch induction power supply, DC 3-6V, **must stay powered at all times** (same role as the ZW111's `V_SENSOR`) | `3V` (second wire, same header pin as pin 1) | Red |

Unlike the ZW111 build, **this sensor ships with its own factory-crimped
6-wire cable already attached** — there's no hand-wiring or color scheme to
choose here. Identify wires by **pin position**, not by re-deriving colors:
the connector housing itself is printed with "1" and "6" at either end (per
the ordered listing's own photo), so match the physical wire order at the
connector to the pin table above, then wire each into the matching QT Py
pin per the table (still crossing TX/RX, still landing two wires on the
single `3V` pin). Confirm the actual factory wire colors once the part is
in hand and update this table with what's actually observed, rather than
assuming the ZW111 build's colors carry over — they don't, since that
scheme was this build's own invention for a hand-built harness, not
anything vendor-specified.

Protocol confirmed directly from the vendor manual, not inferred: `0xEF01`
2-byte header (high byte first), 4-byte address defaulting to `0xFFFFFFFF`,
1-byte package identifier (`01`=command, `02`=data, `07`=acknowledge,
`08`=end of data), 2-byte length field, then payload, then a 2-byte checksum
that's the arithmetic sum of the package identifier, length, and all payload
bytes — byte-for-byte identical to the ZW111's protocol and to what
`tiny_touch_keyboard.ino`'s `fpCommand()` already implements. No firmware
changes are needed to switch sensors, only the wiring above.

### ZW111 unit found defective

The originally-received ZW111 unit was extensively debugged and never
produced a single valid protocol response. Ruled out, each confirmed by
direct measurement rather than assumption:

- Cable wire-to-wire shorts (continuity-checked, none found)
- QT Py board pad shorts, including reworked pads (continuity-checked, none)
- Pin order/orientation (verified against the real Hi-Link datasheet)
- Wire color scheme and physical pin-1 identification
- GND, both power wires, TX, and RX all making genuine continuity through
  their connectors (not just visually attached)
- Four baud rates tested (57600, 115200, 28800, 9600) — none produced a
  valid `0xEF01`-framed response, only inconsistent raw noise
- TX/RX physical separation, to rule out crosstalk between adjacent leads
- The firmware's protocol implementation itself, cross-checked byte-for-byte
  against two independent reference implementations (the Adafruit
  Fingerprint Sensor Library and a ZW111-specific driver on GitHub) — no
  discrepancies found in packet structure, checksum, or instruction codes
  (one unrelated bug was found and fixed: the LED/aura control command used
  `0x3c` instead of the correct `0x35`)

An intermittent power short was also found and fixed along the way (a
resoldered `3V` wire that had detached and was resting against the adjacent
`GND` pad) — but fixing it didn't restore communication, which is what
eventually pointed to the sensor itself being bad rather than the wiring.

**Final diagnosis — the sensor could hear us but could not answer.** A
follow-up session isolated the failure precisely:

| Observation | Conclusion |
| --- | --- |
| The Aura LED reliably obeys an `OFF` command (a state it will never enter on its own) | The sensor powers up, receives UART, parses packets, and executes commands — the **host→sensor** direction works |
| A sweep of the official `Adafruit_Fingerprint` library across 7 baud rates × both TX/RX orientations (14 combinations, software pin-swap via the ESP32 GPIO matrix) returned `trailing_bytes=0` every time | The sensor **never transmits a single byte** — not garbage, total silence. The earlier "garbage" bytes were noise on a floating line, not sensor data |
| The sensor's TX line idles at **2.08V** instead of 3.3V, measured with clean wiring | Below the ESP32's ~2.48V (0.75×VDD) logic-high threshold, so no valid idle-high or start bit can ever be detected |

The receive path survived and the transmit output driver did not — an unusual
but coherent partial failure. Note for future debugging: an idle UART line
sitting at neither ~3.3V (healthy) nor ~0V (shorted) but at some intermediate
voltage is a strong tell for a failed or under-driven output stage, and is
worth measuring early rather than after exhausting the wiring hypotheses.

Diagnostic sketches from this postmortem (`fp_sweep.ino`, a baud/orientation
brute-forcer built on the official library, and `fp_led.ino`, an LED-only
probe that tests the host→sensor direction in isolation) are described in
`docs/superpowers/references/r503-reference.md`.
Given the exhaustive elimination of every other explanation, and that this
was a $8.99 unit from a low-review-count listing (one of its four reviews
independently reported "absolutely unusable" out of the box), the sensor was
replaced with an R503 rather than continuing to debug this specific unit.

The firmware retains raw-byte debug logging (`DEBUG_FP_RAW_ON_FAIL` in
`tiny_touch_keyboard.ino`) added during this process, useful for diagnosing
any future sensor bring-up issue the same way.

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

1. Order QT Py ESP32-S3 and a fingerprint sensor (R503 in use now; ZW101/ZW111
   was tried first but the unit received was defective — see "ZW111 unit
   found defective" above).
2. Set up the macOS helper: generate pairing key, store password in
   Keychain, create `secrets.h`.
3. Edit `tiny_touch_keyboard.ino` pin constants per the remap above (already
   done, committed).
4. Wire the sensor to the QT Py per the R503 pinout above, breadboard first
   (before any enclosure work).
5. Flash firmware via Arduino IDE with the board settings above, use
   `software/macos-helper/tinytouch_enroll.py` to enroll a fingerprint, run
   the helper, verify a full enroll + fingerprint-match + password-type
   cycle.
6. Only after step 5 is fully working: consider enabling secure boot / flash
   encryption.
7. Design and build the wood enclosure around the validated electronics,
   using the mounting constraints noted in the Hardware table (through-hole
   + retaining nut for the R503's threaded body).

## Deferred / not in scope for this build

- PIV/PAM ("blue pill") smartcard mode.
- A combined HID+PIV composite USB firmware (technically possible via
  TinyUSB on ESP32-S3, but is new firmware engineering, not a documented
  path in this repo).
- DFRobot SEN0542/SEN0348 (ID809-protocol) flush sensor route — would
  require writing a new sensor driver to replace the `0xEF01` protocol
  layer; only worth revisiting if the R503's visible metal bezel turns out
  aesthetically unacceptable and a flush-mount sensor is wanted again.
- Enclosure/CAD design — the user is building this themselves.
