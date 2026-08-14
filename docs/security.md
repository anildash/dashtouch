# Is this thing safe?

Reasonable question. Here's the deal, in plain language first.

**Dashboard Touch types your real password.** When your finger matches,
the gadget acts like a tiny USB keyboard and types the same thing you
would have typed. That single fact explains both why it's great (it works
absolutely everywhere a password works) and every caution on this page.

## Things worth knowing before you build one

**It types into whatever's focused.** The gadget can't see your screen.
If the wrong window has focus when you touch the ring, your password
lands there — a chat box, a search bar, a shared doc. The helper only
answers when your Mac asks, but "which window gets the keystrokes" is
decided by macOS focus, not by us. Habit to build: touch the ring when
you see a password prompt, not before.

**If it happens anyway, here's the recovery, and it's fast.** Change
your password in System Settings first, then run
`.venv/bin/dashtouch password` — it prompts you twice, hidden, and
updates only the Keychain copy the gadget draws from. That's the whole
fix; no re-provisioning, no reflashing, and the gadget picks up the
change on its very next touch without a restart. Treat any password
that landed on a synced or logged surface — a chat you're signed into
on other devices, a screen recording, a support ticket — as compromised
the moment you notice, not after you've decided how it happened.

**Your password lives in your Mac's Keychain — never on the gadget.**
The device stores a *pairing key* (a shared secret), and each match earns
it a one-time, encrypted copy of your password that it types and
immediately forgets. Someone who steals just the gadget doesn't have
your password.

**But someone who steals the gadget AND your Mac has more options.**
The pairing key sits in the device's flash memory. A motivated person
with both devices, a soldering iron, and an afternoon could extract it
and impersonate the gadget to your Mac. The ESP32 chip supports one-way
hardware protections (secure boot, flash encryption) that close this;
they're permanent and unforgiving, so we document them but don't burn
them for you.

**The fingerprint sensor itself is the trusting sort.** The sensor and
the QT Py chat over a plain serial line with no authentication — that's
how this class of sensor works. Someone with physical access to the
wiring could fake a "match" signal. The classic hobbyist fix is potting
the electronics in epoxy so tampering means destroying it.

**The browser page is local-only.** The enrollment page lives at
`127.0.0.1` — your Mac only — and every action needs a session token, so
a random website you have open can't quietly enroll a finger.

**Replays don't work.** Every match event is numbered and signed;
yesterday's captured USB traffic can't be replayed today.

## So... should you?

If your threat model is "roommates, family, coffee-shop table" — the
gadget never leaves your home, nobody hostile gets alone time with your
hardware — this is a fine convenience with honest tradeoffs.

If your threat model includes "someone determined, with tools, targeting
me specifically" — or it's a work machine with things you're contractually
obligated to protect — spend the $149 on Apple's keyboard. Genuinely. Its
Secure Enclave design is the stronger answer and we're not going to
pretend otherwise.
