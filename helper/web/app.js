let token = null;
// Fetch the session token from the local helper after the page loads. The
// URL no longer carries the token, so the page must request it from the
// same-origin endpoint /api/token. Remote origins cannot read this
// response due to same-origin policy (and the server does not set CORS).
(async function fetchToken() {
  try {
    const r = await fetch("/api/token", {credentials: 'same-origin'});
    if (r.ok) {
      const j = await r.json();
      token = j.token;
    }
  } catch (e) {
    // ignore — token stays null and UI shows a helpful banner below
  }
})();
let enrolling = false;
let logInterval = null;
let lastStatus = null;

// -- finger tile row: which slot (if any) is mid-enrollment, being named
// for the first time, expanded for rename/remove, or being edited (rename/post-enroll naming).
let pendingSlot = null;
let namingSlot = null;
let selectedSlot = null;
let editingSlot = null;  // Tracks which finger is mid-edit to suppress re-renders

// -- device settings: resting ring color/style, press-Return -------------
// Optimistic local copy of {idle_color, idle_style, press_enter} while a
// change is in flight; dropped in favor of the poll's own s.settings as
// soon as one arrives, per "optimistic UI, corrected by the next poll."
let settingsOverride = null;

// -- tool strip: Help / Under the hood / (on-demand) Update available,
// open on demand, one at a time. Update available is a third tab that only
// exists once a check has found something — created lazily by
// showUpdateTab(), so tab buttons/panels are queried generically by
// data-tab / data-tab-panel rather than hardcoded ids. --------------------
let activeTab = null; // "help" | "debug" | "update" | null
// True once Help has auto-opened for the current run of trouble; reset when
// the trouble clears so a fresh problem can auto-open it again.
let helpAutoRevealed = false;

function updateTabUI() {
  document.querySelectorAll(".tab-btn[data-tab]").forEach((btn) => {
    const on = btn.dataset.tab === activeTab;
    btn.classList.toggle("tab-btn--active", on);
    btn.setAttribute("aria-selected", String(on));
  });
  document.querySelectorAll(".tab-panel[data-tab-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.tabPanel !== activeTab;
  });
}

function openTab(name) {
  if (activeTab === "debug" && name !== "debug") stopLogPolling();
  activeTab = name;
  updateTabUI();
  if (name === "debug") startLogPolling();
}

function closeTab() {
  if (activeTab === "debug") stopLogPolling();
  activeTab = null;
  updateTabUI();
}

function toggleTab(name) {
  if (activeTab === name) closeTab();
  else openTab(name);
}

document.getElementById("tab-btn-help").onclick = () => toggleTab("help");
document.getElementById("tab-btn-debug").onclick = () => toggleTab("debug");

// -- settings card: collapsed by default, no persisted state ------------
document.getElementById("settings-toggle").onclick = () => {
  const btn = document.getElementById("settings-toggle");
  const panel = document.getElementById("settings-panel");
  const open = btn.getAttribute("aria-expanded") === "true";
  btn.setAttribute("aria-expanded", String(!open));
  panel.hidden = open;
};

// Delegated (rather than bound once at load) so the Update available tab,
// added dynamically once a check finds something, gets arrow-key nav too.
document.querySelector(".tab-row").addEventListener("keydown", (e) => {
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  const all = Array.from(document.querySelectorAll('.tab-row [role="tab"]'));
  const i = all.indexOf(e.target);
  if (i === -1) return;
  e.preventDefault();
  const dir = e.key === "ArrowRight" ? 1 : -1;
  all[(i + dir + all.length) % all.length].focus();
});

// Any link into the Help entries (the static list above, or a Checkup "How
// to fix" link) needs the Help panel open before the browser's own hash
// navigation tries to scroll to it — the target is invisible while [hidden].
document.addEventListener("click", (e) => {
  const a = e.target.closest('a[href^="#help-"]');
  if (!a) return;
  if (activeTab !== "help") openTab("help");
});

function revealHelpForHash() {
  if (!location.hash.startsWith("#help-")) return;
  openTab("help");
  requestAnimationFrame(() => {
    const el = document.getElementById(location.hash.slice(1));
    if (el) el.scrollIntoView({block: "center"});
  });
}

// The token fetch above is async; if it hasn't arrived yet, show the
// helpful missing-token banner. The banner will remain if no token is
// available, and once the token arrives the page will start functioning.
if (!token) {
  const banner = document.getElementById("banner");
  banner.textContent = "Heads up — this page is missing its key, so buttons won't work. Open the helper with `dashtouch enroll` if this persists.";
  banner.hidden = false;
}

// -- on-demand update check: the product's one and only outbound network
// call, and it only happens when someone clicks this button. The helper
// (never this page) does the actual fetch — see POST /api/check-update
// in webui.py and docs/security.md. --------------------------------------
const REDUCED_MOTION = window.matchMedia
  && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
let updateChecking = false;
let updateTabShown = false;

