# QT Py UART transmit fault — investigation record

**Date:** 2026-08-12
**Status:** GPIO 5 fault confirmed and routed around; root cause still
unconfirmed. **See the 2026-08-13 resolution below — this was not the only
fault, and on its own it did not explain the silence.**
**Headline:** the pad labeled `TX` (GPIO 5) will not carry UART transmit on
this board. Both fingerprint sensors previously diagnosed as defective were
tested through it, so **neither verdict is safe.**

---

## RESOLVED 2026-08-13 — there was a second, independent fault

The whole device now works end to end (match → HMAC'd event → helper →
typed password). Two separate problems were stacked on top of each other,
and fixing only the first left the symptom unchanged:

1. **The GPIO 5 UART transmit fault** documented in the rest of this file.
   Real, reproduced again on 2026-08-13, still routed around by transmitting
   on GPIO 16.
2. **Sensor pin 6 (`3.3VT`, white wire) was never connected.** This is the
   one that actually mattered. With it unwired the module powers up, parses
   commands, and *executes* them — the aura ring obeys `OFF` and `RED` — but
   it cannot reply. Connect white to `3V` and every command returns a clean
   ACK immediately.

That second fault is what produced this project's entire "the sensor is
dead" arc. A module that receives, obeys, and never answers is
indistinguishable from a broken one if you only ever look at whether bytes
come back.

### Consequences for earlier conclusions

- **The R503 is not defective.** It works.
- **The ZW111 verdict is now unsafe for two independent reasons** — it was
  tested through the dead GPIO 5 pad *and* very likely without `3.3VT`
  connected. Retest before trusting "defective."
- **The `2.08V` and `2.65V` idle readings on sensor TX** measure an
  *unpowered* output stage, not a damaged one. The R503 read 2.65V while
  3.3VT was unwired and worked perfectly once it was connected. Do not
  condemn a part on that measurement alone.
- **`0x55` handshake bytes seen during power-cycling were most likely
  genuine**, not noise. They were dismissed mid-session and that was wrong.

### `ReadSysPara` output from the working module

```
ef01 ffffffff 07 0013 00  0004 0000 00c8 0003 ffffffff 0002 0006  04ed
                          status  id  cap  sec   addr   pkt  baud
```

Capacity `0x00c8` = **200 templates**, matching the genuine GROW R503 spec
and contradicting the Amazon listing's "500" claim. Security level 3, packet
size 128, baud register 6 (= 57600), default address. This is the closest
thing to a model ID obtainable from an unbranded module, and it is the fast
way to identify the next one.

---

## The finding in one paragraph

A UART loopback test — a single jumper between the `TX` and `RX` pads, no
sensor involved — shows a hard directional asymmetry. Transmitting on GPIO 16
and receiving on GPIO 5 moves a byte-perfect packet. Transmitting on GPIO 5
and receiving on GPIO 16 floods hundreds of `0x00` bytes, the signature of a
receive line held low. Since every command this project has ever sent to a
fingerprint sensor went out through GPIO 5, no sensor has ever received one,
and no sensor could ever have replied.

## Evidence

### Loopback, `TX`↔`RX` jumper only, nothing else connected

```
baud=57600   rx=16 tx=5   sent=8 received=256  bytes=0000000000000000...
baud=9600    rx=16 tx=5   sent=8 received=220  bytes=0000000000000000...
baud=115200  rx=16 tx=5   sent=8 received=240  bytes=0000000000000000...
baud=57600   rx=5  tx=16  sent=8 received=8    bytes=ef01a55a00ff427e
```

The last line is exact: all 8 bytes, byte-for-byte identical to what was
sent. Reproduced across many cycles, and again after a reflow of the `TX`
joint. The failure is stable and direction-specific, not intermittent.

### Plain GPIO drive, same jumper

```
drive GPIO 5  -> read GPIO 16 : high=1 low=0  OK
drive GPIO 16 -> read GPIO 5  : high=1 low=0  OK
```

Both pins drive both states correctly at DC. This rules out a dead output
driver and rules out a short to ground — a short would have failed here too.

Important caveat: `digitalRead` is a high-impedance input drawing nanoamps,
so this proves a **DC path exists**, not that the pin can source current. It
does not contradict a high-resistance fault.

### Board variant file (authoritative)

`~/Library/Arduino15/packages/esp32/hardware/esp32/3.3.11/variants/adafruit_qtpy_esp32s3_nopsram/pins_arduino.h`

