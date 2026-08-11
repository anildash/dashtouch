# Sensor bring-up diagnostics

Two throwaway-but-useful sketches written during the postmortem on a dead
ZW111. Keep them around: the next time a fingerprint sensor doesn't answer,
these answer "is it the wiring, the baud rate, or the part?" in about two
minutes instead of a full session.

Both target the QT Py ESP32-S3 and assume the sensor's TXD is on the header
pin labeled `RX` (GPIO 16) and its RXD on `TX` (GPIO 5).

```bash
FQBN="esp32:esp32:adafruit_qtpy_esp32s3_nopsram:CDCOnBoot=cdc,USBMode=default"
arduino-cli compile --fqbn "$FQBN" firmware/diagnostics/fp_sweep
arduino-cli upload  --fqbn "$FQBN" -p /dev/cu.usbmodemXXX firmware/diagnostics/fp_sweep
```

## fp_sweep — "is the sensor alive at all?"

Brute-forces the **official `Adafruit_Fingerprint` library** against the
sensor across 7 baud rates × both TX/RX orientations (14 combinations). The
orientation swap happens in software via the ESP32's GPIO matrix, so no
rewiring is needed. Requires no finger on the sensor — `verifyPassword()` is
a pure handshake.

Install the library first:

```bash
arduino-cli lib install "Adafruit Fingerprint Sensor Library"
```

Reads the result as:

- **A combination reports `verifyPassword=OK`** — that's your baud and
  orientation. Done.
- **`trailing_bytes=0` everywhere** — the sensor is transmitting *nothing*.
  Suspect the sensor's TX path, its TX wire, or the part itself. This is what
  a dead unit looks like.
- **Nonzero `trailing_bytes` but no valid response** — bytes are arriving but
  aren't valid `0xEF01` frames. Suspect baud mismatch, crosstalk between
  adjacent TX/RX leads, or a floating input picking up noise.

Using the canonical library rather than our own protocol code is the point:
it removes our `fpCommand()` implementation from the list of suspects.

## fp_led — "does the sensor hear us?"

Drives the Aura LED (`0x35` AuraLedConfig, and the legacy `0x3c` some modules
use) and **ignores all responses**. This isolates the host→sensor direction,
which still works even when the sensor's transmit path is dead.

The key state is **OFF**: a sensor will never turn its own ring off
spontaneously, so if the ring goes dark on command, it is definitely
receiving and executing. Solid red is the other useful probe, since the
factory idle animation on these modules is typically breathing blue — do not
mistake that default for a response.

Combined verdicts:

| fp_led | fp_sweep | Meaning |
| --- | --- | --- |
| Ring obeys | Gets valid responses | Everything works |
| Ring obeys | Silence (0 bytes) | Sensor receives but can't transmit — dead TX driver or broken TX wire |
| No reaction | Silence | No power, no comms at all, or fully dead part |

If the second row comes up, measure the idle voltage on the sensor's TX line
(probe the QT Py's `RX` pin against `GND`, powered). A healthy idle UART line
sits at ~3.3V. Anything meaningfully below the ESP32's ~2.48V logic-high
threshold means the output stage can't drive a valid high — the ZW111 that
prompted these sketches sat at 2.08V.