// `withNote` appends the one-line reminder that this button is the only
// thing here that reaches the internet, linking to the fuller Help entry.
// Skipped while a check is in flight — the transient "Checking…" state
// shouldn't carry a paragraph with it.
function setUpdateLine(text, withNote = false) {
  const line = document.getElementById("update-line");
  if (!text) {
    line.hidden = true;
    line.textContent = "";
    return;
  }
  line.textContent = text;
  if (withNote) {
    line.append(" ");
    const a = document.createElement("a");
    a.href = "#help-updates";
    a.textContent = "This is the one place we send data.";
    line.append(a);
  }
  line.hidden = false;
}

// Adds the "Update available" tab beside Help / Under the hood, once per
// session — it persists once shown and is never re-checked automatically.
function showUpdateTab(data) {
  if (updateTabShown) return;
  updateTabShown = true;

  const caret = '<span class="tab-caret" aria-hidden="true"><svg viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M2.5 4.5L6 8L9.5 4.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></span>';

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "tab-btn" + (data.security ? " tab-btn--security" : "");
  btn.id = "tab-btn-update";
  btn.dataset.tab = "update";
  btn.setAttribute("role", "tab");
  btn.setAttribute("aria-selected", "false");
  btn.setAttribute("aria-controls", "tab-panel-update");
  btn.innerHTML = (data.security ? '<span class="dot dot--red" aria-hidden="true"></span> ' : "")
    + "Update available" + caret;
  btn.onclick = () => toggleTab("update");
  document.querySelector(".tab-row").appendChild(btn);

  const panel = document.createElement("div");
  panel.className = "tab-panel" + (data.security ? " tab-panel--security" : "");
  panel.id = "tab-panel-update";
  panel.dataset.tabPanel = "update";
  panel.setAttribute("role", "tabpanel");
  panel.setAttribute("aria-labelledby", "tab-btn-update");
  panel.tabIndex = 0;
  panel.hidden = true;

  const lede = data.security
    ? `<p><strong>This update fixes a security issue.</strong> Since this
       gadget types your real password, it's worth updating sooner rather
       than later.</p>`
    : "";
  const releaseLink = isSafeLinkUrl(data.url)
    ? `<p><a href="${escapeAttr(data.url)}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">More about this release</a></p>`
    : "";

  panel.innerHTML = `${lede}
    <p>Version ${escapeHtml(data.latest)} is out — you're on ${escapeHtml(data.current)}.</p>
    <p>${escapeHtml(data.headline || "")}</p>
    <p class="hint">To update: <code>git pull</code>, then re-run
    <code>./setup</code>. Only reflash the gadget (see the README's
    "Flashing by hand" section, or whatever the release notes say) if this
    update touches the firmware — the release notes will say so.</p>
    ${releaseLink}`;

  document.getElementById("tool-strip").appendChild(panel);
  openTab("update");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
}
function escapeAttr(s) {
  return escapeHtml(s);
}

// escapeHtml only neutralizes & < > " — it does nothing about the URL
// *scheme*, so a "javascript:" URL from remote content would survive it
// and execute on this token-bearing page. The server already filters
// version.json's "url" field to http(s) (see webui.py's check_update),
// but this page renders that field directly, so it re-checks rather than
// trusting the network hop between them.
function isSafeLinkUrl(s) {
  const v = String(s || "");
  return v.startsWith("https://") || v.startsWith("http://");
}

async function checkForUpdates() {
  if (updateChecking || !token) return;
  updateChecking = true;
  const btn = document.getElementById("update-check-btn");
  btn.disabled = true;
  if (REDUCED_MOTION) {
    setUpdateLine("Checking…");
  } else {
    btn.classList.add("spinning");
    setUpdateLine(null);
  }
  try {
    const r = await fetch("/api/check-update", {method: "POST",
      headers: {"Content-Type": "application/json", "X-DT-Token": token},
      body: "{}"});
    const data = await r.json();
    if (data.checked) {
      if (data.update_available) {
        setUpdateLine(null);
        showUpdateTab(data);
      } else {
        setUpdateLine("You're up to date.", true);
      }
    } else {
      setUpdateLine(data.error || "Couldn't check for updates just now.", true);
    }
  } catch {
    setUpdateLine("Can't reach the helper — is it still running?");
  } finally {
    updateChecking = false;
    btn.classList.remove("spinning");
    btn.disabled = false;
  }
}

document.getElementById("update-check-btn").onclick = checkForUpdates;

// -- the twin ring: on-screen mirror of the physical aura ------------------
const RING_CLASSES = ["ring--idle", "ring--reading", "ring--lift", "ring--match",
  "ring--nomatch", "ring--fail", "ring--helper", "ring--dark", "ring--boot-fail"];
// Idle-only modifiers layered on top of "ring--idle" — they carry the
// user's configured resting color/style, so they're tracked separately
// from RING_CLASSES (which are the mutually-exclusive status states).
const IDLE_MODIFIER_CLASSES = ["ring--idle-off", "ring--idle-breathing"];
const FLASH_MS = 1000; // 0.25s steps x 4 iterations

// Tracks the most recent event sequence number; when event_seq advances,
// the new event gets flashed. Resets on page load so the first poll never fires a stale flash.
let lastSeq = null;
let flashCls = null;
let flashStartedAt = 0;

