# Dashboard Touch — design

**Date:** 2026-08-13
**Status:** approved (brainstorming session, section-by-section)
**Supersedes:** the tinyTouch-derived project direction. The working tinyTouch
build is preserved in git history and remains flashable until the parity gate
(§12) passes.

---

## 1. What Dashboard Touch is

Dashboard Touch is a way to get Touch ID-style convenience on a Mac without
buying Apple's $149 Touch ID keyboard. A small fingerprint sensor — mounted
wherever you like — types your password for you when an authentication prompt
appears.

- **Mechanism:** fingerprint match on the sensor → signed event to a Mac
  helper → helper returns the password encrypted for that one event → device
  types it over USB HID and wipes it from memory.
- **Hardware:** the common R503 fingerprint sensor (~$10–20) and the Adafruit
  QT Py ESP32-S3 (~$12.50). Both cheap, easy to source, easy to program, with
  active communities.
- **Mounting:** users build or adapt their own housing. The sensor is a
  ~28mm-flange, M25-threaded (~1") panel-mount part; anywhere it fits, it
  works. This is a feature of the project, not a gap.
- **Security:** typing your real password has real tradeoffs. They are
  enumerated honestly in `security.md`, in plain language, before anyone
  spends money.

Fork lineage: Dashboard Touch is an extensive refactor of
[tinyTouch](https://github.com/ZimengXiong/tinyTouch), credited in the
README. MIT license carries over. Repo remains `anildash/dashtouch`.

## 2. Decisions of record

| Decision | Choice |
| --- | --- |
| PIV/smartcard ("blue pill") tree | **Deleted.** HID-only, single-purpose project |
| Refactor depth | **Ground-up rewrite**; inherited code is reference only |
| Firmware foundation | **Arduino via arduino-cli** |
| Host helper | **Python** |
| Config/enrollment UI | **Web UI served by the helper on localhost** — the device never gets WiFi |
| Device↔host protocol | **Existing scheme kept, re-implemented cleanly from a written spec** |
| Execution | **In-place rewrite with a parity gate** (Approach 1): legacy stays flashable until the new stack passes end-to-end on real hardware |
| Documentation voice | **Consumer-level, friendly** — written for someone who reads The Verge, not datasheets |

## 3. Base assumptions, re-founded

The checkpoint (`docs/checkpoint-2026-08-13.md` §5) enumerated every
inherited tinyTouch assumption. Their dispositions:

| Inherited assumption | Dashboard Touch disposition |
| --- | --- |
| HID password-typing is the mechanism | **Kept** — it is the product |
| Host daemon + Keychain on macOS | **Kept** (macOS-only remains) |
| Shared-key HMAC pairing | **Kept**, spec'd normatively (§7) |
| Templates on sensor flash, slots 1–5 | **Slots 1–200** — the 5-slot cap is dropped; the sensor holds 200 |
| HID vs PIV "red/blue pill" split | **Gone** — one mode, one firmware |
| Enrollment via serial commands | **Kept** as transport, driven by the web UI |
| Arduino toolchain | **Kept** (arduino-cli; PIV's ESP-IDF tree deleted) |
| Pins swapped for a faulty board | **Reverted to silkscreen defaults** (§5); the swap becomes a documented troubleshooting path |

Durable hardware knowledge (checkpoint §4) carries forward verbatim: 3.3VT
is mandatory; hand-rolled `0xEF01` works; `ReadSysPara` is the model ID;
DTR must be asserted; the diagnostic ordering that actually worked.

## 4. Repo end-state

```
README.md                  consumer-voice: what/why/cost/quickstart/mounting
LICENSE
setup                      guided setup script (thin wrapper on `dashtouch setup`)
firmware/
  dashtouch/               the one firmware (Arduino sketch dir)
    dashtouch.ino          state machine + setup/loop
    r503.h/.cpp            sensor driver (hand-rolled 0xEF01)
    link.h/.cpp            host link: serial commands + match-event protocol
    config.h               pins, baud, detection mode (checked in)
    secrets.h              pairing key (gitignored); secrets.example.h template
  diagnostics/             kept as-is — proven bring-up/repair suite
helper/
  dashtouch_helper/
    daemon.py              long-running process; sole owner of the serial port
    serial_link.py         port discovery, DTR, line framing
    protocol.py            HMAC verify + one-time encrypted response
    keychain.py            password + pairing key, keyed on board serial
    webui.py               localhost HTTP: static pages + JSON API
    cli.py                 the `dashtouch` command
  web/                     static HTML/JS/CSS (no framework)
docs/
  protocol.md              normative wire-protocol spec with test vectors
  security.md              plain-English first, detail below
  troubleshooting.md       distilled from this project's dead ends
  history/                 checkpoint, UART-fault record, old specs/plans
```

**Deleted at the parity gate, not before:** `firmware/tiny_touch_keyboard/`,
`firmware/tiny_touch_smartcard/`, `software/macos-helper/`,
`hardware/case/` (upstream STLs for a different board), and the old README
content.

## 5. Firmware design

**Structure.** One sketch, split into focused files (Arduino compiles all
`.cpp` in the sketch directory). No Adafruit fingerprint library: the
hand-rolled protocol is the implementation verified byte-for-byte on real
hardware, and the library was shown to obscure failures (`trailing_bytes`).

**Sensor driver (`r503.h/.cpp`).** Commands: `VerifyPassword`, `ReadSysPara`,
`GenImg`, `Img2Tz`, `RegModel`, `Store`, `DeleteChar`, `Search`,
`AuraLedConfig`. Uniform packet builder/parser with checksum verification and
timeouts; every reply's confirmation code surfaced to the caller.

**State machine (`dashtouch.ino`).**
`IDLE → CAPTURE → SEARCH → MATCHED (request → type) → COOLDOWN → IDLE`,
plus `ENROLLING` entered via serial command from the helper.

**LED behavior — transitions only.** Aura commands fire on state changes,
never per poll iteration; redundant commands are suppressed. Idle is a
steady purple with no flicker (the inherited firmware strobed purple/white
while polling; that behavior is explicitly not carried forward).

**The LED language** (defined against this unit's verified palette — all 7
colors and all 4 animated modes render; other units should be surveyed with
`fp_colors` before trusting the full palette). Organizing logic: **red =
device-side problem, yellow = Mac-side problem**; red appears nowhere else.

| State | Ring |
| --- | --- |
| Idle, ready | Steady purple |
| Reading a finger | Steady white |
| Match / typed | Green flash ×2 → idle |
| No match | Red flash ×2 → idle |
| Helper unreachable (match event unanswered) | Steady yellow, cleared on next successful helper exchange |
| Enroll: place finger | Breathing white |
| Enroll: lift finger | Steady cyan |
| Enroll: place same finger again | Breathing white |
| Enroll: success | Green flash ×3 |
| Enroll: fail | Red flash ×3 |
| Sensor unreachable at boot | See below — the ring cannot be assumed reachable |

**Boot failure is signaled honestly.** The ring is on the sensor, driven
over the same UART that just failed — failure cannot be painted on hardware
the firmware can't reach. Three layers: (1) the firmware attempts steady
red anyway, which costs nothing and genuinely works in the most common
stranding failure (3.3VT unwired: the sensor receives but cannot reply);
(2) the documented diagnostic signal is the *absence of purple* — "if the
ring never turns purple, the sensor isn't talking"; (3) the QT Py's onboard
NeoPixel, which the sensor cannot take down, is normally off and turns
steady red when the sensor is unreachable, and the web UI Status page states
the condition in words.

**Pin defaults follow the silkscreen.** Transmit on GPIO 5 (pad `TX`),
receive on GPIO 16 (pad `RX`); sensor yellow→`RX`, brown→`TX` — the standard
crossover every tutorial shows. The original build's board cannot transmit
on GPIO 5, but that is a defective unit, not a systemic trait; a clean
project must not inherit one unit's scar as its default. The swap is a
one-line documented change in `config.h`, with `fp_loopback` as the
two-minute test for whether a board needs it. This project's own device
keeps the swapped values locally.

**Finger detection: polling by default.** `GenImg` polling works on every
module regardless of WAKEUP wiring or polarity. Blue→`A3` stays in the
standard wiring table; `config.h` offers optional interrupt mode with
configurable polarity. (The original build's "WAKEUP always active" reading
was plausibly an inverted-polarity misread; polling sidesteps the whole
question.)

**Wiring: all six wires, always.** 3.3VT (white) is called out in every
document as the wire whose absence makes a working sensor look dead.

**Config vs secrets.** `config.h` (checked in): pins, baud, detection mode,
LED colors. `secrets.h` (gitignored): pairing key only.

## 6. Helper design

One Python package, one process, **sole owner of the serial port** — 
enrollment and status flow through the daemon, structurally eliminating the
port-contention failures of the two-script layout.

**The web server is the local API.** Bound to `127.0.0.1` only. Static pages
plus a small JSON API; every mutating request requires a per-session random
token so a hostile browser tab or local curl can't drive enrollment. The CLI
uses the same API when the daemon runs, and may drive serial directly for
setup-time operations when it doesn't.

**CLI verbs:**

| Verb | Does |
| --- | --- |
| `dashtouch setup` | guided: deps check, pairing key, password (hidden prompt → Keychain; never argv), write `secrets.h`, detect board, offer flash, open enrollment |
| `dashtouch run` | the daemon (what launchd invokes) |
| `dashtouch enroll` | opens the browser to the Fingers page |
| `dashtouch doctor` | port discovery, DTR check, ring-color decoder, pointers into `firmware/diagnostics/` |
| `dashtouch install-agent` | writes + loads the launchd plist with correct absolute paths |

Keychain entries keyed on board serial (as today — supports multiple boards).
Dependencies: `pyserial`, `cryptography`, stdlib `http.server`. No web
framework.

## 7. Wire protocol (`docs/protocol.md`)

The proven scheme, written normatively; both ends implement from the
document. Shared test vectors let pytest prove the crypto without hardware.

- **Transport:** USB CDC, 115200, line-oriented ASCII frames, binary fields
  hex-encoded — human-readable in `capture.py` on purpose.
- **Pairing:** 32-byte key; Keychain on host, `secrets.h` on device.
- **Match event:** `EV <nonce16> <counter> <slot> <score> <hmac-sha256>`;
  HMAC over all preceding fields; counter strictly monotonic per boot.
- **Response:** password encrypted AES-256-GCM under a key derived from
  pairing key + event nonce; valid once; decrypted in RAM, typed, wiped.
- **Plaintext commands:** `PING/PONG`, `STATUS` (includes protocol version),
  `ENROLL <slot>` / `DELETE <slot>` + progress lines. These trigger nothing a
  person at the device couldn't do.
- **Versioning:** mismatches announce themselves via `STATUS`.
- **Test vectors:** key/nonce/counter → expected HMAC and ciphertext, in the
  spec; exercised by pytest and an optional firmware self-test build.

Out of scope, stated plainly: the sensor↔MCU UART is unauthenticated
(inherent to R503-class parts); physical flash access without eFuse
hardening exposes the pairing key. Both treated fully in `security.md`.

## 8. Web UI

Three pages, boring on purpose — plain HTML + fetch:

1. **Status** — device connected or not, firmware/protocol versions, sensor
   parameters from `ReadSysPara`, ring-color legend.
2. **Fingers** — the sensor's 200 slots as a simple list with helper-stored
   labels ("right index") in local JSON; Enroll walks place → lift → place
   with live progress mirrored from the serial stream; Delete per slot.
3. **Help** — the short-form troubleshooting: six wires (3.3VT first), DTR,
   ring colors, when to run `fp_loopback`.

## 9. Onboarding

The promise the repo is organized around: **buy two parts (~$25), wire six
leads, run one command, enroll in your browser.**

- **README:** what it is, what it costs (BOM links), a three-sentence honest
  security summary up top linking to `security.md`, the wiring table, the
  quickstart, and mounting patterns.
- **Mounting guidance, not product:** the R503's ~28mm flange / M25 (~1")
  threaded barrel is the spec; panel-mount into anything ≥16.5mm deep, or
  surface-mount with a collar. Sketched patterns (desk grommet, under-desk
  edge, enclosure wall, false drawer), framed as "yours to invent." One hard
  constraint carried from the enclosure research: **the sensing pad stays
  exposed** — no wood veneer or opaque covers on a capacitive sensor.
- **`./setup`:** idempotent, resumable; every step safe to re-run.

## 10. Documentation voice

All user-facing words — README, web UI copy, setup output,
troubleshooting — are written at a consumer level: friendly, plain-English,
no assumed jargon, the register of a good Verge explainer. Technical depth
is not deleted, it is *relocated*: `protocol.md` stays a normative spec;
`security.md` opens in plain English and puts the detailed material below;
`docs/history/` keeps the full forensic record.

## 11. Security documentation (`security.md`)

Opens with the plain-language truth: *this gadget types your real password,
same as if you typed it — that's why it works everywhere, and it's what you
should understand before building one.* Then the enumerated considerations:

- Wrong-field risk: the password goes wherever focus is.
- The sensor link: R503-class UART is unauthenticated and spoofable with
  physical access; epoxy potting as the folk mitigation.
- Flash dump: pairing key extractable without eFuse hardening; secure
  boot/flash encryption documented as the (one-way, deferred) fix.
- Localhost UI: what it exposes, why the session token exists.
- Replay/injection: what the nonce/counter/HMAC design does and doesn't stop.
- The honest paragraph upstream got right, rewritten in the new voice: when
  you should just buy the Apple keyboard instead.

## 12. Testing and the parity gate

**Host:** pytest for `protocol.py` against the spec vectors; keychain and
serial mocked for daemon logic. **Firmware:** `arduino-cli compile` gate on
every change; spec vectors in an optional self-test build; the
`firmware/diagnostics/` suite as the hardware harness. **End-to-end:** the
parity gate, on the real device:

1. Fresh flash boots to steady purple (no idle blinking)
2. `PING`/`PONG` and `STATUS` (with versions) over CDC
3. Enroll a finger entirely through the web UI
4. Enrolled finger → green ring → real password typed
5. Non-enrolled finger → red ring → nothing typed
6. Unplug/replug — daemon reconnects unaided
7. `dashtouch install-agent` → works with no terminal open
8. `./setup` runs start-to-finish on a machine without the venv

Only after all eight pass does one commit delete the legacy trees (§4) — 
and the repo *is* Dashboard Touch.

## 13. Build order

1. `docs/protocol.md` + `protocol.py` + pytest vectors
2. Firmware core: `r503` driver + state machine to steady-purple READY
3. Helper daemon to full match-and-type parity
4. Web UI enrollment
5. README, `security.md`, `troubleshooting.md`, `./setup` — in the voice
6. Parity gate on hardware → legacy deletion commit

## 14. Out of scope / deferred

- Secure boot / flash encryption (one-way eFuse burns) — documented, not
  performed.
- ZW111 retest — deliberately set aside.
- The GPIO 5 root cause — routed around; a curiosity, not a blocker.
- Any non-macOS host support.
- Device-side WiFi, forever, on purpose.
