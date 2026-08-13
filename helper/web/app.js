const token = new URLSearchParams(location.search).get("token");
let enrolling = false;
let logVisible = false;
let logInterval = null;

if (!token) {
  const banner = document.getElementById("banner");
  banner.textContent = "Heads up — this page is missing its key, so buttons won't work. Open the link the helper prints when it starts, or run .venv/bin/dashtouch enroll.";
  banner.hidden = false;
}

// -- the twin ring: on-screen mirror of the physical aura ------------------
const RING_CLASSES = ["ring--idle", "ring--reading", "ring--lift", "ring--match",
  "ring--nomatch", "ring--fail", "ring--helper", "ring--dark", "ring--boot-fail"];
const FLASH_MS = 1000; // 0.25s steps x 4 iterations

// Tracks the most recent line/stage that triggered a flash, so a poll that
// sees the same event twice doesn't re-flash it — it settles to idle once
// and stays there until a genuinely new event arrives.
let flash = {key: null, cls: null, startedAt: 0};

function flashOrSettle(key, cls, label) {
  const now = Date.now();
  if (flash.key !== key) flash = {key, cls, startedAt: now};
  if (now - flash.startedAt < FLASH_MS) return {cls: flash.cls, label};
  return {cls: "ring--idle", label: "Ready"};
}

function computeRingState(s) {
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
    const settled = flashOrSettle(stage, ok ? "ring--match" : "ring--fail",
                                  ok ? "That's a match" : "Didn't recognize that");
    if (settled.cls !== "ring--idle") return settled;
    // The flash already ran its course — this enrollment episode is over.
    // Fall through so ordinary touches keep lighting up the ring.
  }

  const line = s.last_line || "";
  if (line === "TOUCH") return {cls: "ring--reading", label: "Reading…"};
  if (line === "TYPED") return flashOrSettle(line, "ring--match", "That's a match");
  if (line === "NO_MATCH") return flashOrSettle(line, "ring--nomatch", "Didn't recognize that");
  if (line === "ERR helper_timeout" || line === "ERR bad_response") {
    return {cls: "ring--helper", label: "Can't reach your Mac"};
  }

  return {cls: "ring--idle", label: "Ready"};
}

function updateRing(s) {
  const {cls, label} = computeRingState(s);
  const ring = document.getElementById("ring");
  ring.classList.remove(...RING_CLASSES);
  ring.classList.add(cls);
  document.getElementById("ring-label").textContent = label;
}

// -- slot dropdown: truthful list of FREE slots, from the sensor's own ----
// index table (slots_used), not a guess based on local labels.
let lastFreeKey = null;

function updateSlotSelect(s) {
  const used = new Set(s.slots_used || []);
  const free = [];
  for (let i = 1; i <= 200; i++) if (!used.has(i)) free.push(i);
  const key = free.join(",");
  if (key === lastFreeKey) return; // unchanged — leave the user's pick alone
  lastFreeKey = key;

  const select = document.getElementById("slot");
  const prev = select.value;
  select.innerHTML = "";
  if (free.length === 0) {
    const opt = document.createElement("option");
    opt.textContent = "No free slots";
    opt.disabled = true;
    select.appendChild(opt);
    return;
  }
  for (const n of free) {
    const opt = document.createElement("option");
    opt.value = String(n);
    opt.textContent = String(n);
    select.appendChild(opt);
  }
  // Keep the previous pick if it's still free; otherwise the first option
  // (the lowest free slot) is selected by default.
  if (free.includes(Number(prev))) select.value = prev;
}

// -- enrolled list: union of device truth (slots_used) and local labels ---
// A used slot with no label (enrolled from the device itself) still shows.
function updateSlotList(s) {
  const labels = s.slots || {};
  const seen = new Set((s.slots_used || []).map(String));
  for (const k of Object.keys(labels)) seen.add(k);
  const rows = Array.from(seen, Number).sort((a, b) => a - b);

  const ul = document.getElementById("slots");
  ul.innerHTML = "";
  for (const slot of rows) {
    const label = labels[String(slot)];
    const li = document.createElement("li");
    const num = document.createElement("span");
    num.className = "slot-num";
    num.textContent = String(slot);
    li.appendChild(num);
    li.appendChild(document.createTextNode(` · ${label || "(unnamed)"}`));
    const del = document.createElement("button");
    del.className = "remove-btn";
    del.textContent = "Remove";
    del.onclick = async () => {
      try {
        const response = await fetch("/api/delete", {method: "POST",
          headers: {"Content-Type": "application/json", "X-DT-Token": token},
          body: JSON.stringify({slot})});
        if (!response.ok) {
          document.getElementById("progress").textContent = "That didn't go through — this page has probably gone stale. Close this tab and open the fresh link from the helper (or run .venv/bin/dashtouch enroll).";
        }
      } catch {
        document.getElementById("progress").textContent = "Can't reach the helper — is it still running?";
      }
    };
    li.appendChild(del);
    ul.appendChild(li);
  }
}

async function refresh() {
  const r = await fetch("/api/status");
  const s = await r.json();

  document.getElementById("conn").textContent = s.connected
    ? `Connected — firmware ${s.fw}`
    : "Not connected. Is it plugged in?";
  document.getElementById("sensorline").textContent =
    s.sensor === "ok" ? "Sensor: happy"
                      : s.sensor === "fail" ? "Sensor: not answering — check the wiring"
                      : "";
  document.getElementById("capline").textContent = s.cap ? `${s.cap} finger slots` : "";

  updateRing(s);

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
    if (s.enroll_stage.startsWith("ENROLL_OK") || s.enroll_stage.startsWith("ENROLL_FAIL")) {
      enrolling = false;
    }
  }

  updateSlotSelect(s);
  updateSlotList(s);
}

document.getElementById("enroll").onclick = async () => {
  const slot = Number(document.getElementById("slot").value);
  const label = document.getElementById("label").value;
  document.getElementById("progress").textContent = "Starting…";
  try {
    const response = await fetch("/api/enroll", {method: "POST",
      headers: {"Content-Type": "application/json", "X-DT-Token": token},
      body: JSON.stringify({slot, label})});
    if (response.ok) {
      enrolling = true;
    } else {
      document.getElementById("progress").textContent = "That didn't go through — this page has probably gone stale. Close this tab and open the fresh link from the helper (or run .venv/bin/dashtouch enroll).";
    }
  } catch {
    document.getElementById("progress").textContent = "Can't reach the helper — is it still running?";
  }
};

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
    if (!r.ok) return;
    const data = await r.json();
    const logEl = document.getElementById("log");
    logEl.textContent = (data.events || []).map(formatEvent).join("\n");
    logEl.scrollTop = logEl.scrollHeight;
  } catch {
    // Helper unreachable right now — leave the last-known log on screen.
  }
}

document.getElementById("debug-toggle").onclick = () => {
  logVisible = !logVisible;
  const logEl = document.getElementById("log");
  const btn = document.getElementById("debug-toggle");
  if (logVisible) {
    logEl.style.display = "block";
    btn.textContent = "Hide";
    if (token) {
      fetchLog();
      logInterval = setInterval(fetchLog, 1000);
    }
  } else {
    logEl.style.display = "none";
    btn.textContent = "Show what's happening";
    if (logInterval) {
      clearInterval(logInterval);
      logInterval = null;
    }
  }
};

setInterval(refresh, 800);
refresh();
