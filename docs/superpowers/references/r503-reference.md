# R503 sensor — reference material, driver code, and prior art

Gathered 2026-08-10, while the replacement R503-compatible sensor
(Amazon ASIN B08HM8QDVW) was in transit. Purpose: be able to plug the sensor
in and go, rather than re-researching from scratch.

Cloned repos live in `reference/` at the repo root, which is **gitignored** —
re-clone with the commands in "Local clones" below if the directory is empty.

---

## TL;DR — what to do the moment the sensor arrives

1. **Power it up before wiring anything to the UART pins.** The R5xx family
   emits a `0x55` handshake byte on its TX line at power-on. Seeing that byte
   proves the sensor's transmit path is alive — the exact thing the dead
   ZW111 could never do. This is the fastest go/no-go test on a new unit.
2. Wire per the pin table in the design spec (`2026-08-03-hardware-build-design.md`,
   "R503 pinout"). Identify wires by **connector position**, not color — the
   housing is printed `1` and `6` at the ends, and sellers vary the colors.
3. Flash the existing `firmware/tiny_touch_keyboard` — no protocol changes
   needed, the packet format is identical.
4. Enroll with `software/macos-helper/tinytouch_enroll.py --port ... --slot 1`.

Still outstanding before end-to-end works: the macOS password has **not** been
stored in Keychain yet (see plan Task 1 Step 4 — run it yourself, it takes
your real password as an argument).

---

## Canonical driver libraries

| Library | Why it matters | URL |
| --- | --- | --- |
| **Adafruit Fingerprint Sensor Library** | The canonical implementation for the whole R30x/R50x family. Our `fpCommand()` was verified byte-for-byte against it. Installed locally via `arduino-cli lib install "Adafruit Fingerprint Sensor Library"` (v2.1.4). Use it directly for any A/B sanity check against our hand-rolled code. | https://github.com/adafruit/Adafruit-Fingerprint-Sensor-Library |
| **R503Lib** (mpagnoulle) | ESP32-specific, R503-specific. **This is where the correct Aura LED semantics came from** — see "LED control" below. Cleaner enum definitions than Adafruit's. | https://github.com/mpagnoulle/R503-Fingerprint-Sensor-Library |
| **fingerprint-R503** (hkieninger) | ESP8266/Arduino-SDK library for the GROW R5xx family. Useful third opinion on packet handling. | https://github.com/hkieninger/fingerprint-R503 |
| ZW111 driver (LuongHuuPhuc) | The ZW111-specific driver used to verify our protocol during the dead-sensor debugging. Same `0xEF01` framing. Kept for reference only. | https://github.com/LuongHuuPhuc/ZW111_Fingerprint_Driver |

### Vendor documentation

- **R503 user manual (GROW/Hangzhou Grow Technology, Ver 1.1)** — the
  authoritative pin table and protocol spec:
  https://cdn-shop.adafruit.com/product-files/4651/4651_R503%20fingerprint%20module%20user%20manual.pdf
- Adafruit's R503 product page (same sensor, panel-mount version):
  https://www.adafruit.com/product/4651
- ZW111 datasheet (Hi-Link), for the superseded sensor:
  http://5.imimg.com/data5/SELLER/Doc/2025/7/532184999/NO/AJ/MR/1833510/hi-link-hlk-zw111-finger-print-module.pdf

---

## Prior art — projects built on this exact sensor

### linux-fingerprint-r503 (matpb) — closest analog to tinyTouch
https://github.com/matpb/linux-fingerprint-r503

**This is essentially tinyTouch for Linux**, and independently arrived at the
same architecture:

```
R503 --UART 57600--> MCU --USB CDC--> host daemon --> PAM
```

Notable parallels worth reading before writing the blog post:

- It also **MACs the MCU↔host link** (SipHash-2-4 with a TOFU-paired secret
  in EEPROM) for the same reason tinyTouch uses a pairing key + HMAC: the USB
  serial link is otherwise trivially spoofable.
- Its `SPEC.md` has an explicit threat-model section covering what the design
  does *not* protect against — a good model for tinyTouch's own security
  table in the README.
