# Sensor and board bring-up diagnostics

A handful of small sketches plus a host-side reader. Together they answer
"is it the wiring, the baud rate, the sensor, or the board?" in a few
minutes instead of an evening.

All target the QT Py ESP32-S3. Pin labels map to GPIOs as follows (confirmed
against the Arduino core's variant file, not assumed):

| Pad label | GPIO | Role in this build |
| --- | --- | --- |
| `TX` | 5 | our **receive** (sensor yellow/TXD) |
| `RX` | 16 | our **transmit** (sensor brown/RXD) |
| `A3` | 8 | WAKEUP (sensor blue) — unused, see below |

**The TX/RX roles above are swapped relative to the silkscreen**, because
the board these were written against can't carry UART transmit on GPIO 5.
If yours can, use the silkscreen orientation. Either way, a sketch pointed
at the wrong pair will look like a dead sensor, so check this first.

`A3`/WAKEUP is wired but unused: the production firmware sets
`USE_INT_PIN = false` and polls `GenImg` instead, because on this module the
WAKEUP line sat permanently at the active level, so the INT path scanned
nonstop and every scan returned `GENIMG_FAIL 2`.

```bash
FQBN="esp32:esp32:adafruit_qtpy_esp32s3_nopsram:CDCOnBoot=cdc,USBMode=default"
arduino-cli compile --fqbn "$FQBN" firmware/diagnostics/fp_sweep
arduino-cli upload  --fqbn "$FQBN" -p /dev/cu.usbmodemXXX firmware/diagnostics/fp_sweep
```

`fp_sweep` needs the Adafruit library: `arduino-cli lib install "Adafruit
Fingerprint Sensor Library"`. The others have no dependencies.

## Reading the output: `capture.py`

```bash
.venv/bin/python firmware/diagnostics/capture.py --secs 30
.venv/bin/python firmware/diagnostics/capture.py --until "sweep complete"
.venv/bin/python firmware/diagnostics/capture.py --watch
```

**The board only transmits when the host asserts DTR.** The ESP32-S3's native
USB CDC stays mute otherwise, and a board with DTR low is indistinguishable
from a dead one — no boot banner, no reply to anything. `capture.py` always
asserts it. If you reach for `screen` or `cat` instead, make sure DTR is
raised or you will misdiagnose a healthy board.

`--watch` survives disconnects and prints a timeline of port appear/vanish
events. Repeated cycles mean the board is resetting, which almost always
means a shorted pin is browning out the regulator — a pattern that is
invisible to a reader that exits on the first read error.

## Wire ALL SIX sensor wires before diagnosing anything

**Check this before anything else.** Sensor pin 6 (`3.3VT`, white) must be
connected to `3V`. With it unwired the module powers up, receives commands,
and *executes* them — the aura ring visibly obeys — but it **cannot reply to
anything**. That looks exactly like a dead sensor, and it is the most common
reason a healthy one gets written off.

Both power wires (pins 1 and 6) land on the single `3V` pad. If you are
bringing wires up one at a time to isolate a fault, connect **both power
wires first** — an under-powered module produces misleading results at every
later step.

## Triage order

**Test the board before you blame the sensor.** A board-side transmit fault
looks identical to a dead sensor, and every test that assumes the MCU's UART
works will happily confirm the wrong conclusion.

0. **Check all six wires**, especially `3.3VT` (see above).
1. **`fp_loopback`** — does this board's UART work at all? No sensor involved.
2. **`gpio_drive`** — if loopback fails, is the pin electrically sane at DC?
3. **`fp_probe`** — raw `0xEF01` commands, no library. The most trustworthy
   "is the sensor alive?" test; also dumps `ReadSysPara` (capacity, security
   level, baud), which is the only model ID an unbranded module will give you.
4. **`fp_boot_listen`** — did the sensor ever transmit a `0x55` handshake?
5. **`fp_led`** — does the sensor hear us, independent of whether it replies?
6. **`fp_sweep`** — baud/orientation sweep. **Read its caveats below before
   trusting a negative result from it.**

## `fp_loopback` — "does the board's UART work?"

Jumper the pad labeled `TX` straight to the pad labeled `RX`, with **nothing
else connected**. The board transmits 8 bytes and should receive its own
transmission, at three baud rates plus the reversed pin assignment.

- **`received=8` with the bytes echoed back** — UART peripheral, GPIO matrix
  routing, and both pads are all good. Any fault is downstream.
- **`received=0`** — nothing is arriving. Check the jumper before anything else.
- **Hundreds of `0x00` bytes when only 8 were sent** — the receive line is being
  held low. A UART reads a stuck-low line as an endless run of start bits.

That last signature is the interesting one, because it is direction-specific:
if one pin assignment echoes perfectly and the reverse floods zeros, the
transmitting pin in the failing case cannot drive the line.

## `gpio_drive` — "is the pin electrically sane?"

Same single `TX`↔`RX` jumper. Drives each pin as a bare digital output and
reads the other as a digital input, with no UART involved.

Note what this does and does not prove. `digitalRead` is a high-impedance
input drawing nanoamps, so a pass means **a DC path exists** — not that the
pin can source meaningful current. A pin that passes here but fails
`fp_loopback` can still be a high-resistance path: DC settles fine, but the
edges never form at 57600 baud where each bit is only 17µs wide.

## `fp_sweep` — "is the sensor alive at all?"

Brute-forces the **official `Adafruit_Fingerprint` library** against the
sensor across 7 baud rates × both TX/RX orientations (14 combinations). The
orientation swap happens in software via the ESP32's GPIO matrix, so no
rewiring is needed. Requires no finger on the sensor — `verifyPassword()` is
a pure handshake.

> **`trailing_bytes` does NOT measure sensor silence — do not read it that
> way.** `verifyPassword()` consumes the sensor's response internally, so
> `trailing_bytes` counts only what arrived *after* the library was done.
> Zero is the normal result whether the sensor answered or not, so it is
> not evidence of anything. Don't use it to decide a sensor is dead.
>
> A working R503 has been observed returning `confirm=0x00` to a raw
> `VerifyPassword` via `fp_probe` while `fp_sweep` simultaneously reported
> `verifyPassword=fail trailing_bytes=0` on all 14 combinations. **Trust
> `fp_probe` over `fp_sweep` for any negative result.**

- **A combination reports `verifyPassword=OK`** — that's your baud and
  orientation. Done. (A positive result here is still meaningful.)
- **`verifyPassword=fail` everywhere** — inconclusive on its own. Confirm
  with `fp_probe` before drawing any conclusion about the sensor.
- **Nonzero `trailing_bytes` but no valid response** — bytes are arriving but
  aren't valid `0xEF01` frames. Suspect baud mismatch, crosstalk between
  adjacent TX/RX leads, or a floating input picking up noise.

Using the canonical library rather than our own protocol code is the point:
it removes our `fpCommand()` implementation from the list of suspects.

## `fp_probe` — "what does the sensor actually say?" (start here)

Sends raw `0xEF01` packets with no library involved, and dumps every byte
that comes back. Three commands per cycle: `VerifyPassword` (0x13),
`ReadSysPara` (0x0F), and a known-good `AuraLedConfig` (0x35) as a control.

It exists because a library sitting between you and the sensor can report
failure on a sensor that's answering perfectly well. This removes that
variable.

`ReadSysPara`'s reply is also the only model ID an unbranded module offers:

```
ef01 ffffffff 07 0013 00  0004 0000 00c8 0003 ffffffff 0002 0006  04ed
                          status  id  cap  sec   addr   pkt  baud
```

`cap=0x00c8` = 200 templates (matches genuine GROW R503), `baud=6` = 57600.

## `fp_colors` — "what does this unit's ring actually support?"

R503-class clones vary; many listings advertise only a "2-color ring," and
spec-defined colors may render wrong or identical on a given unit. This
sketch loops a fixed, self-describing sequence — 7 colors at 3s each (red,
blue, purple, green, yellow, cyan, white), then breathing / flashing /
fade-in / fade-out on blue — with dark gaps as delimiters, so no serial
monitor is needed. Run it once on any new unit and define the firmware's
LED language only from what renders distinctly.

(The unit in this build passed all 7 colors and all 4 animated modes,
despite its listing advertising two colors.)

## `fp_boot_listen` — "did the sensor ever transmit?"

The R5xx family emits a `0x55` handshake byte within milliseconds of getting
power. **`fp_sweep` structurally cannot see it** — it sits in a 2500ms
USB-settle delay while the byte comes and goes.

This sketch opens the UART as its first instruction, buffers everything into
RAM, and only then brings up USB serial to report, so the evidence survives
even though it arrived before the host was listening. `loop()` keeps printing
late arrivals, so you can also power-cycle the sensor by hand while it runs.

Since the sensor is powered from the board's `3V` rail, a reflash does not
power-cycle it. To trigger the handshake, pull **both** power wires (sensor
pins 1 and 6) and reinsert them.

## `fp_led` — "does the sensor hear us?"

Drives the Aura LED (`0x35` AuraLedConfig, and the legacy `0x3c` some modules
use) and **ignores all responses**. This isolates the host→sensor direction,
which still works even when the sensor's transmit path is dead.

The key state is **OFF**: a sensor will never turn its own ring off
spontaneously, so if the ring goes dark on command, it is definitely
receiving and executing.

**Do not use the ring as a power-on gate.** An R503's aura is under software
control and is not guaranteed to light up until commanded, so a dark ring at
power-up is weak evidence of nothing in particular. Conversely, some modules
idle with a breathing-blue animation, which is a factory default and *not* a
response to anything you sent. Neither state tells you much on its own.

## Combined verdicts

| fp_loopback | fp_led | fp_probe | Meaning |
| --- | --- | --- | --- |
| Echoes back | Ring obeys | `confirm=0x00` | Everything works |
| Echoes back | **Ring obeys** | **No reply** | **Check `3.3VT` (pin 6) first — this is the exact signature of an unwired touch supply, and it is NOT evidence of a dead TX** |
| Echoes back | No reaction | No reply | No power, no comms, or a fully dead part |
| **Floods zeros** | any | any | **Board-side transmit fault — every sensor verdict below this line is unsafe** |

"Receives but never replies" looks like a dead TX driver or a broken TX
wire. Far more often it just means `3.3VT` isn't connected — check that
first, every time.

Measuring the idle voltage on the sensor's TX line is still worth doing, but
**a low reading does not condemn the part**. A healthy idle UART line sits at
~3.3V; the working R503 read **2.65V while `3.3VT` was unwired** and was
completely functional once it was connected. Wire all six pins before you
attribute a low reading to a damaged output stage.
