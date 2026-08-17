# Is this thing safe?

It's safe enough for casual users. It is _not_ best practice to have a device that types in your password for you, though. So you need to judge what feels right.

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

One field gets special treatment, because it's the one place this product
itself invites you to type right after touching the sensor: naming a
finger, right after enrollment, or renaming one later. The device actually
stops matching for as long as that field is focused (see `PAUSE` in
`docs/protocol.md`), so a stray touch there can't type your password into
a name and have it saved to `~/.dashtouch/labels.json` in plain text.

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
them for you. A third copy of that same key has to exist in plaintext on
the Mac side, briefly: `firmware/dashtouch/secrets.h`, which
`dashtouch setup`/`dashtouch pairing` write right before flashing,
because the key has to be compiled into the firmware. It's gitignored,
owner-read-only (mode `0600`), and deleted as soon as the flash
succeeds — so in normal operation it isn't on your disk at all. If a
flash *fails*, it's deliberately left behind so you can retry by hand;
that's the one case where it lingers, and it's worth deleting once
you're done, because anyone with file access to your Mac would find it
as good as the Keychain entry.

**The fingerprint sensor itself is the trusting sort.** The sensor and
the QT Py chat over a plain serial line with no authentication — that's
how this class of sensor works. Someone with physical access to the
wiring could fake a "match" signal. The classic hobbyist fix is potting
the electronics in epoxy so tampering means destroying it.

**The browser page is local-only.** The enrollment page lives at
`127.0.0.1` — your Mac only — and every action that changes something
needs a session token, so a random website you have open can't quietly
enroll a finger. The helper also checks that each request actually
addressed it as `127.0.0.1` or `localhost`. That second check matters
more than it sounds: binding to `127.0.0.1` keeps out remote *packets*,
but not remote *pages*. A site can point a hostname it controls at
`127.0.0.1` — DNS rebinding — and your browser will then treat that site
as being the same origin as the helper, which is normally enough to read
the session token straight out of the page's own API. Checking the
`Host` header is what tells a real local page apart from a rebound one.

**Replays don't work.** Every match event is numbered and signed;
yesterday's captured USB traffic can't be replayed today.[^replay-boot]

[^replay-boot]: One precision note: a `BOOT` line from the device resets
    the Mac side's replay counter, since a real reboot legitimately
    restarts numbering from zero. Someone who can *write* to the serial
    port could send a fake `BOOT` to rewind that window and replay a
    captured match event — but the reply is still a fresh, encrypted
    password payload keyed to the original nonce, undecryptable without
    the pairing key, and the real device ignores it. No password is
    disclosed either way.

## The one thing that talks to the internet

Everything above happens entirely between your Mac and the gadget on
your desk — no cloud, no account, no server of ours in the loop. There's
exactly one exception, and it's opt-in every single time.

**How it works.** Click the small refresh icon next to "Connected: v…"
and the helper — never the browser — fetches one file:
`https://raw.githubusercontent.com/anildash/dashtouch/main/version.json`.
It reads the version number out of that file and compares it, locally, to
the version you're running. That's almost the entire request: it does
carry a `User-Agent: dashtouch-helper` header, so GitHub can tell this
came from Dashboard Touch rather than a browser — no other identifiers,
no version number tucked into the URL, no telemetry, no account, no
cookies. Other than that header, it's the same GET request your browser
would make if you typed that URL in yourself and hit enter.

**It only ever happens when you click the button.** There is no check at
startup, no check on a schedule, no check when this page loads, no
background phoning home — ever. That also means the broader fact holds:
clicking that button is the *only* time Dashboard Touch talks to the
internet at all. Every other page load, every fingerprint match, every
poll of `/api/status` you see happening constantly in Under the hood —
all of that stays on `127.0.0.1`, between your Mac and the gadget.

**Why bother at all.** This is a device that types your real password.
If a security problem ever turns up in it, you need a way to actually
learn a fix exists — the honest alternative is "remember to go check
GitHub every so often," and nobody does that. So the check exists, but
on your terms: nothing runs unless you ask it to, and if what comes back
is a security fix, it's called out in red rather than buried next to a
changelog entry about icon spacing. Worth clicking occasionally, and
especially worth clicking before you hand this thing a password you
actually care about.

## So... should you?

If your threat model is "roommates, family, coffee-shop table" — the
gadget never leaves your home, nobody hostile gets alone time with your
hardware — this is a fine convenience with honest tradeoffs.

If your threat model includes "someone determined, with tools, targeting
me specifically" — or it's a work machine with things you're contractually
obligated to protect — spend the $149 on Apple's keyboard. Genuinely. Its
Secure Enclave design is the stronger answer and we're not going to
pretend otherwise.