- It ships in a hand-cut wooden enclosure ("wish I had a 3d printer…"),
  same aesthetic direction as this build.
- BOM under $15, framed explicitly against the scarcity/expense of commercial
  Linux fingerprint readers — the same "why build this" framing as tinyTouch's
  "$149 Magic Keyboard" comparison.

Its `SPEC.md` §3.1 is the single most useful gotcha document found (see
"Gotchas" below).

### FingerprintDoorbell (frickelzeugs) — 383★, most popular R503 project
https://github.com/frickelzeugs/FingerprintDoorbell

ESP32 + R503 + MQTT doorbell. Most-starred R503 project on GitHub; good
reference for LED ring feedback patterns and for enrollment UX.

### Others worth a look

| Project | Notes | URL |
| --- | --- | --- |
| madmicio (ESP8266+MQTT+Home Assistant) | R502/R503, HA integration | https://github.com/madmicio/Fingerprints-reader-R503---R502-esp8266-mqtt-Home-Assistant |
| dnoegel/fingerprint-doorlock | ESP32 smart lock | https://github.com/dnoegel/fingerprint-doorlock |
| bkbilly/mqtt_fingerprint_pi | Python-side R503 driver (Raspberry Pi) | https://github.com/bkbilly/mqtt_fingerprint_pi |
| AlaisterLeung/r503-arduino | R503 + libfprint-tod virtual device | https://github.com/AlaisterLeung/r503-arduino |
| Dygear/r503 | Rust driver | https://github.com/Dygear/r503 |
| ESPHome `fingerprint_grow` component | Production-quality reference implementation of the whole command set | https://esphome.io/components/fingerprint_grow/ |

### Tutorials / write-ups (useful for blog-post framing and screenshots)

- ESP32 + R503 over hardware serial (Medium, Lakmina Gamage):
  https://lakminagamage.medium.com/esp32-with-r503-fingerprint-sensor-using-hardware-serial-communication-67caf00f9b78
- R503 RGB ring indicator with ESP32 (Medium, ProtoNest IoT):
  https://protonestiot.medium.com/r503-rgb-ring-indicator-fingerprint-module-with-esp32-3f7dd4978c30
- Interfacing R502/R503 with Arduino (how2electronics):
  https://how2electronics.com/interfacing-r502-r503-capacitive-fingerprint-sensor-with-arduino/
- Video walkthrough: https://www.youtube.com/watch?v=I-YitaulaWY
- Arduino Forum thread on the R503 specifically:
  https://forum.arduino.cc/t/adafruit-fingerprint-sensor-model-r503/943627

---

## Gotchas collected from prior art

These are other people's hard-won debugging lessons. Reading them cost
minutes; rediscovering them cost this project a full session.

1. **`0x55` on power-up means TX is alive.** From `linux-fingerprint-r503`
   SPEC §3.1: the sensor emits a handshake byte at power-on. If you see it
   but get no command responses, the fault is in the *host→sensor* direction,
   not the sensor. If you never see it, suspect the sensor or its TX path.
2. **Never put a voltage divider on the sensor's RX line.** The R503's RX has
   an internal pullup strong enough to fight a 1k/2k divider, leaving the line
   above the LOW threshold so no start bit is ever detected. Symptom: the
   `0x55` handshake arrives, but no command ever gets a reply. *Not relevant
   to our build* — the QT Py ESP32-S3 is natively 3.3V, so the sensor connects
   directly — but worth knowing if the wiring is ever adapted to a 5V board.
3. **Don't share the MCU's USB UART with the sensor.** On boards where the
   hardware UART is bonded to the USB-serial chip, sensor traffic and console
   traffic corrupt each other. *Also not an issue for us* — the QT Py's native
   USB is separate from the UART1 peripheral we route to GPIO 5/16.
4. **Wire colors vary by seller.** `linux-fingerprint-r503` explicitly warns
   that RXD is "brown, sometimes green depending on the seller — verify
   against the wire that goes into the RXD pin of the JST header, not the
   colour." Matches the position-not-color guidance in our design spec.
5. **Default baud is 57600**, settable as `9600×N`. Our firmware already
   matches.

### Observed real-world R503 wire colors

