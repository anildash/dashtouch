const token = new URLSearchParams(location.search).get("token");
let enrolling = false;
let logVisible = false;
let logInterval = null;

if (!token) {
  document.getElementById("progress").textContent = "Heads up — this page is missing its key, so buttons won't work. Open the link the helper prints when it starts, or run .venv/bin/dashtouch enroll.";
}

async function refresh() {
  const r = await fetch("/api/status");
  const s = await r.json();
  document.getElementById("conn").textContent = s.connected
    ? `Connected — firmware ${s.fw}`
    : "Not connected. Is it plugged in?";
  document.getElementById("sensorline").textContent =
    s.sensor === "ok" ? "Sensor: happy (ring should be purple)"
                      : s.sensor === "fail" ? "Sensor: not answering — check the wiring"
                      : "";
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
  const ul = document.getElementById("slots");
  ul.innerHTML = "";
  for (const [slot, label] of Object.entries(s.slots || {})) {
    const li = document.createElement("li");
    li.textContent = `Slot ${slot}: ${label || "(unnamed)"} `;
    const del = document.createElement("button");
    del.textContent = "Remove";
    del.onclick = async () => {
      try {
        const response = await fetch("/api/delete", {method: "POST",
          headers: {"Content-Type": "application/json", "X-DT-Token": token},
          body: JSON.stringify({slot: Number(slot)})});
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
