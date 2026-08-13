# Sensor and board bring-up diagnostics

Five throwaway-but-useful sketches plus a host-side reader. Together they
answer "is it the wiring, the baud rate, the sensor, or the board?" in a few
minutes instead of a full session.

All target the QT Py ESP32-S3. Pin labels map to GPIOs as follows (confirmed
against the Arduino core's variant file, not assumed):

| Pad label | GPIO |
| --- | --- |
| `TX` | 5 |
| `RX` | 16 |
| `A3` | 8 |

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

## Triage order

**Test the board before you blame the sensor.** This is the hard-won one. Two
different fingerprint sensors were diagnosed as defective through a board-side
transmit fault that nobody had checked, because every test assumed the MCU's
UART worked.

1. **`fp_loopback`** — does this board's UART work at all? No sensor involved.
2. **`gpio_drive`** — if loopback fails, is the pin electrically sane at DC?
3. **`fp_sweep`** — only once the board is proven: is the sensor alive?
4. **`fp_boot_listen`** — if the sweep is silent, did the sensor ever transmit?
5. **`fp_led`** — does the sensor hear us, independent of whether it can reply?

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

- **A combination reports `verifyPassword=OK`** — that's your baud and
  orientation. Done.
- **`trailing_bytes=0` everywhere** — the sensor is transmitting *nothing*.
  Before concluding the part is dead, confirm with `fp_loopback` that the
  board can transmit. A sensor that never receives a command cannot reply,
  and the result looks identical to a dead sensor.
- **Nonzero `trailing_bytes` but no valid response** — bytes are arriving but
  aren't valid `0xEF01` frames. Suspect baud mismatch, crosstalk between
  adjacent TX/RX leads, or a floating input picking up noise.

Using the canonical library rather than our own protocol code is the point:
it removes our `fpCommand()` implementation from the list of suspects.

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

| fp_loopback | fp_led | fp_sweep | Meaning |
| --- | --- | --- | --- |
| Echoes back | Ring obeys | Valid responses | Everything works |
| Echoes back | Ring obeys | Silence | Sensor receives but can't transmit — dead TX driver or broken TX wire |
| Echoes back | No reaction | Silence | No power, no comms, or a fully dead part |
| **Floods zeros** | any | any | **Board-side transmit fault — every sensor verdict below this line is unsafe** |

If the "sensor receives but can't transmit" row comes up, measure the idle
voltage on the sensor's TX line (probe the board's `RX` pin against `GND`,
powered). A healthy idle UART line sits at ~3.3V. Anything meaningfully below
the ESP32's ~2.48V logic-high threshold means the output stage can't drive a
valid high — the ZW111 that prompted these sketches sat at 2.08V.