function computeRingState(s) {
  // ONLY site where lastSeq is updated — compute once at poll time
  const firstPoll = (lastSeq === null);
  const newEvent = !firstPoll && s.event_seq > lastSeq;
  lastSeq = s.event_seq;

  if (!s.connected) return {cls: "ring--dark", label: "Not connected"};
  if (s.sensor === "fail") return {cls: "ring--boot-fail", label: "Sensor not talking"};

  // Enrollment stages mirror regardless of which client (this tab or
  // another) started them — the physical ring doesn't care who clicked.
  const stage = s.enroll_stage || "";
  if (stage === "ENROLL_WAIT_FINGER_1") return {cls: "ring--reading", label: "Reading…"};
  if (stage === "ENROLL_REMOVE_FINGER") return {cls: "ring--lift", label: "Lift your finger…"};
  if (stage === "ENROLL_WAIT_FINGER_2") return {cls: "ring--reading", label: "Same finger again…"};
  if (stage.startsWith("ENROLL_OK") || stage.startsWith("ENROLL_FAIL")) {
    const ok = stage.startsWith("ENROLL_OK");
    if (newEvent) {
      const now = Date.now();
      flashCls = ok ? "ring--match" : "ring--fail";
      flashStartedAt = now;
    }
    const now = Date.now();
    if (now - flashStartedAt < FLASH_MS) {
      return {cls: flashCls, label: ok ? "That's a match" : "Didn't recognize that"};
    }
    // The flash already ran its course — this enrollment episode is over.
    // Fall through so ordinary touches keep lighting up the ring.
  }

  const line = s.last_line || "";
  if (line === "TOUCH") return {cls: "ring--reading", label: "Reading…"};
  if (line === "TYPED") {
    if (newEvent) {
      const now = Date.now();
      flashCls = "ring--match";
      flashStartedAt = now;
    }
    const now = Date.now();
    if (now - flashStartedAt < FLASH_MS) {
      // Determine which finger matched
      let matchLabel = "That's a match";
      if (s.last_match) {
        const slotNum = s.last_match.slot;
        const slotKey = String(slotNum);
        if (s.slots && s.slots[slotKey] && s.slots[slotKey].label) {
          matchLabel = `That's your ${s.slots[slotKey].label}`;
        } else {
          matchLabel = "That's a match";
        }
      }
      return {cls: flashCls, label: matchLabel};
    }
    return {cls: "ring--idle", label: "Ready"};
  }
  if (line === "NO_MATCH") {
    if (newEvent) {
      const now = Date.now();
      flashCls = "ring--nomatch";
      flashStartedAt = now;
    }
    const now = Date.now();
    if (now - flashStartedAt < FLASH_MS) {
      return {cls: flashCls, label: "Didn't recognize that"};
    }
    return {cls: "ring--idle", label: "Ready"};
  }
  if (line === "ERR helper_timeout" || line === "ERR bad_response") {
    return {cls: "ring--helper", label: "Can't reach your Mac"};
  }

  return {cls: "ring--idle", label: "Ready"};
}

// The ring's idle appearance mirrors the device's configured resting
// color/style (settings.idle_color / settings.idle_style). Falls back to
// the historical purple/steady default while settings are still unknown —
// momentary, so no error copy.
function idleAppearance() {
  const settings = currentSettingsBase();
  const colorDef = IDLE_COLORS.find((c) => c.n === settings.idle_color) || IDLE_COLORS[3];
  const breathing = settings.idle_style === 2;
  return {colorDef, breathing};
}

function updateRing(state) {
  const {cls, label} = state;
  const ring = document.getElementById("ring");
  ring.classList.remove(...RING_CLASSES, ...IDLE_MODIFIER_CLASSES);
  ring.classList.add(cls);

  const {colorDef, breathing} = idleAppearance();
  if (cls === "ring--idle") {
    if (colorDef.n === 0) {
      // Off: no fill, no glow — just the faint --line outline handled in CSS.
      ring.style.removeProperty("--ring-idle-color");
      ring.style.removeProperty("--ring-idle-color-rgb");
      ring.classList.add("ring--idle-off");
    } else {
      // Resolve the tokens to literal values rather than passing a var()
      // reference through a custom property — that extra indirection does
      // not resolve reliably, and left the ring rendering dark.
      const root = getComputedStyle(document.documentElement);
      ring.style.setProperty(
        "--ring-idle-color", root.getPropertyValue(colorDef.cssVar).trim());
      ring.style.setProperty(
        "--ring-idle-color-rgb",
        root.getPropertyValue(`${colorDef.cssVar}-rgb`).trim());
      if (breathing) ring.classList.add("ring--idle-breathing");
    }
  }

  const ringLabel = document.getElementById("ring-label");
  if (cls === "ring--helper") {
    ringLabel.innerHTML = '<a href="#help-yellow">Can\'t reach your Mac — why?</a>';
  } else {
    ringLabel.textContent = label;
  }

  updateReadyLegendDot(colorDef);
}

