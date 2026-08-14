# Dashboard Touch

**Touch ID for your Mac, without the $149 keyboard.**

Rest your finger on a little sensor and your password types itself — at
the login screen, in sudo prompts, anywhere your Mac asks. You build it
yourself from about $25 of parts, and you get to decide exactly where the
sensor lives: your desk, your monitor stand, a drawer front you drilled
one hole in.

![The Dashboard Touch helper page: a glowing purple ring showing the device
is ready, a row of enrolled fingers, and a setup checklist with everything
green.](docs/images/web-ui.png)

The page above is where you add fingers and check that everything's
working. It runs on your own Mac — nothing leaves it.

![A round fingerprint sensor set into a small wooden block, its ring lit
purple, wired to a thumb-sized microcontroller on a workbench.](docs/images/device.jpg)

*A work-in-progress build — the sensor gets mounted into the desk itself,
but this is the whole gadget: one sensor, one microcontroller, six wires.*

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
| Adafruit QT Py ESP32-S3 (the tiny computer, what Anil used) | ~$12.50 | [adafruit.com](https://www.adafruit.com/product/5426) |
| R503 fingerprint sensor (the round thing, what Anil used) | ~$10–20 | [Amazon](https://amzn.to/4wnVuO9) |
| USB-C cable, data-capable (not a charge-only one) | you have one | [Amazon](https://amzn.to/4zjg9p9) |

Presumably a [cheaper board](https://amzn.to/4gjkss2) could work here too —
untested in this build, so it's a "try it and report back" rather than a
recommendation. If the Amazon sensor is out of stock, [Adafruit sells the
same part](https://www.adafruit.com/product/4651) — it's a fine swap, just
usually pricier and often backordered itself.

Some links on this page are affiliate links — they cost you nothing extra
and help pay for the next round of parts.

The sensor is a round module about an inch across with a threaded barrel —
made to poke through a hole in a panel and screw tight. Any panel you
like. That's the fun part. Don't want to build an enclosure? [This one](https://amzn.to/4wwqw6m)
skips the woodworking.

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
.venv/bin/dashtouch run       # start the helper
.venv/bin/dashtouch enroll    # opens your browser — add a finger
.venv/bin/dashtouch           # prints the link to that page, if you'd
                              # rather open it yourself
.venv/bin/dashtouch password  # change the password it types (no reflash)
.venv/bin/dashtouch pairing   # rotate the pairing key (needs a reflash)
```

The helper's page lives at port 3274 — DASH on a phone keypad, because of course it is.

<details><summary>Flashing by hand (if setup couldn't see your board)</summary>

```sh
arduino-cli compile --fqbn esp32:esp32:adafruit_qtpy_esp32s3_nopsram:CDCOnBoot=cdc,USBMode=default firmware/dashtouch
arduino-cli upload --fqbn esp32:esp32:adafruit_qtpy_esp32s3_nopsram:CDCOnBoot=cdc,USBMode=default -p $(arduino-cli board list | grep -o '/dev/cu.usbmodem[0-9]*' | head -1) firmware/dashtouch
```
</details>

Follow the ring: **breathing white** means place your finger, **cyan**
means lift, green flashes mean you're in. From then on, purple means
ready — touch the ring, watch your password appear.

Want it running all the time without a terminal open?

```sh
.venv/bin/dashtouch install-agent
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

Ring not matching this table, or stuck on one color? [docs/troubleshooting.md](docs/troubleshooting.md)
walks through it symptom by symptom.

Don't want a lit ring on your desk all night, or want Return pressed
yourself instead of automatically? Both the resting ring (including
turning it off entirely) and pressing Return after typing are settings on
the helper's page, stored right on the gadget.

## Something not working?

Run `.venv/bin/dashtouch doctor` for a quick check-up, or read
[docs/troubleshooting.md](docs/troubleshooting.md) — every dead end in
there is one this project personally drove into so you don't have to.

## Credits

Dashboard Touch is an extensive rework of
[tinyTouch](https://github.com/ZimengXiong/tinyTouch) by Zimeng Xiong,
which proved the whole idea. The debugging war stories live in
[docs/history/](docs/history/). MIT licensed, like the original.