From `linux-fingerprint-r503`, for cross-checking once the part is in hand —
**verify by position before trusting these**:

| Sensor pin | Signal | Commonly-seen color |
| --- | --- | --- |
| 1 | VCC (3.3V) | Red |
| 2 | GND | Black |
| 3 | TXD | Yellow |
| 4 | RXD | Brown (sometimes green) |
| 5 | WAKEUP | Blue |
| 6 | 3.3VT (touch supply) | White |

---

## LED control — two bugs this research caught in our firmware

The R503's aura ring uses command `0x35` (`AuraLedConfig`). Verified against
`R503Lib.cpp`, which sends `SEND_CMD(0x35, control, speed, color, repeat)`.

**Bug 1 — wrong color constants.** Our firmware inherited color codes that
don't match the R5xx spec. Correct values:

| Value | Color |
| --- | --- |
| 1 | Red |
| 2 | Blue |
| 3 | Purple |
| 4 | Green |
| 5 | Yellow |
| 6 | Cyan |
| 7 | White |

The old firmware used green=`0x02` and red=`0x04`, which on an R503 render as
**blue** and **green** respectively. Fixed — purple (`3`) and white (`7`) were
already correct by coincidence.

**Bug 2 — wrong parameter order.** Our `setAura()` sent
`(control, color, color, 0)`. The correct order is
`(control, speed, color, repeat)`; the old code coincidentally landed the
color in the right slot but passed the color value as the *speed* byte. Fixed.

Control codes: `1`=breathing, `2`=flash, `3`=on, `4`=off, `5`=fade-in,
`6`=fade-out.

Both fixes are committed but **unverified against real hardware** — the LED
behavior is the first thing to sanity-check once the sensor is connected.

---

## Local clones

```bash
mkdir -p reference && cd reference
git clone --depth 1 https://github.com/adafruit/Adafruit-Fingerprint-Sensor-Library.git
git clone --depth 1 https://github.com/mpagnoulle/R503-Fingerprint-Sensor-Library.git
git clone --depth 1 https://github.com/matpb/linux-fingerprint-r503.git
git clone --depth 1 https://github.com/frickelzeugs/FingerprintDoorbell.git
git clone --depth 1 https://github.com/hkieninger/fingerprint-R503.git
```

The Adafruit library is also installed into the arduino-cli sketchbook
(`arduino-cli lib install "Adafruit Fingerprint Sensor Library"`), so it can
be `#include`d directly from a diagnostic sketch.

---

## Diagnostic sketch worth keeping

`fp_sweep.ino` (written during the ZW111 postmortem, in the session
scratchpad) brute-forces the official Adafruit library against the sensor
across **7 baud rates × both TX/RX orientations**, reporting both the
handshake result and the raw byte count received for each combination. It
needs no finger on the sensor and no rewiring — the ESP32's GPIO matrix
swaps TX/RX in software.

This is the single most useful "is this sensor alive at all?" test. It's
what produced the conclusive verdict on the ZW111: all 14 combinations
returned `trailing_bytes=0`, i.e. total silence rather than garbage, proving
the sensor never transmitted. Consider re-creating it under `firmware/` as a
permanent diagnostic if a third sensor is ever needed.

---

## Blog post angles surfaced by this research

- **The build is genuinely cheap**: ~$23-33 in core electronics versus $149
  for a new Magic Keyboard with Touch ID, ~$55-65 used.
- **The dead-sensor debugging arc** is a good story with a real lesson:
  every wiring hypothesis was eliminated by measurement, the protocol was
  verified against two independent reference implementations, and the answer
  was still "the part is broken." Worth writing up as a cautionary tale about
  cheap sensors from low-review listings, and about the value of a
  known-good reference implementation as a diagnostic tool.
- **Prior art convergence**: `linux-fingerprint-r503` independently arrived at
  the same architecture *and* the same MAC'd-link security model for the Linux
  desktop. Two people solving the same problem the same way is a good framing
  device for why the commercial options are unsatisfying.
- **The security tradeoff table** in the tinyTouch README (HID vs PIV/PAM) is
  the most interesting technical content in the project and deserves
  foregrounding — it's an honest accounting of the risks rather than a
  "look what I built" post.