// The rail legend's "Ready" swatch is the only legend entry that isn't a
// fixed status color — it always mirrors the configured idle color, even
// when the ring itself is currently showing some other state.
function updateReadyLegendDot(colorDef) {
  const dot = document.querySelector(".legend li:first-child .dot");
  if (!dot) return;
  if (colorDef.n === 0) {
    dot.style.background = "transparent";
    dot.style.boxShadow = "inset 0 0 0 1px var(--line)";
  } else {
    dot.style.background = `var(${colorDef.cssVar})`;
    dot.style.boxShadow = "";
  }
}

// A match flash is "live" for FLASH_MS after a TYPED event — used to tint
// the matching finger row's fingerprint mark in the list below.
function isMatchFlashActive() {
  return flashCls === "ring--match" && (Date.now() - flashStartedAt < FLASH_MS);
}

// -- finger tile row: macOS Touch-ID-style tiles, no slot numbers in sight -
// The page always picks the lowest free slot itself from slots_used —
// there's no picker for the user.
function lowestFreeSlot(s) {
  const used = new Set(s.slots_used || []);
  for (let i = 1; i <= 200; i++) if (!used.has(i)) return i;
  return null;
}

// Named fingers first, oldest-added first (legacy string-format entries
// carry added=0.0 from the loader, so they sort to the very front).
// Fingers enrolled outside the page (no labels.json entry) come after,
// ordered by slot, shown as "Unnamed".
function sortedFingers(s) {
  const labels = s.slots || {};
  const used = new Set((s.slots_used || []).map(String));
  const named = [];
  const unnamed = [];
  for (const k of used) {
    const entry = labels[k];
    if (entry) named.push({slot: Number(k), label: entry.label, added: entry.added});
    else unnamed.push({slot: Number(k)});
  }
  named.sort((a, b) => a.added - b.added);
  unnamed.sort((a, b) => a.slot - b.slot);
  return named.concat(unnamed.map((u) => ({slot: u.slot, label: null})));
}

function renderFingerRow(s) {
  const row = document.getElementById("finger-row");
  row.innerHTML = "";

  const matchSlot = s.last_match ? s.last_match.slot : null;
  const matchLive = isMatchFlashActive();

  for (const f of sortedFingers(s)) {
    if (f.slot === pendingSlot) continue; // shown as the pending tile instead
    const tile = document.createElement("button");
    tile.type = "button";
    tile.className = "finger-tile"
      + (f.slot === selectedSlot ? " finger-tile--selected" : "")
      + (matchLive && f.slot === matchSlot ? " finger-tile--match" : "");
    const glyph = document.createElement("span");
    glyph.className = "finger-glyph";
    glyph.setAttribute("aria-hidden", "true");
    glyph.textContent = "🫆";
    const name = document.createElement("span");
    name.className = "finger-name";
    name.textContent = f.label || "Unnamed";
    tile.appendChild(glyph);
    tile.appendChild(name);
    tile.onclick = () => selectTile(f.slot);
    row.appendChild(tile);
  }

  if (pendingSlot !== null) {
    const tile = document.createElement("div");
    tile.className = "finger-tile finger-tile--pending";
    const glyph = document.createElement("span");
    glyph.className = "finger-glyph";
    glyph.setAttribute("aria-hidden", "true");
    glyph.textContent = "🫆";
    const name = document.createElement("span");
    name.className = "finger-name";
    name.textContent = "Adding…";
    tile.appendChild(glyph);
    tile.appendChild(name);
    row.appendChild(tile);
  }

  const noneEnrolled = (s.slots_used || []).length === 0;
  const addTile = document.createElement("button");
  addTile.type = "button";
  addTile.className = "finger-tile finger-tile--add"
    + (noneEnrolled ? " finger-tile--empty" : "");
  const free = lowestFreeSlot(s);
  addTile.disabled = free === null || pendingSlot !== null || enrolling;
  const plus = document.createElement("span");
  plus.className = "finger-glyph finger-glyph--plus";
  plus.setAttribute("aria-hidden", "true");
  plus.textContent = "+";
  const addName = document.createElement("span");
  addName.className = "finger-name";
  addName.textContent = "Add a finger";
  addTile.appendChild(plus);
  addTile.appendChild(addName);
  addTile.onclick = startEnroll;
  row.appendChild(addTile);

  document.getElementById("finger-limit-hint").hidden = free !== null;
}

