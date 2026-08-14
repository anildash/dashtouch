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
   transmit on its `TX` pad at all. [firmware/diagnostics/](../firmware/diagnostics/README.md)
   has `fp_loopback`, which settles it in two minutes with a single jumper
   wire — if it shows zeros flooding in one direction, run
   `.venv/bin/dashtouch pins --swap`. It moves the sensor UART to the
   other pin pair on the spot, no reflash needed, and tells you right
   away whether the sensor comes back. Only the sensor wiring is
   affected — the USB link to your Mac never changes — so it's always
   safe to try.

## The board seems completely dead

- **Is your cable a charging cable?** Plenty of USB-C cables carry no
  data. Try the cable you use for a hard drive or a camera — or grab
  [a data-capable one](https://amzn.to/4zjg9p9) if you're not sure yours
  qualifies.
- **Serial silence isn't death.** The board only speaks when the Mac
  asserts a control signal called DTR. Our tools do this automatically;
  random serial apps may not. Trust `.venv/bin/dashtouch doctor` over a generic
  terminal app.

## It matches (green!) but nothing types

- Is the helper running? `.venv/bin/dashtouch run` in a terminal, or
  `.venv/bin/dashtouch install-agent` to make it permanent.
- A **steady yellow ring** after the green means exactly this: the device
  matched you, then couldn't reach the Mac side.
- Check the log: `cat /tmp/dashtouch-helper.log`

## It types the wrong password

The Keychain copy is stale — you probably changed your Mac password (or
it ended up somewhere it shouldn't have, and you already changed it).
Either way: `.venv/bin/dashtouch password`. It prompts you twice,
hidden, and updates only the Keychain entry — nothing else about your
setup changes, and the fix takes effect on your very next touch with no
restart needed. (`./setup` also works, but it's the sledgehammer — it
regenerates the pairing key too and expects a reflash. Reach for
`dashtouch password` first.)

If your password ended up typed somewhere it shouldn't — a chat, a
shared screen, anywhere synced or logged — treat that old password as
burned. Change it in System Settings, then run the command above right
away.

## Fingerprints stopped working after setup

This is a pairing mismatch, not a fingerprint problem — your prints are
still safe on the sensor. It happens when the pairing key changed
Mac-side (via `.venv/bin/dashtouch pairing`, or a re-run of `./setup`)
but the firmware never got reflashed with it. The Checkup's Pairing row
will show red, and every touch's signature gets silently rejected.

Fix: `.venv/bin/dashtouch pairing` walks you through generating a fresh
key and reflashing in one go — run it again if you skipped the flash
step the first time, or flash by hand with the commands it prints.

## Enrolling keeps failing

- Cover the whole ring with the flat pad of your finger, not the tip.
- Same finger both times — the sensor compares the two presses.
- Wet, dusty, or freshly-lotioned fingers read poorly.

## "More than one board is plugged in"

Unplug the one that isn't Dashboard Touch, or pass
`.venv/bin/dashtouch --serial <which>` if you actually run two.

## Still stuck?

`firmware/diagnostics/` is a whole toolbox of tiny test programs with
their own README — loopback tests, raw sensor probes, a ring-color
survey. They exist because this build needed every one of them once.
