# When it doesn't work

Every fix in here was earned the hard way on the very first build. Work
top to bottom — the list is ordered by "most likely culprit."

## The ring never turns purple

The firmware can't talk to the sensor. In order:

1. **Count your wires. All six?** The white one (touch power) is the
   classic miss — without it the sensor *receives* commands and even
   executes them, but physically cannot answer. Every symptom looks like
   a dead sensor. It isn't. Both red and white go to `3V`.
2. **Yellow and brown swapped?** Yellow (sensor's voice) goes to `RX`,
   brown (sensor's ears) goes to `TX`. Crossed pairs are silent.
3. **Loose leads.** If you're using clip leads or a breadboard, tug-test
   each one. A clip that looks attached but isn't cost this project a
   full evening.
4. **Rare, but real: the board itself.** One known QT Py unit cannot
   transmit on its `TX` pad at all. `firmware/diagnostics/fp_loopback`
   settles it in two minutes with a single jumper wire — if it shows
   zeros flooding in one direction, open `firmware/dashtouch/config.h`
   and swap the two pin numbers (the comment shows you exactly where).

## The board seems completely dead

- **Is your cable a charging cable?** Plenty of USB-C cables carry no
  data. Try the cable you use for a hard drive or a camera.
- **Serial silence isn't death.** The board only speaks when the Mac
  asserts a control signal called DTR. Our tools do this automatically;
  random serial apps may not. Trust `dashtouch doctor` over a generic
  terminal app.

## It matches (green!) but nothing types

- Is the helper running? `dashtouch run` in a terminal, or
  `dashtouch install-agent` to make it permanent.
- A **steady yellow ring** after the green means exactly this: the device
  matched you, then couldn't reach the Mac side.
- Check the log: `cat /tmp/dashtouch-helper.log`

## It types the WRONG password

The Keychain copy is stale — you probably changed your Mac password.
Re-run `./setup` (it's safe to re-run; it just re-asks).

## Enrolling keeps failing

- Cover the whole ring with the flat pad of your finger, not the tip.
- Same finger both times — the sensor compares the two presses.
- Wet, dusty, or freshly-lotioned fingers read poorly.

## "More than one board is plugged in"

Unplug the one that isn't Dashboard Touch, or pass
`dashtouch --serial <which>` if you actually run two.

## Still stuck?

`firmware/diagnostics/` is a whole toolbox of tiny test programs with
their own README — loopback tests, raw sensor probes, a ring-color
survey. They exist because this build needed every one of them once.