// Below the row: naming (right after a successful enroll), or rename +
// remove for a tile the user clicked. Never both — naming wins, since it
// only appears in the brief window right after enrollment succeeds.
function renderFingerPanel(s) {
  const panel = document.getElementById("finger-panel");
  panel.innerHTML = "";

  if (namingSlot !== null) {
    editingSlot = namingSlot;  // Mark that we're editing
    panel.hidden = false;
    const label = document.createElement("label");
    label.textContent = "Name this finger";
    const input = document.createElement("input");
    input.type = "text";
    input.className = "rename-input";
    input.maxLength = 64;
    input.placeholder = "right index";
    label.appendChild(input);
    const save = document.createElement("button");
    save.textContent = "Save";
    const doSave = () => {
      editingSlot = null;
      saveFingerName(namingSlot, input.value, false);
    };
    const doCancel = () => {
      editingSlot = null;
      namingSlot = null;
      if (lastStatus) renderFingerPanel(lastStatus);
    };
    save.onclick = doSave;
    input.onkeydown = (e) => {
      if (e.key === "Enter") { e.preventDefault(); doSave(); }
      if (e.key === "Escape") { e.preventDefault(); doCancel(); }
    };
    panel.appendChild(label);
    panel.appendChild(save);
    appendPauseNote(panel);
    requestAnimationFrame(() => input.focus());
  } else if (selectedSlot !== null) {
    editingSlot = selectedSlot;  // Mark that we're editing
    panel.hidden = false;
    const labels = s.slots || {};
    const entry = labels[String(selectedSlot)];
    const label = document.createElement("label");
    label.textContent = "Rename";
    const input = document.createElement("input");
    input.type = "text";
    input.className = "rename-input";
    input.maxLength = 64;
    input.value = entry ? entry.label : "";
    label.appendChild(input);
    const save = document.createElement("button");
    save.textContent = "Save";
    const doSave = () => {
      editingSlot = null;
      saveFingerName(selectedSlot, input.value, true);
    };
    const doCancel = () => {
      editingSlot = null;
      selectedSlot = null;
      if (lastStatus) renderFingerPanel(lastStatus);
    };
    save.onclick = doSave;
    input.onkeydown = (e) => {
      if (e.key === "Enter") { e.preventDefault(); doSave(); }
      if (e.key === "Escape") { e.preventDefault(); doCancel(); }
    };
    const remove = document.createElement("button");
    remove.className = "remove-btn";
    remove.textContent = "Remove";
    remove.onclick = () => {
      editingSlot = null;
      removeFinger(selectedSlot);
    };
    panel.appendChild(label);
    panel.appendChild(save);
    panel.appendChild(remove);
    appendPauseNote(panel);
    requestAnimationFrame(() => input.focus());
  } else {
    panel.hidden = true;
    editingSlot = null;
  }

  syncPauseState();
}

// -- pause the sensor while a naming/renaming field is open ---------------
// The bug this guards: the "Name this finger" field is shown right after
// the person just had their finger on the sensor, so a stray touch while
// it's focused would match and type their real password into the name
// field — which then gets saved to disk. The firmware actually stops
// matching for as long as this page says so (see docs/protocol.md's
// PAUSE); it also auto-resumes on its own after 90s so a crashed helper or
// a closed tab can never leave the sensor permanently deaf — this page's
// 30s refresh is just keeping that window topped up, not the mechanism
// itself. No new ring color: this is a brief, on-screen-driven state, and
// the LED language is settled (see led.h) — the page carries the feedback.
let pauseActive = false;
let pauseRefreshTimer = null;

async function sendPause(paused) {
  if (!token) return;
  try {
    await fetch("/api/pause", {method: "POST",
      headers: {"Content-Type": "application/json", "X-DT-Token": token},
      body: JSON.stringify({paused}),
      keepalive: true});
  } catch {
    // Best-effort — if this never lands, the firmware's own 90s auto-resume
    // (or the next successful refresh) is the backstop.
  }
}

// Called every time the finger panel re-renders — the single place that
// knows whether a naming/renaming field is currently open.
function syncPauseState() {
  const shouldPause = namingSlot !== null || selectedSlot !== null;
  if (shouldPause === pauseActive) return;
  pauseActive = shouldPause;
  if (shouldPause) {
    sendPause(true);
    // Refresh well inside the firmware's 90s auto-resume window so a long
    // pause (someone thinking about what to name a finger) never lapses.
    pauseRefreshTimer = setInterval(() => sendPause(true), 30000);
  } else {
    if (pauseRefreshTimer) clearInterval(pauseRefreshTimer);
    pauseRefreshTimer = null;
    sendPause(false);
  }
}

// Closing the tab shouldn't make someone wait out the firmware's timeout —
// resume immediately if we were the one holding it paused.
function resumeOnUnload() {
  if (pauseActive) sendPause(false);
}
window.addEventListener("pagehide", resumeOnUnload);
window.addEventListener("beforeunload", resumeOnUnload);

function appendPauseNote(panel) {
  const note = document.createElement("p");
  note.className = "pause-note";
  note.textContent = "The sensor's paused while you type, so it can't type your password in here by accident.";
  panel.appendChild(note);
}

function selectTile(slot) {
  namingSlot = null;
  selectedSlot = selectedSlot === slot ? null : slot;
  if (lastStatus) {
    renderFingerRow(lastStatus);
    renderFingerPanel(lastStatus);
  }
}

