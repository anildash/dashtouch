const token = new URLSearchParams(location.search).get("token");

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
  if (s.enroll_stage) {
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
    if (!response.ok) {
      document.getElementById("progress").textContent = "That didn't go through — this page has probably gone stale. Close this tab and open the fresh link from the helper (or run .venv/bin/dashtouch enroll).";
    }
  } catch {
    document.getElementById("progress").textContent = "Can't reach the helper — is it still running?";
  }
};

setInterval(refresh, 800);
refresh();
