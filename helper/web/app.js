const token = new URLSearchParams(location.search).get("token");
let enrolling = false;
let logInterval = null;
let lastStatus = null;

// -- finger tile row: which slot (if any) is mid-enrollment, being named
// for the first time, or expanded for rename/remove.
let pendingSlot = null;
let namingSlot = null;
let selectedSlot = null;

// -- tool strip: Help / Under the hood open on demand, one at a time -------
let activeTab = null; // "help" | "debug" | null
// True once Help has auto-opened for the current run of trouble; reset when
// the trouble clears so a fresh problem can auto-open it again.
let helpAutoRevealed = false;

function updateTabUI() {
  const helpBtn = document.getElementById("tab-btn-help");
  const debugBtn = document.getElementById("tab-btn-debug");
  const helpPanel = document.getElementById("tab-panel-help");
  const debugPanel = document.getElementById("tab-panel-debug");

  helpBtn.classList.toggle("tab-btn--active", activeTab === "help");
  helpBtn.setAttribute("aria-selected", String(activeTab === "help"));
  helpPanel.hidden = activeTab !== "help";

  debugBtn.classList.toggle("tab-btn--active", activeTab === "debug");
  debugBtn.setAttribute("aria-selected", String(activeTab === "debug"));
  debugPanel.hidden = activeTab !== "debug";
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

document.querySelectorAll('.tab-row [role="tab"]').forEach((btn, i, all) => {
  btn.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const dir = e.key === "ArrowRight" ? 1 : -1;
    all[(i + dir + all.length) % all.length].focus();
  });
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

if (!token) {
  const banner = document.getElementById("banner");
  banner.textContent = "Heads up — this page is missing its key, so buttons won't work. Open the link the helper prints when it starts, or run .venv/bin/dashtouch enroll.";
  banner.hidden = false;
}

// -- the twin ring: on-screen mirror of the physical aura ------------------
const RING_CLASSES = ["ring--idle", "ring--reading", "ring--lift", "ring--match",
  "ring--nomatch", "ring--fail", "ring--helper", "ring--dark", "ring--boot-fail"];
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

function updateRing(state) {
  const {cls, label} = state;
  const ring = document.getElementById("ring");
  ring.classList.remove(...RING_CLASSES);
  ring.classList.add(cls);
  const ringLabel = document.getElementById("ring-label");
  if (cls === "ring--helper") {
    ringLabel.innerHTML = '<a href="#help-yellow">Can\'t reach your Mac — why?</a>';
  } else {
    ringLabel.textContent = label;
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

  const addTile = document.createElement("button");
  addTile.type = "button";
  addTile.className = "finger-tile finger-tile--add";
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
    save.onclick = () => saveFingerName(namingSlot, input.value, false);
    panel.appendChild(label);
    panel.appendChild(save);
    requestAnimationFrame(() => input.focus());
  } else if (selectedSlot !== null) {
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
    save.onclick = () => saveFingerName(selectedSlot, input.value, true);
    const remove = document.createElement("button");
    remove.className = "remove-btn";
    remove.textContent = "Remove";
    remove.onclick = () => removeFinger(selectedSlot);
    panel.appendChild(label);
    panel.appendChild(save);
    panel.appendChild(remove);
  } else {
    panel.hidden = true;
  }
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

// -- checkup: setup health rows from /api/status, each with a "how to fix" --
// link into the symptom-keyed Help entry below when it's not ok.
function updateCheckup(s) {
  const rows = s.health || [];
  const ul = document.getElementById("checkup");
  ul.innerHTML = "";
  let failing = false;

  for (const row of rows) {
    if (row.ok === false) failing = true;

    const li = document.createElement("li");
    li.className = "checkup-row" + (row.ok === false ? " checkup-row--fail" : "");

    const dot = document.createElement("span");
    dot.className = "dot " + (row.ok === true ? "dot--green"
                              : row.ok === false ? "dot--red"
                              : "dot--muted");
    li.appendChild(dot);

    const text = document.createElement("span");
    text.className = "checkup-text";
    text.textContent = `${row.label} — ${row.detail}`;
    li.appendChild(text);

    if (row.ok === false) {
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

  document.getElementById("conn").textContent = s.connected
    ? `Connected — firmware ${s.fw}`
    : "Not connected. Is it plugged in?";
  document.getElementById("sensorline").textContent =
    s.sensor === "ok" ? "Sensor: happy"
                      : s.sensor === "fail" ? "Sensor: not answering — check the wiring"
                      : "";
  if (s.cap) {
    const used = (s.slots_used || []).length;
    const usedText = used === 0 ? "none used yet" : used === 1 ? "1 used" : `${used} used`;
    document.getElementById("capline").textContent = `${s.cap} finger slots (${usedText})`;
  } else {
    document.getElementById("capline").textContent = "";
  }

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
  renderFingerPanel(s);
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