async function startEnroll() {
  if (!lastStatus) return;
  const slot = lowestFreeSlot(lastStatus);
  if (slot === null) return;
  document.getElementById("progress").textContent = "Starting…";
  try {
    const response = await fetch("/api/enroll", {method: "POST",
      headers: {"Content-Type": "application/json", "X-DT-Token": token},
      body: JSON.stringify({slot, label: ""})});
    if (response.ok) {
      enrolling = true;
      pendingSlot = slot;
      selectedSlot = null;
      namingSlot = null;
      if (activeTab === "debug" && !logInterval && token) {
        fetchLog();
        logInterval = setInterval(fetchLog, 1000);
      }
      renderFingerRow(lastStatus);
      renderFingerPanel(lastStatus);
    } else {
      document.getElementById("progress").textContent = "That didn't go through — this page has probably gone stale. Close this tab and open the fresh link from the helper (or run .venv/bin/dashtouch enroll).";
    }
  } catch {
    document.getElementById("progress").textContent = "Can't reach the helper — is it still running?";
  }
}

async function saveFingerName(slot, value, isRename) {
  try {
    const response = await fetch("/api/label", {method: "POST",
      headers: {"Content-Type": "application/json", "X-DT-Token": token},
      body: JSON.stringify({slot, label: value})});
    if (!response.ok) {
      document.getElementById("progress").textContent = "That didn't go through — this page has probably gone stale. Close this tab and open the fresh link from the helper (or run .venv/bin/dashtouch enroll).";
      return;
    }
    if (isRename) selectedSlot = null; else namingSlot = null;
    refresh();
  } catch {
    document.getElementById("progress").textContent = "Can't reach the helper — is it still running?";
  }
}

async function removeFinger(slot) {
  try {
    const response = await fetch("/api/delete", {method: "POST",
      headers: {"Content-Type": "application/json", "X-DT-Token": token},
      body: JSON.stringify({slot})});
    if (!response.ok) {
      document.getElementById("progress").textContent = "That didn't go through — this page has probably gone stale. Close this tab and open the fresh link from the helper (or run .venv/bin/dashtouch enroll).";
      return;
    }
    selectedSlot = null;
    refresh();
  } catch {
    document.getElementById("progress").textContent = "Can't reach the helper — is it still running?";
  }
}

// -- device settings: resting ring color/style, press-Return -------------
const IDLE_COLORS = [
  {n: 0, name: "Off", cssVar: null},
  {n: 1, name: "Red", cssVar: "--aura-red"},
  {n: 2, name: "Blue", cssVar: "--aura-blue"},
  {n: 3, name: "Purple", cssVar: "--aura-purple"},
  {n: 4, name: "Green", cssVar: "--aura-green"},
  {n: 5, name: "Yellow", cssVar: "--aura-yellow"},
  {n: 6, name: "Cyan", cssVar: "--aura-cyan"},
  {n: 7, name: "White", cssVar: "--aura-white"},
];
// What each collision color normally signals elsewhere in the LED
// language — shown as a caution when the user picks one of these five for
// their resting color. 2 (blue) and 3 (purple) are unclaimed, so absent
// here on purpose.
const COLOR_COLLISION_MEANING = {
  1: "the gadget has a problem",
  4: "a match",
  5: "it can't reach your Mac",
  6: "lift your finger, during enrollment",
  7: "it's reading your finger",
};

async function postSetting(key, value) {
  try {
    const response = await fetch("/api/settings", {method: "POST",
      headers: {"Content-Type": "application/json", "X-DT-Token": token},
      body: JSON.stringify({key, value})});
    if (!response.ok) {
      document.getElementById("progress").textContent = "That didn't go through — this page has probably gone stale. Close this tab and open the fresh link from the helper (or run .venv/bin/dashtouch enroll).";
    }
  } catch {
    document.getElementById("progress").textContent = "Can't reach the helper — is it still running?";
  }
}

function currentSettingsBase() {
  if (settingsOverride) return settingsOverride;
  if (lastStatus && lastStatus.settings) return lastStatus.settings;
  return {idle_color: 3, idle_style: 1, press_enter: true};
}

function setIdleColor(n) {
  settingsOverride = {...currentSettingsBase(), idle_color: n};
  if (lastStatus) renderSettings(lastStatus);
  postSetting("idle_color", n);
}

function setIdleStyle(n) {
  settingsOverride = {...currentSettingsBase(), idle_style: n};
  if (lastStatus) renderSettings(lastStatus);
  postSetting("idle_style", n);
}

function setPressEnter(on) {
  settingsOverride = {...currentSettingsBase(), press_enter: on};
  if (lastStatus) renderSettings(lastStatus);
  postSetting("press_enter", on ? 1 : 0);
}

