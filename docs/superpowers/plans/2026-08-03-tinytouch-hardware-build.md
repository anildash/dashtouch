# tinyTouch Hardware Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get a QT Py ESP32-S3 + ZW101 fingerprint sensor running tinyTouch's
HID ("red pill") firmware end-to-end on a breadboard — fingerprint touch
types the real macOS password — before any enclosure work begins.

**Architecture:** Existing `tiny_touch_keyboard.ino` firmware talks to the
fingerprint sensor over UART using the `0xEF01` packet protocol and to macOS
over USB HID (as a keyboard) plus USB CDC (serial link to a Python helper
daemon that holds the real password in Keychain). The only code change
needed is remapping three GPIO pin constants, since the QT Py ESP32-S3
doesn't expose the pins the firmware currently hardcodes. Fingerprint
templates live on the sensor's own flash, not the ESP32 — enrollment must
happen via a separate one-off sketch before the tinyTouch firmware can match
anything, since tinyTouch's own firmware has no enroll routine.

**Tech Stack:** Arduino IDE (ESP32 board package), C/C++ (`.ino`), Python 3
(macOS helper), macOS Keychain.

## Global Constraints

- Board: Adafruit QT Py ESP32-S3, 8MB flash / no PSRAM (#5426).
- Arduino IDE board settings: `USB CDC on Boot: Enabled`, `USB Mode: USB-OTG`
  (from `firmware/tiny_touch_keyboard/README.md`).
- Fingerprint sensor: ZW101, UART at 57600 baud, `0xEF01` packet header.
- Never commit `firmware/tiny_touch_keyboard/secrets.h` (already covered by
  the repo's existing guidance; verify `.gitignore` before creating it).
- Do not enable secure boot / flash encryption during this plan — those are
  one-way eFuse burns and are explicitly deferred until after the full
  enroll-match-type cycle is verified working (see design spec).

## Prerequisites

Before starting Task 1, have in hand: an Adafruit QT Py ESP32-S3 (#5426), a
ZW101 fingerprint sensor with its 6-pin cable, and a USB-C cable. These are
purchasing steps (see the design spec's Cost/BOM section for sourcing
links), not engineering tasks, so they aren't broken out below.

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

- [ ] **Step 1: Create the venv and install dependencies**

```bash
cd /Users/anildash/Developer/tinyTouch
python3 -m venv .venv
. .venv/bin/activate
pip install -r software/macos-helper/requirements.txt
```

Expected: `cryptography` and `pyserial` install with no errors.

- [ ] **Step 2: Generate a pairing key and record it**

```bash
openssl rand -hex 32 | tee /tmp/tinytouch-pairing-key.txt
```

Expected: a 64-character hex string printed and saved to
`/tmp/tinytouch-pairing-key.txt`. Keep this terminal/file open — Task 4
needs these exact bytes.

- [ ] **Step 3: Store the pairing key in Keychain**

```bash
.venv/bin/python software/macos-helper/tinytouch_helper.py \
  --set-pairing-key "$(cat /tmp/tinytouch-pairing-key.txt)"
```

Expected: command exits 0 with no error output.

- [ ] **Step 4: Store your real macOS password in Keychain**

```bash
.venv/bin/python software/macos-helper/tinytouch_helper.py \
  --set-password 'your-actual-mac-login-password'
```

Expected: command exits 0. Immediately clear this command from your shell
history (`history -d <line>` in zsh, or just don't worry about it if your
shell history isn't persisted/shared).

- [ ] **Step 5: Delete the plaintext pairing-key scratch file**

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

- [ ] **Step 1: Confirm current values**

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
static const int FP_INT_PIN = 18; // QT Py ESP32-S3 pin labeled A0
```

- [ ] **Step 3: Verify the edit**

```bash
grep -n "FP_TX_PIN\|FP_RX_PIN\|FP_INT_PIN" firmware/tiny_touch_keyboard/tiny_touch_keyboard.ino
```

Expected output includes:
```
14:static const int FP_TX_PIN = 5;   // QT Py ESP32-S3 pin labeled TX
15:static const int FP_RX_PIN = 16;  // QT Py ESP32-S3 pin labeled RX
16:static const int FP_INT_PIN = 18; // QT Py ESP32-S3 pin labeled A0
```

- [ ] **Step 4: Commit**

```bash
git add firmware/tiny_touch_keyboard/tiny_touch_keyboard.ino
git commit -m "$(cat <<'EOF'
Remap fingerprint sensor pins for QT Py ESP32-S3

GPIO 43/44/2 aren't broken out on this board; use the pins labeled
TX/RX/A0 instead (GPIO 5/16/18), routed via the ESP32-S3's UART
GPIO matrix.
EOF
)"
```

---

### Task 3: Wire the sensor and verify boot-time sensor detection

**Files:** None (hardware wiring + Arduino Serial Monitor observation only).

**Interfaces:**
- Consumes: pin assignments from Task 2 (`FP_TX_PIN=5`, `FP_RX_PIN=16`,
  `FP_INT_PIN=18`).

- [ ] **Step 1: Wire on a breadboard (power off)**

Connect, with the QT Py ESP32-S3 unpowered:
- ZW101 VCC → QT Py `3V` pin
- ZW101 GND → QT Py `GND` pin
- ZW101 TX → QT Py pin labeled `RX` (GPIO 16)
- ZW101 RX → QT Py pin labeled `TX` (GPIO 5)
- ZW101 interrupt/touch-out pin → QT Py pin labeled `A0` (GPIO 18)

(Sensor TX goes to board RX and vice versa — this is a standard UART
crossover, not a mistake to double check away.)

- [ ] **Step 2: Install the ESP32 board package and select the board**

In Arduino IDE: Boards Manager → install "esp32" (Espressif Systems), then
select **Tools > Board > Adafruit QT Py ESP32-S3**. Set:
```
USB CDC on Boot: Enabled
USB Mode: USB-OTG
```

- [ ] **Step 3: Create a placeholder secrets.h so the sketch compiles**

```bash
cp firmware/tiny_touch_keyboard/secrets.example.h firmware/tiny_touch_keyboard/secrets.h
```

(Task 4 fills in the real pairing key; an all-zero key is fine for this
wiring-only check.)

- [ ] **Step 4: Flash and open Serial Monitor**

In Arduino IDE, open `firmware/tiny_touch_keyboard/tiny_touch_keyboard.ino`,
click Upload, then open Serial Monitor at 115200 baud.

- [ ] **Step 5: Verify sensor detection**

Expected output within ~2 seconds of boot:
```
BOOT tinyTouch HID
READY
```

If you instead see:
```
BOOT tinyTouch HID
ERR fingerprint_verify
```
the sensor isn't responding — recheck TX/RX aren't swapped, recheck the
3V/GND connections, and confirm the sensor's LED lights up on power-on.

- [ ] **Step 6: Sanity-check the serial link**

In Serial Monitor's input box, type `PING` and send. Expected response:
```
PONG
```

---

### Task 4: Enroll a fingerprint

tinyTouch's own firmware has no enrollment routine — it only matches against
slots 1-5 (`START_SLOT`/`END_SLOT` in the `.ino`). Templates live in the
sensor's own flash, so enrollment is a one-time step done with a separate,
temporary sketch using the standard `Adafruit_Fingerprint` library, which
speaks the same `0xEF01` protocol.

**Files:**
- Create (temporary, not committed): a scratch Arduino sketch, e.g.
  `/tmp/tinytouch_enroll/tinytouch_enroll.ino`.

**Interfaces:**
- Produces: a fingerprint template stored in the ZW101's onboard flash at
  ID 1, which `tiny_touch_keyboard.ino`'s `scanMatch()` (searching slots
  1-5) will match against in Task 5.

- [ ] **Step 1: Install the Adafruit Fingerprint Sensor Library**

In Arduino IDE: Sketch > Include Library > Manage Libraries, search
"Adafruit Fingerprint Sensor Library", install it.

- [ ] **Step 2: Disconnect the QT Py from Arduino IDE / close Serial Monitor**

Close the Serial Monitor from Task 3 so it doesn't hold the port.

- [ ] **Step 3: Create the enrollment sketch**

Create `/tmp/tinytouch_enroll/tinytouch_enroll.ino`:

```cpp
#include <Adafruit_Fingerprint.h>

HardwareSerial fingerSerial(1);
Adafruit_Fingerprint finger(&fingerSerial);

uint8_t getFingerprintEnroll(uint8_t id) {
  int p = -1;
  Serial.println("Place finger on sensor...");
  while (p != FINGERPRINT_OK) {
    p = finger.getImage();
    switch (p) {
      case FINGERPRINT_OK: Serial.println("Image taken"); break;
      case FINGERPRINT_NOFINGER: Serial.print("."); break;
      default: Serial.println("Error taking image"); return p;
    }
  }
  p = finger.image2Tz(1);
  if (p != FINGERPRINT_OK) { Serial.println("Error converting image 1"); return p; }

  Serial.println("Remove finger");
  delay(2000);
  p = 0;
  while (p != FINGERPRINT_NOFINGER) p = finger.getImage();

  p = -1;
  Serial.println("Place same finger again...");
  while (p != FINGERPRINT_OK) {
    p = finger.getImage();
    switch (p) {
      case FINGERPRINT_OK: Serial.println("Image taken"); break;
      case FINGERPRINT_NOFINGER: Serial.print("."); break;
      default: Serial.println("Error taking image"); return p;
    }
  }
  p = finger.image2Tz(2);
  if (p != FINGERPRINT_OK) { Serial.println("Error converting image 2"); return p; }

  p = finger.createModel();
  if (p != FINGERPRINT_OK) { Serial.println("Prints did not match"); return p; }

  p = finger.storeModel(id);
  if (p == FINGERPRINT_OK) {
    Serial.println("Stored!");
  } else {
    Serial.println("Error storing model");
  }
  return p;
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  fingerSerial.begin(57600, SERIAL_8N1, 16, 5); // RX=16, TX=5 (matches Task 2 wiring)
  if (finger.verifyPassword()) {
    Serial.println("Sensor found");
  } else {
    Serial.println("Sensor NOT found - check wiring");
    while (1) delay(1000);
  }
}

void loop() {
  getFingerprintEnroll(1); // store into slot 1, within tinyTouch's 1-5 search range
  Serial.println("Enroll finished. Reset the board to enroll another finger, or upload a different sketch.");
  while (1) delay(1000);
}
```

- [ ] **Step 4: Flash and run enrollment**

Upload the sketch (same board/USB settings as Task 3), open Serial Monitor
at 115200 baud. Follow the printed prompts: place finger, remove, place
same finger again.

Expected final output:
```
Stored!
Enroll finished. Reset the board to enroll another finger, or upload a different sketch.
```

If you see `Sensor NOT found - check wiring`, recheck the wiring from
Task 3 — the pin assignments in this sketch (`fingerSerial.begin(57600,
SERIAL_8N1, 16, 5)`) intentionally match Task 2's remap.

---

### Task 5: Flash tinyTouch firmware with real secrets and verify end-to-end match

**Files:**
- Modify (untracked, git-ignored): `firmware/tiny_touch_keyboard/secrets.h`

**Interfaces:**
- Consumes: pairing key from Task 1 Step 3 (Keychain), pin remap from
  Task 2, enrolled fingerprint from Task 4 (slot 1).

- [ ] **Step 1: Confirm secrets.h is git-ignored**

```bash
git check-ignore -v firmware/tiny_touch_keyboard/secrets.h
```

Expected: prints a matching `.gitignore` rule. If it prints nothing, STOP
and add `firmware/tiny_touch_keyboard/secrets.h` to `.gitignore` before
proceeding, so the real password/pairing-key-adjacent file is never
committed.

- [ ] **Step 2: Write the real pairing key into secrets.h**

Edit `firmware/tiny_touch_keyboard/secrets.h`, replacing the all-zero
`PAIRING_KEY` array with the 32 bytes from the hex string generated in
Task 1 Step 2 (each pair of hex characters becomes one `0xNN` entry, in
order). Example if the generated key started `a1b2c3...`:

```cpp
static const uint8_t PAIRING_KEY[32] = {
  0xa1, 0xb2, 0xc3, /* ...remaining 29 bytes... */
};
```

- [ ] **Step 3: Re-flash tiny_touch_keyboard.ino**

In Arduino IDE, re-open `tiny_touch_keyboard.ino` (from Task 2's edits),
Upload again. Open Serial Monitor at 115200 baud.

Expected:
```
BOOT tinyTouch HID
READY
```

- [ ] **Step 4: Start the macOS helper**

In a terminal:

```bash
cd /Users/anildash/Developer/tinyTouch
. .venv/bin/activate
.venv/bin/python software/macos-helper/tinytouch_helper.py
```

Expected: the helper starts and connects to the ESP32's serial port without
error (leave it running).

- [ ] **Step 5: Touch the enrolled finger to the sensor**

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
references point at `/Users/anildash/Developer/tinyTouch` and your `.venv`
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
