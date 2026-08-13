# Dashboard Touch

**Touch ID for your Mac, without the $149 keyboard.**

Rest your finger on a little sensor and your password types itself — at
the login screen, in sudo prompts, anywhere your Mac asks. You build it
yourself from about $25 of parts, and you get to decide exactly where the
sensor lives: your desk, your monitor stand, a drawer front you drilled
one hole in.

*(Photo: your build here.)*

## The honest part, first

Dashboard Touch works by **typing your real password** the moment it
recognizes your finger. That's why it works everywhere — and it's also a
real security tradeoff you should understand before building one. The
short version: anyone with physical access to your desk and your gadget
could get up to mischief. Read [docs/security.md](docs/security.md) —
it's written for humans — and decide if that tradeoff is fine for your
desk. (For a lot of home offices, it is.)

## What you need

| Part | Cost | Where |
| --- | --- | --- |
| Adafruit QT Py ESP32-S3 (the tiny computer) | ~$12.50 | [adafruit.com](https://www.adafruit.com/product/5426) |
| R503 fingerprint sensor (the round thing) | ~$10–20 | Amazon/AliExpress, search "R503 fingerprint" |
| USB-C cable that carries data | you have one | — |

The sensor is a round module about an inch across with a threaded barrel —
made to poke through a hole in a panel and screw tight. Any panel you
like. That's the fun part.

## Wire it (six wires, all six matter)

The sensor's cable has six colored leads. They land on the QT Py like so:

| Wire | Meaning | Goes to |
| --- | --- | --- |
| Red | power | `3V` |
| Black | ground | `GND` |
| Yellow | sensor talks | `RX` |
| Brown | sensor listens | `TX` |
| Blue | touch wake | `A3` |
| **White** | **touch power** | **`3V` (yes, a second wire on the same pin)** |

**About that white wire:** without it, the sensor can hear but can't
speak — everything will look broken in a way that took this project two
weeks to figure out so you don't have to. Both red *and* white go to `3V`.

## Set it up

```sh
git clone https://github.com/anildash/dashtouch
cd dashtouch
./setup
```

The script walks you through everything: it makes a pairing key, tucks
your password into the Mac's Keychain (never anywhere else), and flashes
the firmware onto the board. Then:

```sh
dashtouch run      # start the helper
dashtouch enroll   # opens your browser — add a finger
```

Follow the ring: **breathing white** means place your finger, **cyan**
means lift, green flashes mean you're in. From then on, purple means
ready — touch the ring, watch your password appear.

Want it running all the time without a terminal open?

```sh
dashtouch install-agent
```

## The ring, decoded

| Color | Meaning |
| --- | --- |
| Purple, steady | Ready and waiting |
| White | Reading your finger |
| Green flashes | Matched — password typed |
| Red flashes | Not a finger it knows |
| Yellow, steady | Matched, but it can't reach your Mac — is the helper running? |
| Cyan | Lift your finger (enrolling) |
| Never turns purple | The sensor isn't talking — recheck all six wires |

## Something not working?

Run `dashtouch doctor` for a quick check-up, or read
[docs/troubleshooting.md](docs/troubleshooting.md) — every dead end in
there is one this project personally drove into so you don't have to.

## Credits

Dashboard Touch is an extensive rework of
[tinyTouch](https://github.com/ZimengXiong/tinyTouch) by Zimeng Xiong,
which proved the whole idea. The debugging war stories live in
[docs/history/](docs/history/). MIT licensed, like the original.