function renderSettings(s) {
  const settings = settingsOverride || s.settings;
  const known = !!settings;
  const disabled = !known || !token;

  document.getElementById("settings-reading").hidden =
    known || !s.connected;

  const active = settings || {idle_color: 3, idle_style: 1, press_enter: true};

  // -- resting color swatches --
  const swatchRow = document.getElementById("swatch-row");
  swatchRow.innerHTML = "";
  for (const c of IDLE_COLORS) {
    const item = document.createElement("span");
    item.className = "swatch-item";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "idle-color";
    input.id = `idle-color-${c.n}`;
    input.className = "sr-only-radio";
    input.checked = active.idle_color === c.n;
    input.disabled = disabled;
    input.setAttribute("aria-label", c.name);
    input.onchange = () => setIdleColor(c.n);
    const label = document.createElement("label");
    label.setAttribute("for", input.id);
    label.className = "swatch" + (c.n === 0 ? " swatch--off" : "")
      + (active.idle_color === c.n ? " swatch--selected" : "");
    if (c.cssVar) label.style.setProperty("--swatch-color", `var(${c.cssVar})`);
    if (active.idle_color === c.n) label.innerHTML = CHECK_ICONS.ok;
    item.appendChild(input);
    item.appendChild(label);
    swatchRow.appendChild(item);
  }

  const caution = document.getElementById("settings-color-caution");
  const meaning = COLOR_COLLISION_MEANING[active.idle_color];
  if (meaning && known) {
    const name = IDLE_COLORS.find((c) => c.n === active.idle_color).name;
    caution.textContent = `${name} normally means ${meaning}.`;
    caution.hidden = false;
  } else {
    caution.hidden = true;
  }

  // -- resting style: hidden entirely when the color is Off --
  const styleRow = document.getElementById("settings-style-row");
  styleRow.hidden = !known || active.idle_color === 0;
  if (!styleRow.hidden) {
    const styleOptions = document.getElementById("style-options");
    styleOptions.innerHTML = "";
    for (const [n, label] of [[1, "Steady"], [2, "Breathing"]]) {
      const opt = document.createElement("label");
      opt.className = "style-option";
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "idle-style";
      input.value = n;
      input.checked = active.idle_style === n;
      input.disabled = disabled;
      input.onchange = () => setIdleStyle(n);
      opt.appendChild(input);
      opt.appendChild(document.createTextNode(label));
      styleOptions.appendChild(opt);
    }

    const preview = document.getElementById("style-preview");
    const colorDef = IDLE_COLORS.find((c) => c.n === active.idle_color);
    if (colorDef && colorDef.cssVar) {
      preview.style.setProperty("--swatch-color", `var(${colorDef.cssVar})`);
      preview.style.setProperty("--swatch-color-rgb", `var(${colorDef.cssVar}-rgb)`);
    }
    preview.classList.toggle("style-preview--breathing", active.idle_style === 2);
  }

  // -- press Return after typing --
  const toggle = document.getElementById("press-enter-toggle");
  toggle.checked = !!active.press_enter;
  toggle.disabled = disabled;
  toggle.onchange = () => setPressEnter(toggle.checked);
}

// -- status marks: checkmark (ok) / empty checkbox (off) / x (bad) / warn --
const CHECK_ICONS = {
  ok: '<svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3 8.5L6.2 11.5L13 4.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  off: '<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg"><rect x="2.5" y="2.5" width="11" height="11" rx="2.5"/></svg>',
  bad: '<svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M4 4L12 12M12 4L4 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  warn: '<svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M8 2L15 14H1L8 2Z" fill="currentColor"/><rect x="7.25" y="6" width="1.5" height="4" fill="var(--ink)"/><rect x="7.25" y="11" width="1.5" height="1.5" fill="var(--ink)"/></svg>',
};

// -- checkup: setup health rows from /api/status, each with a "how to fix" --
// link into the symptom-keyed Help entry below when it's not ok.
function updateCheckup(s) {
  const rows = s.health || [];
  const ul = document.getElementById("checkup");
  ul.innerHTML = "";
  let failing = false;

  for (const row of rows) {
    // state is the authoritative source; fall back to ok for older shapes.
    const state = row.state || (row.ok === true ? "ok" : row.ok === false ? "bad" : "off");
    if (state === "bad") failing = true;

    const li = document.createElement("li");
    li.className = "checkup-row" + (state === "bad" ? " checkup-row--fail" : "");

    const mark = document.createElement("span");
    mark.className = `check-mark check-mark--${state}`;
    mark.innerHTML = CHECK_ICONS[state] || CHECK_ICONS.off;
    li.appendChild(mark);

    const text = document.createElement("span");
    text.className = "checkup-text";
    text.textContent = `${row.label}: ${row.detail}`;
    li.appendChild(text);

    if (state === "bad" || state === "warn") {
      const fix = document.createElement("a");
      fix.className = "checkup-fix";
      fix.href = `#${row.fix}`;
      fix.textContent = "How to fix";
      li.appendChild(fix);
    }

    ul.appendChild(li);
  }

  document.getElementById("health-summary").hidden = !failing;
  document.getElementById("checkup-section").classList.toggle("checkup-section--alert", failing);
  return failing;
}