```c
static const uint8_t TX = 5;
static const uint8_t RX = 16;
```

The pin mapping in the design spec is correct. The loopback result
independently confirms it: for `rx=5 tx=16` to work, both GPIOs must be
physically present on the two jumpered pads.

## Hypotheses tested

| # | Hypothesis | Verdict |
| --- | --- | --- |
| 1 | Sensor is dead (ZW111, then R503) | **Unsafe** — never received a command |
| 2 | Connector orientation reversed | Untested; blocked on a meter |
| 3 | Loose jumper contact | Weakened — survived a rebuild onto solid pins |
| 4 | Wrong baud rate | Ruled out — 7 rates swept |
| 5 | Wrong TX/RX orientation | Ruled out — swept in software both ways |
| 6 | Wrong pin mapping in firmware | Ruled out — variant file and loopback agree |
| 7 | Dead GPIO 5 output driver | Ruled out — drives fine at DC |
| 8 | Solder bridge, `TX` to ground | Ruled out — a short is direction-agnostic; the reverse direction works |
| 9 | Cold/high-resistance joint on `TX` | **Disproven** — reflowed, behavior unchanged |
| 10 | UART TX not routing onto GPIO 5 | **Open** — consistent with all evidence, unconfirmed |

## What the reflow taught us

Reflowing the `TX` joint turned the board into a ~4.3s reset loop with zero
serial output. `capture.py --watch` caught it:

```
port APPEARED → opened → read failed → VANISHED → (0.8s) → APPEARED …
```

The timing was diagnostic: the sketch waits `delay(2500)` in setup, then
starts transmitting, and the port died ~3.5s after each appearance. The board
was browning out the instant firmware drove GPIO 5 — a solder bridge created
by the reflow itself. Wicking it clean restored stability.

Two lessons worth keeping:

- A repeated appear/vanish cycle on the USB port is a **brownout signature**,
  not a flaky cable. Correlate the survival time against the sketch's own
  startup delay to find which line of firmware kills it.
- The reflow disproved the cold-joint theory rather than confirming it. The
  original fault survived a joint rebuild, so it is not the joint.

## Working configuration

The board does flawless UART with **transmit on GPIO 16, receive on GPIO 5** —
the reverse of the silkscreen. Route around the fault rather than fixing it:

| Sensor wire | Signal | → QT Py pad | GPIO | Role |
| --- | --- | --- | --- | --- |
| red | Power 3.3V | `3V` | — | — |
| black | GND | `GND` | — | — |
| yellow | TXD | `TX` | 5 | our **receive** |
| brown | RXD | `RX` | 16 | our **transmit** |
| blue | WAKEUP | `A3` | 8 | — |
| white | 3.3VT | `3V` | — | — |

Yellow and brown land on pads whose labels contradict their function. That is
intentional and must stay documented, or the next person wires it by the
silkscreen and hits the same wall.

Firmware constants become:

```c
static const int FP_TX_PIN = 16;  // pad labeled RX
static const int FP_RX_PIN = 5;   // pad labeled TX
```

`fp_sweep` validates this for free — its `[swapped]` pass is exactly
`rx=5, tx=16`.

## Still open

- **Root cause of the GPIO 5 UART fault.** Hypothesis 10 fits everything but
  is unconfirmed. Worth testing UART TX on GPIO 5 against a *different*
  receive pin (A0/GPIO 18) to separate "GPIO 5 can't do UART TX" from
  "something specific to the GPIO 5 ↔ GPIO 16 pairing."
- **Whether the R503 works.** It has never been given a fair test.
- **Whether the ZW111 was ever defective.** See below.
- **Connector orientation.** Still unverified electrically; the pullup test in
  the design spec resolves it once a meter is available.

## Reopening the ZW111 verdict

The design spec's "ZW111 unit found defective" section concludes the part was
dead because it never transmitted under any wiring, baud, or connector. Every
one of those tests sent commands through GPIO 5. A sensor that receives
nothing transmits nothing, so the observation is fully explained by the board
fault and does not establish that the ZW111 was defective.

The one piece of ZW111 evidence that is *not* explained by this is the
measured 2.08V idle on its TX line, against the ESP32's ~2.48V logic-high
threshold. That was a direct measurement of the sensor's own output stage and
remains suspicious. But it was a single reading, and it is no longer
sufficient on its own.

If the R503 works in the swapped configuration, retest the ZW111 the same way
before trusting the original verdict.
