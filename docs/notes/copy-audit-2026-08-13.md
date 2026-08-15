# Copy audit — 2026-08-13

Walked the user sequence end to end: README top → wiring → quickstart →
`./setup` output → `dashtouch setup` → the web page (Checkup, device card,
ring, enroll form, enrolled list, Help, Under the hood) → enrollment flow →
error/edge copy → `dashtouch doctor` → `dashtouch install-agent` →
troubleshooting.md → security.md.

## What changed

**README.md**
- Parts table now uses the brief's real links: fingerprint sensor
  (Amazon, what I used), Adafruit R503 as the alternative (noted:
  often out of stock, costs nearly twice as much, same part), the
  data-capable USB-C cable, and the cheaper-board possibility framed
  honestly as untested ("presumably... try it and report back").
- Added the one-line affiliate disclosure near the parts table.
- Added the enclosure link as the "skip the woodworking" option,
  right alongside the existing build-your-own panel-mounting text —
  didn't touch that ethos.
- The ring table now links to `docs/troubleshooting.md`.

**docs/troubleshooting.md**
- The board-fault step (#4 under "ring never turns purple") now links
  to `firmware/diagnostics/README.md` instead of just naming a path.
- The dead-board cable bullet links the data-capable cable.
- Three commands (`dashtouch doctor`, `dashtouch run` / `install-agent`,
  `dashtouch --serial`) were missing the `.venv/bin/` prefix that
  actually works — fixed to match the rest of the docs.

**helper/dashtouch_helper/cli.py**
- `cmd_enroll`'s "helper isn't running" message was telling people to
  run `dashtouch run` — missing `.venv/bin/`, so it wouldn't have
  worked as typed. Fixed.

**helper/web/index.html**
- The two Help summary bullets ("never turns purple" / "turns yellow")
  now link down to their full entries (`#help-no-purple`, `#help-yellow`)
  instead of just repeating a shorter version of the same text.
- The "Not connected" help entry now links the data-capable cable
  alongside the existing "try the one you'd use for a hard drive"
  advice.

## Left alone, on purpose

- `helper/dashtouch_helper/webui.py` prints the boot URL to the
  terminal — it's out of scope for this pass (not in the brief's file
  list), and its one line of user-facing text ("port N was busy —
  moved to ephemeral") was already fine.
- `docs/security.md` reads consistently with the rest of the project
  already (plain language, honest tradeoffs, no apology-toned errors)
  — no changes needed there beyond the skim the brief asked for.
- `docs/superpowers/plans/2026-08-13-dashboard-touch-rewrite.md` still
  has a stale `8737` reference, but it's a planning doc, not
  user-facing copy, and outside the brief's file list — left as is.
- Did not add a link for the "cheaper board" or "Adafruit R503"
  alternative anywhere but the parts table — the brief's binding list
  scopes those to that one spot, and repeating them elsewhere would
  read as a link dump.
- No stale port `8737` found in any in-scope, user-facing file; `3274`
  is used consistently everywhere it appears.