async function refresh() {
  const r = await fetch("/api/status");
  if (!r.ok && r.status === 403) {
    document.getElementById("progress").textContent = "That didn't go through — this page has probably gone stale. Close this tab and open the fresh link from the helper (or run .venv/bin/dashtouch enroll).";
    if (logInterval) clearInterval(logInterval);
    logInterval = null;
    return;
  }
  const s = await r.json();
  lastStatus = s;

  // Suppress finger panel re-renders while an edit is in progress.
  // Belt and braces: also check if the active element is an input in the panel.
  const panelEl = document.getElementById("finger-panel");
  const activeIsInput = document.activeElement && panelEl && panelEl.contains(document.activeElement);
  if (editingSlot !== null || activeIsInput) {
    // Skip the panel rebuild this tick — let the edit continue undisturbed.
    // Update everything else normally.
    editingSlot = editingSlot || (activeIsInput ? true : null);  // Keep track if we detected focus
  } else {
    // Safe to rebuild: no edit in progress.
    editingSlot = null;
  }

  document.getElementById("conn-text").textContent = s.connected
    ? `Connected: v${s.fw || ""}`
    : "Not connected. Is it plugged in?";
  document.getElementById("update-check-btn").hidden = !s.connected;

  // Re-render an already-fetched result rather than checking again — the
  // daemon only ever populates last_update_check from an explicit click.
  if (!updateTabShown && s.last_update_check && s.last_update_check.checked
      && s.last_update_check.update_available) {
    showUpdateTab(s.last_update_check);
  }

  const cap = s.cap ? Number(s.cap) : 200;
  const used = (s.slots_used || []).length;
  document.getElementById("slots-counter").textContent = `${used} of ${cap} slots used`;

  // Real settings data wins over any optimistic guess as soon as it arrives.
  if (s.settings) {
    settingsOverride = null;
  }
  renderSettings(s);

  // Single call site for computeRingState — it's also where lastSeq
  // advances, so it must run exactly once per poll.
  const ringState = computeRingState(s);
  updateRing(ringState);
  const failing = updateCheckup(s);

  const trouble = failing || ringState.cls === "ring--helper" || ringState.cls === "ring--boot-fail";
  if (trouble) {
    if (!helpAutoRevealed) {
      helpAutoRevealed = true;
      if (activeTab !== "help") openTab("help");
    }
  } else {
    helpAutoRevealed = false;
  }

  if (enrolling && s.enroll_stage) {
    const nice = {
      "ENROLL_WAIT_FINGER_1": "Place your finger on the ring…",
      "ENROLL_REMOVE_FINGER": "Lift it off (ring goes cyan)…",
      "ENROLL_WAIT_FINGER_2": "Same finger again…",
    }[s.enroll_stage] || (s.enroll_stage.startsWith("ENROLL_OK")
      ? "Done! That finger works now."
      : s.enroll_stage.startsWith("ENROLL_FAIL")
      ? "That didn't take — try again with the pad flat on the ring."
      : s.enroll_stage);
    document.getElementById("progress").textContent = nice;
    if (s.enroll_stage.startsWith("ENROLL_OK")) {
      // A successful enrollment always moves straight into naming — the
      // fingerprint is stored, but no name exists yet. If some other
      // client (serial, another tab) drove this enrollment, pendingSlot is
      // null here and there's nothing of ours to name.
      if (pendingSlot !== null) namingSlot = pendingSlot;
      pendingSlot = null;
      enrolling = false;
    } else if (s.enroll_stage.startsWith("ENROLL_FAIL")) {
      // Failure leaves no tile and no name — pendingSlot simply clears,
      // dropping the pending tile from the row on the next render.
      pendingSlot = null;
      enrolling = false;
    }
  }

  renderFingerRow(s);
  // Skip panel rebuild if an edit is in progress — this preserves focus and text in the input.
  if (editingSlot === null) {
    renderFingerPanel(s);
  }
}

// -- debug view: live device/helper activity feed --------------------------
const DIR_PREFIX = {device: "device → ", host: "→ device ", web: "web  ", helper: "helper  "};

function formatEvent(e) {
  const ts = new Date(e.t * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  const hhmmss = `${pad(ts.getHours())}:${pad(ts.getMinutes())}:${pad(ts.getSeconds())}`;
  const prefix = DIR_PREFIX[e.dir] || `${e.dir} `;
  return `${hhmmss}  ${prefix}${e.text}`;
}

async function fetchLog() {
  if (!token) return;
  try {
    const r = await fetch("/api/log", {headers: {"X-DT-Token": token}});
    if (!r.ok) {
      if (r.status === 403) {
        document.getElementById("progress").textContent = "That didn't go through — this page has probably gone stale. Close this tab and open the fresh link from the helper (or run .venv/bin/dashtouch enroll).";
        if (logInterval) clearInterval(logInterval);
        logInterval = null;
      }
      return;
    }
    const data = await r.json();
    const logEl = document.getElementById("log");
    logEl.textContent = (data.events || []).map(formatEvent).join("\n");
    logEl.scrollTop = logEl.scrollHeight;
  } catch {
    // Helper unreachable right now — leave the last-known log on screen.
  }
}

function startLogPolling() {
  if (logInterval || !token) return;
  fetchLog();
  logInterval = setInterval(fetchLog, 1000);
}

function stopLogPolling() {
  if (logInterval) clearInterval(logInterval);
  logInterval = null;
}

revealHelpForHash();
window.addEventListener("hashchange", revealHelpForHash);

setInterval(refresh, 800);
refresh();
