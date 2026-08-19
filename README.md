# Dashboard Touch

**Touch ID for your Mac, without an Apple keyboard.**

> Dashboard Touch is built on the work of [tinyTouch](https://github.com/ZimengXiong/tinyTouch)
> by **[Zimeng Xiong](https://github.com/ZimengXiong)**, which defined this entire
> approach. This project is an extensive refactoring of that original work, and
> shares its MIT license. If you find Dashboard Touch useful, go star tinyTouch —
> none of this exists without it. TinyTouch also supports other authentication
> methods that Dashboard Touch doesn't, so it's worth checking out just to learn
> what's possible!

Automatically type in your password at the tap of your finger, anywhere your Mac
asks for it. For those of us who use our own keyboards, but miss the convenience
and ease of Touch ID on Apple devices, Dashboard Touch lets you build your own
solution from parts that you can get for about $30.

Best of all, you get to decide exactly where the sensor lives: on your desk, in
a custom enclosure, or wherever else you can imagine.

Once you've installed a few simple tools, you can manage the whole thing through
a friendly web interface, and it's all FREE and open source, with no
surveillance or data sent anywhere. Your fingerprints never leave your sensor
device, and your password never leaves your Mac.

![The Dashboard Touch helper page: a glowing purple ring showing the device
is ready, a row of enrolled fingers, and a setup checklist with everything
green.](docs/images/web-ui.png)

The page above is where you add fingerprints and check that everything's
working. It runs entirely on your own Mac.

![A round fingerprint sensor set into a small wooden block, its ring lit
purple, wired to a thumb-sized microcontroller on a workbench.](docs/images/device.jpg)

_A look at a Dashboard Touch build in progress, with the fingerprint sensor
mounted in a small wooden block designed to mount to a desk, the connection
wires soldered to the QT Py microcontroller, and a standard USB plug providing
power and sending the signal to the computer._

## How it works, and why it's safe

Dashboard Touch works by **typing your real password** as soon as your
fingerprint has been verified by the sensor. Behind the scenes, the system
basically looks like a keyboard to your Mac, which just happens to type in the
correct password _only_ if your securely-recorded fingerprint is pressed to the
device. This design is why it works everywhere, but it also entails a real
security tradeoff that you should understand before building one. The short
version: anyone with physical access to your desk and your Dashboard Touch
hardware, if they have enough expertise, could cause you real problems. You can
read over [docs/security.md](docs/security.md) and decide if that tradeoff is
fine for where your Mac is located. (For most normal households and home
offices, it will probably be something most people are comfortable with.)

## What you need to get started

The build really only requires a few simple parts. These are the exact devices
that I used to build mine, but there are _lots_ of similar variants and you
could probably get them to work with a little bit of effort, too.

| Part               | Product                                   | Cost         | Where                                                 |
| ------------------ | ----------------------------------------- | ------------ | ----------------------------------------------------- |
| Microcontroller    | Adafruit QT Py ESP32-S3                   | ~$12.50      | [adafruit.com](https://www.adafruit.com/product/5426) |
| Fingerprint sensor | Simlug R503 clone                         | ~$10–20      | [Amazon](https://amzn.to/4wnVuO9)                     |
| USB-C cable        | Must be a _data_ cable, not just charging | you have one | [Amazon](https://amzn.to/4zjg9p9)                     |

Of course, it's likely a lot of this will work with [tinyTouch](https://tinytouch.dev),
which Zimeng Xiong is now selling as a hardware device designed to work with
his code. You should definitely support his project! And I'm sure his
enclosure will look really clean and elegant on any setup. 

Presumably a [cheaper board](https://amzn.to/4gjkss2) could work here too. I
haven't tested any of those other variants, but if you do and it works, please
do share your notes back. If the Amazon sensor is out of stock,
[Adafruit sells the same part](https://www.adafruit.com/product/4651); it was
just out of stock (and a lot more expensive) when I was doing my build. (Some of
these links are affiliate links. If I make any money from that, I'll use it to
help folks who want to build some of this stuff but don't have the tools/etc.
that they need.)

The fingerprint sensor is a round cylinder about an inch across with a threaded
barrel. I built a very simple wooden panel to mount mine on (you just poke it
through the hole and screw the bolt on the back), but if you don't want to build
an enclosure, I think [this one](https://amzn.to/4wwqw6m) would probably fit
with no work required.

## How to hook it up (what you need to solder)

You'll need to solder a few small connections to put together the QT Py board
and the sensor. It's not hard if you have experience soldering, but it can be a
little bit fiddly.

The fingerprint sensor's cable has six colored leads. By default, they're
attached to a little connector plug (it's a JST-SH connector with a 1mm pitch,
if you are a nerd) so you will need to either pull the connector pins out of the
plug or cut the wires so that you can solder them to the board.

The wires connect to the QT Py like this:

| Wire      | Meaning         | Goes to                                 |
| --------- | --------------- | --------------------------------------- |
| Red       | power           | `3V`                                    |
| Black     | ground          | `GND`                                   |
| Yellow    | sensor talks    | `RX`                                    |
| Brown     | sensor listens  | `TX`                                    |
| Blue      | touch wake      | `A3`                                    |
| **White** | **touch power** | **`3V` (the same pin as the red wire)** |

Make sure you wire up the white wire to the power lead just like the red wire.
It's easy to get excited and leave it off, because the sensor will power up and
light up without it, but nothing will work right if you don't, so save yourself
some trouble and be sure to get all 6 wires going.

## Set it up

You'll need the code from this github repo to set everything up. There's a
script that should help, so you can just do:

```sh
git clone https://github.com/anildash/dashtouch
cd dashtouch
./setup
```

The script walks you through everything: it makes a pairing key, stores your
password in the macOS Keychain (this is the same secure way all your other apps
do it), and flashes the firmware onto the QT Py board.

Once all of that is configured, you can use the dashtouch command-line tool to
do all of your key tasks:

```sh
.venv/bin/dashtouch run       # start the helper
.venv/bin/dashtouch enroll    # opens your browser — add a finger
.venv/bin/dashtouch           # prints the link to that page, if you'd
                              # rather open it yourself
.venv/bin/dashtouch doctor  # diagnose the current system setup
.venv/bin/dashtouch password  # change the password it types (no reflash)
.venv/bin/dashtouch pairing   # rotate the pairing key (needs a reflash)
.venv/bin/dashtouch install-agent   # configure the helper to run in the background automatically
```

### macOS will ask you about a keyboard

The first time you plug the board in after it's wired up and flashed, macOS will
pop open the Keyboard Setup Assistant. This is a good sign! It means your Mac has
noticed the QT Py showing up as a USB keyboard, which is exactly what it's
supposed to be doing.

Just click **Quit** to dismiss it. The assistant is trying to work out what
layout your new keyboard has, and it does that by asking you to press a few
specific keys — but this "keyboard" only ever types one thing, so there's
nothing useful to tell it. Quitting doesn't break anything and doesn't skip any
setup step. Dashboard Touch works exactly the same afterward.

You may see the assistant again if you move the board to a different USB port,
because macOS counts that as meeting a new device. Same answer: Quit.

### Dashboard Touch helper

The "helper" is a little app that stays running in the background in order to
enable the Dashboard Touch system to do its tasks, but it also provides a
convenient user interface for you to configure or customize your setup right
from your web browser. The helper's page lives at IP address 127.0.0.1, and the
port number is 3274. (That's DASH on a phone keypad.)

### Manually updating firmware

The `dashtouch` utility flashes the firmware to your board for you, but if you
want to do that manually yourself, you can do that with the Arduino CLI tools.

<details><summary>Flashing by hand (if setup couldn't see your board)</summary>

The firmware includes `firmware/dashtouch/secrets.h`, which holds your pairing
key. `dashtouch setup` and `dashtouch pairing` write that file right before
flashing and delete it immediately afterward, so the key isn't left sitting on
your disk in plaintext. That means it's normally *not* there, and a bare
`arduino-cli compile` will stop with `secrets.h: No such file or directory`.

So this is the flow when setup couldn't reach your board: run `dashtouch pairing`
and let it fail to find the board — it writes `secrets.h` and leaves it in place
when the flash doesn't happen. Then flash by hand:

```sh
arduino-cli compile --fqbn esp32:esp32:adafruit_qtpy_esp32s3_nopsram:CDCOnBoot=cdc,USBMode=default firmware/dashtouch
arduino-cli upload --fqbn esp32:esp32:adafruit_qtpy_esp32s3_nopsram:CDCOnBoot=cdc,USBMode=default -p $(arduino-cli board list | grep -o '/dev/cu.usbmodem[0-9]*' | head -1) firmware/dashtouch
```

Delete `firmware/dashtouch/secrets.h` when you're done — it's a plaintext copy
of the same key that's in your Keychain.

</details>

## Once you're set up

After Dashboard Touch is running, everything you can do is basically visible in
the helper tool's web page, and guided by the ring light on the fingerprint
sensor.

By default, the ring will be solid purple to indicate that the system is ready
(this is configurable, and you can turn the light off). Other colors and
blinking statuses make it clear when you can add a new fingerprint, whether an
existing fingerprint has been detected, or if there is any kind of error.

### Sensor ring colors

| Color              | Meaning                                                       |
| ------------------ | ------------------------------------------------------------- |
| Purple, steady     | Ready and waiting                                             |
| White              | Reading your finger                                           |
| Green flashes      | Matched — password typed                                      |
| Red flashes        | Not a finger it knows                                         |
| Yellow, steady     | Matched, but it can't reach your Mac — is the helper running? |
| Cyan               | Lift your finger (enrolling)                                  |
| Never turns purple | The sensor isn't talking — recheck all six wires              |

If you see some unexpected color, or get stuck,
[docs/troubleshooting.md](docs/troubleshooting.md) walks through most common
problems.

### Settings

I tried to make there be as few settings as possible so there isn't too much to
configure after you get it working, but there is a simple one-click way to
change which color the ring shows when it's at rest. (You have the option to
turn it off, or to make the light "breathe".)

And the other setting is whether or not the system hits "return" automatically
after typing in your password. You can switch that off if you want to verify
that you're ready to authenticate each time, or if you have any qualms about the
system submitting your password on its own when you register a fingerprint.

## Something not working?

Run `.venv/bin/dashtouch doctor` for a quick check-up, or read
[docs/troubleshooting.md](docs/troubleshooting.md), which walks through the
usual suspects symptom by symptom.

## Future directions

**Could it be wireless?** In theory, yes — the board has WiFi and Bluetooth LE,
and pads on the underside for a battery. It'd have to type over Bluetooth rather
than USB, since typing your password at the login screen is the whole point and
that only works if your Mac sees a real keyboard. I haven't explored it, so
consider it an open idea rather than a supported option.

## Credits and contributions

Dashboard Touch is an extensive refactoring of
[tinyTouch](https://github.com/ZimengXiong/tinyTouch) by Zimeng Xiong, which
defined this entire approach. It shares the same MIT license as the project
which inspired it.

The protocol is documented in [docs/protocol.md](docs/protocol.md), and this is
my first attempt at sharing any of the code I've made for a hardware project, so
improvements, feedback, comments and pull requests are very welcome!
