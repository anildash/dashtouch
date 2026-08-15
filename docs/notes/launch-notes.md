# Launch notes — landing page, blog post, shopping list

Working notes, not finished copy. Written 2026-08-13, the night the
rewrite passed its parity gate. Raw material is deliberately over-included;
cut on the way out, not on the way in.

---

## 1. The shopping list

Live in the README's parts table too, but collected here in the shape a
landing page wants. **Some links are affiliate links** — disclose once,
visibly, in the user's own voice.

### What you actually need (~$25)

| Part | What I used | Notes |
| --- | --- | --- |
| Fingerprint sensor | [R503-compatible, ~$10–20](https://amzn.to/4wnVuO9) | The exact unit in this build. Unbranded; self-reports 200-template capacity. |
| Microcontroller | [Adafruit QT Py ESP32-S3, $12.50](https://www.adafruit.com/product/5426) | Native USB, tiny, well-documented, active community. |
| USB-C cable | [This one](https://amzn.to/4zjg9p9) | Must carry **data**, not just power. Charge-only cables are the single most common "it's dead" false alarm. |

### Optional / alternatives

| | | |
| --- | --- | --- |
| [Adafruit R503](https://www.adafruit.com/product/4651) | Same sensor, genuine GROW branding | Frequently out of stock, ~2× the price. Worth watching if you'd rather buy from Adafruit. |
| [Cheaper ESP32-S3 board](https://amzn.to/4gjkss2) | Presumably works | **Untested in this build** — say so plainly. Similar chip, but the pin mapping and USB behavior would need checking. |
| [Ready-made enclosure](https://amzn.to/4wwqw6m) | For people who don't want to build one | Framing matters: building your own mount is the *fun* part and the project's ethos. This is the "skip the woodworking" escape hatch, not the default. |

**Cost story for the landing page:** ~$25 in parts against **$149** for a
new Magic Keyboard with Touch ID (~$55–65 used). That's roughly 84% below
new retail. Don't oversell it — the honest pitch is "you already wanted to
build something."

---

## 2. Landing page — structure and thesis

**One-line thesis:** *Touch ID for your Mac, without the $149 keyboard —
and you decide where the button lives.*

The mounting freedom is the real differentiator, not the price. Apple sells
you a keyboard with a fingerprint reader in one fixed spot. This is a
~1-inch threaded sensor you can put through a hole in **anything**: desk
edge, monitor arm, drawer front, the underside of a shelf. That's the
emotional hook — price is the rational backup.

**Suggested page order:**

1. **Hero:** the ring. It's the product's whole identity — a glowing
   circle that answers you. Video of a touch → green flash → password
   filling a login field beats any headline. If static: the ring at rest,
   purple, mounted in real wood.
2. **The honest paragraph, above the fold.** This types your real password.
   That's why it works everywhere, and it's the thing to understand before
   you build one. Link to `security.md`. Leading with the caveat *builds*
   trust for this audience — it's the tinyTouch README's best instinct and
   worth keeping.
3. **What it costs** — the table above, affiliate disclosure inline.
4. **What it looks like to use** — the LED language as a feature: purple
   ready, white reading, green match, red no, yellow "can't reach your
   Mac," cyan lift-your-finger. Six colors, no manual required.
5. **Mount it anywhere** — a gallery slot. My under-desk build, plus
   sketched patterns (desk grommet, drawer front, enclosure wall).
6. **Setup in three commands** — clone, `./setup`, enroll in the browser.
   Screenshot of the web page's Checkup card: every row green.
7. **The build story** → blog post link.
8. **GitHub, MIT, credit to [tinyTouch](https://github.com/ZimengXiong/tinyTouch).**

---

## 3. Blog post — the material

The strongest version isn't "look what I built." It's a **debugging
story with a real moral**, and the moral is unusually clean.

### The spine

Two fingerprint sensors were condemned as dead. Neither was.

- **Act 1 — the ZW111.** Weeks of debugging. Every wiring hypothesis
  eliminated by measurement, protocol verified byte-for-byte against two
  independent reference implementations. Verdict: defective part. Ordered
  a replacement.
- **Act 2 — the R503.** New sensor, identical silence. Fourteen
  baud/orientation combinations, nothing. A board-only loopback test (one
  jumper, no sensor) finally revealed the QT Py's `TX` pad **cannot carry
  UART transmit** — so no command this project had ever sent reached
  either sensor. Both verdicts instantly unsafe.
- **Act 3 — the actual cause.** Route around the dead pin, still silence.
  Then: **one unconnected wire.** Sensor pin 6, `3.3VT`, the touch-power
  supply. Without it the module powers up, receives commands, and
  *executes* them — the LED ring visibly obeys — but physically cannot
  reply. Connect the white wire; every command answers immediately.

### The moral (this is the post's actual value)

**A test that can't fail correctly is worse than no test.** The diagnostic
that condemned the first sensor reported `trailing_bytes=0` and called it
proof of silence. But the library call it wrapped *consumed the response
first* — zero was the normal reading whether the sensor answered or not.
The number was always going to be zero. It measured nothing, and it was
believed across several debugging sessions — long enough to condemn one
sensor, order a replacement, and start condemning that one too.

*(Timeline, for accuracy: the build ran Aug 3–14, 2026. Don't inflate it
— the story is that a bad metric survived repeated scrutiny, not that it
survived a long time.)*

Corollary worth its own paragraph: **a low voltage reading isn't a dead
component.** The sensor's TX line measured 2.65V against a 3.3V ideal —
damning-looking evidence of a failing output stage. It was just an
unpowered one. Same reading, opposite conclusion.

### Other beats worth including

- **The LED as an honest instrument.** The ring turned out to be the best
  diagnostic in the project: it obeyed commands while the sensor couldn't
  answer, which is precisely the signature that cracked the case. A part
  that can *hear* but not *speak* looks identical to a dead part — unless
  something visible responds.
- **Boot failure you can't display.** The ring is on the sensor, driven
  over the UART that just failed. You cannot paint an error on hardware you
  can't reach. The fix is layered: try the ring anyway (it works in the
  most common failure), document *absence of purple* as the real signal,
  and light the microcontroller's own LED — the one the sensor can't take
  down.
- **First solder joints.** This build's first-ever soldering, five joints,
  all passing electrical verification on the first try — including both
  data lines, where a marginal joint shows up instantly as garbled packets.
- **The rewrite.** 31 commits, every task reviewed by a fresh pair of eyes,
  every firmware change verified on real hardware. Bugs the reviews caught
  that testing wouldn't have: a checksum validator that could walk off a
  stack buffer, a password buffer left unwiped after a failed decrypt, a
  ring that flashed once and then never again, a status page that could
  paint "Done!" over someone else's failure.
- **The stale-token comedy.** Four separate encounters with the same class
  of failure — a browser tab holding a dead session token, failing
  silently — before the right fix (persist the token; stop rotating it)
  killed the class instead of the instance. Good example of the difference
  between fixing a bug and fixing a *kind* of bug.
- **Naming detail:** the helper's web page lives on port **3274** — DASH on
  a phone keypad.

### Framing to avoid

Don't write it as "AI built my gadget." The interesting story is the
debugging discipline: hypotheses named and eliminated, wrong conclusions
retracted in writing, and a documentation trail that let the project pick
itself up on a different machine weeks later. The `docs/history/` folder is
the receipts.

---

## 4. Assets to capture

- [ ] Hero video: touch → green flash → password appears in a login prompt
- [ ] The ring at rest (purple) in the finished mount
- [ ] Web page screenshot: Checkup card, all rows green
- [ ] Enrollment in progress: page and physical ring showing the same color
- [ ] The wiring, before enclosure — all six wires visible, white one obvious
- [ ] Optional: the `fp_colors` diagnostic cycling all seven colors
- [ ] Before/after: breadboard clip-lead sprawl → soldered build

---

## 5. Open questions to settle

- Does the landing page live at its own domain, or as a section of
  anildash.com?
- Blog post and landing page simultaneously, or post first and let the
  page follow?
- How much of the tinyTouch fork lineage goes in the post? (It's a genuine
  credit story — someone else proved the idea; this is a rebuild on
  different assumptions.)
- Comfortable naming the specific sensor listing, given the listing's own
  copy was wrong twice (claimed 500-template capacity, claimed housing
  markings that don't exist)? That's honest-review material either way.
