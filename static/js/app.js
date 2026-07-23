const TIMER_SETTINGS = {
  tickIntervalMs: 1000,
  adjustSeconds: 300,
};

let activeSessionId = null;
let timerLoop = null;
let eventSource = null;

function toClock(totalSeconds) {
  const safeSeconds = Math.max(0, Number(totalSeconds) || 0);
  const minutes = Math.floor(safeSeconds / 60);
  const seconds = safeSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function money(value) {
  return `N${Number(value || 0).toLocaleString()}`;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = payload.message || `Request failed with status ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

function setStatus(text) {
  const statusEl = document.getElementById("sessionStatus");
  if (statusEl) {
    statusEl.textContent = text;
  }
}

function setTimer(seconds) {
  const timerEl = document.getElementById("timerValue");
  if (timerEl) {
    timerEl.textContent = toClock(seconds);
  }
}

function setCheckoutResult(ok, text) {
  const el = document.getElementById("checkoutResult");
  if (!el) {
    return;
  }
  el.classList.remove("d-none", "alert-success", "alert-danger", "alert-warning");
  el.classList.add(ok ? "alert-success" : "alert-warning");
  el.textContent = text;
}

function setSessionStartResult(ok, text) {
  const el = document.getElementById("sessionStartResult");
  if (!el) {
    return;
  }
  el.classList.remove("d-none", "alert-success", "alert-danger", "alert-warning");
  el.classList.add(ok ? "alert-success" : "alert-warning");
  el.textContent = text;
}

function setDeviceState({ online = null, switch1 = null, switch2 = null } = {}) {
  const onlineEl = document.getElementById("deviceOnlineState");
  const switch1El = document.getElementById("switch1State");
  const switch2El = document.getElementById("switch2State");

  if (onlineEl && online !== null) {
    onlineEl.textContent = online ? "Online" : "Offline";
  }
  if (switch1El && switch1 !== null) {
    switch1El.textContent = switch1 ? "ON" : "OFF";
  }
  if (switch2El && switch2 !== null) {
    switch2El.textContent = switch2 ? "ON" : "OFF";
  }
}

function getStatusClass(statusText) {
  const value = String(statusText || "").toLowerCase();
  if (value.includes("success") || value.includes("done") || value.includes("closed")) {
    return "status-ok";
  }
  if (value.includes("off") || value.includes("override") || value.includes("fail")) {
    return "status-off";
  }
  return "status-warn";
}

async function loadSwitchWorkflow() {
  const list = document.getElementById("workflowList");
  if (!list) {
    return;
  }

  try {
    const data = await fetchJson("/api/user/workflow/smart-switch");
    list.innerHTML = "";
    data.workflow.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      list.appendChild(li);
    });
  } catch (error) {
    list.innerHTML = `<li>${error.message}</li>`;
  }
}

async function startSessionFromPayment(event) {
  event.preventDefault();

  const payload = {
    game_id: Number(document.getElementById("gameSelect")?.value || 1),
    branch: document.getElementById("branchSelect")?.value || "branch1",
    duration_minutes: Number(document.getElementById("durationSelect")?.value || 60),
    payment_status: document.getElementById("paymentStatus")?.value || "successful",
    plug_id: document.getElementById("plugId")?.value || "plug-001",
  };

  try {
    const data = await fetchJson("/api/user/payment/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!data.session) {
      setCheckoutResult(false, `Payment declined for ${money(data.payment.amount)}. Retry payment to start session.`);
      return;
    }

    localStorage.setItem("activeSessionId", String(data.session.id));
    setCheckoutResult(true, `Payment successful (${money(data.payment.amount)}). Redirecting to session timer...`);
    window.setTimeout(() => {
      window.location.href = "/user/session";
    }, 700);
  } catch (error) {
    setCheckoutResult(false, error.message);
  }
}

async function tickSession() {
  if (!activeSessionId) {
    return;
  }

  try {
    const data = await fetchJson(`/api/user/session/${activeSessionId}/tick`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });

    setTimer(data.remaining_seconds);
    setStatus(`Session ${data.status}.`);

    if (data.status !== "active") {
      clearInterval(timerLoop);
      timerLoop = null;
      localStorage.removeItem("activeSessionId");
      setStatus("Session ended. Smart plug turned off.");
    }
  } catch (error) {
    clearInterval(timerLoop);
    timerLoop = null;
    setStatus(error.message);
  }
}

function applyStatusRows(statusRows = []) {
  const byCode = Object.fromEntries(statusRows.map((row) => [String(row.code || "").toLowerCase(), row.value]));
  const switch1 = byCode.switch_1 ?? byCode.switch1 ?? byCode.switch;
  const switch2 = byCode.switch_2 ?? byCode.switch2;
  setDeviceState({
    switch1: typeof switch1 === "boolean" ? switch1 : null,
    switch2: typeof switch2 === "boolean" ? switch2 : null,
  });
}

async function refreshDeviceStatus() {
  const onlineEl = document.getElementById("deviceOnlineState");
  if (!onlineEl) {
    return;
  }

  try {
    const data = await fetchJson("/api/user/device/status");
    setDeviceState({ online: !!data.device?.online });
    applyStatusRows(data.status || []);
  } catch (error) {
    setStatus(error.message);
  }
}

function openSessionEventStream() {
  if (eventSource) {
    eventSource.close();
  }

  eventSource = new EventSource("/api/user/session/events");
  eventSource.onmessage = (event) => {
    try {
      const packet = JSON.parse(event.data || "{}");
      const payload = packet.payload || {};

      if (payload.remaining_seconds !== undefined) {
        setTimer(payload.remaining_seconds);
      }

      if (payload.status) {
        setStatus(`Session ${payload.status}.`);
      }

      if (packet.type === "device_status" && payload.device) {
        setDeviceState({ online: !!payload.device.online });
        applyStatusRows(payload.status || []);
      }

      if (packet.type === "tuya_event") {
        refreshDeviceStatus();
      }
    } catch {
      // Ignore malformed SSE payloads to keep UI responsive.
    }
  };

  eventSource.onerror = () => {
    setStatus("Live updates disconnected. Reconnecting...");
  };
}

async function startSessionFromSessionPage(event) {
  event.preventDefault();

  const payload = {
    game_id: Number(document.getElementById("sessionGame")?.value || 0),
    branch: document.getElementById("sessionBranch")?.value || "branch1",
    station: document.getElementById("sessionStation")?.value || "station1",
    duration_minutes: Number(document.getElementById("sessionDuration")?.value || 60),
    payment_status: "successful",
  };

  try {
    const data = await fetchJson("/api/user/session/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!data.session) {
      setSessionStartResult(false, "Payment must be successful before session can start.");
      return;
    }

    activeSessionId = data.session.id;
    localStorage.setItem("activeSessionId", String(activeSessionId));
    setSessionStartResult(true, `Session started for ${payload.station}.`);
    setTimer(data.session.remaining_seconds);
    setStatus("Session active.");

    if (timerLoop) {
      clearInterval(timerLoop);
    }
    timerLoop = setInterval(tickSession, TIMER_SETTINGS.tickIntervalMs);
    await refreshDeviceStatus();
  } catch (error) {
    setSessionStartResult(false, error.message);
  }
}

async function adjustSession(deltaSeconds) {
  if (!activeSessionId) {
    return;
  }

  try {
    const data = await fetchJson(`/api/user/session/${activeSessionId}/adjust`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ delta_seconds: deltaSeconds }),
    });

    setTimer(data.remaining_seconds);
    setStatus(`Session ${data.status}.`);
  } catch (error) {
    setStatus(error.message);
  }
}

async function stopSession() {
  if (!activeSessionId) {
    return;
  }

  try {
    await fetchJson(`/api/user/session/${activeSessionId}/stop`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    setStatus(error.message);
  }

  setTimer(0);
  setStatus("Session manually stopped.");
  localStorage.removeItem("activeSessionId");
  activeSessionId = null;

  if (timerLoop) {
    clearInterval(timerLoop);
    timerLoop = null;
  }
}

async function setupSessionPage() {
  const timerEl = document.getElementById("timerValue");
  if (!timerEl) {
    return;
  }

  activeSessionId = Number(localStorage.getItem("activeSessionId") || 0);

  if (!activeSessionId) {
    try {
      const current = await fetchJson("/api/user/session/current");
      if (current.session) {
        activeSessionId = current.session.id;
        localStorage.setItem("activeSessionId", String(current.session.id));
      }
    } catch (error) {
      setStatus(error.message);
      return;
    }
  }

  if (!activeSessionId) {
    setStatus("No active session. Start one with the form above.");
  }

  if (activeSessionId) {
    try {
      const data = await fetchJson(`/api/user/session/${activeSessionId}`);
      setTimer(data.remaining_seconds);
      setStatus(`Session ${data.status}.`);

      if (data.status === "active") {
        timerLoop = setInterval(tickSession, TIMER_SETTINGS.tickIntervalMs);
      }
    } catch (error) {
      setStatus(error.message);
    }
  }

  document.getElementById("sessionStartForm")?.addEventListener("submit", startSessionFromSessionPage);
  document.getElementById("add5")?.addEventListener("click", () => adjustSession(TIMER_SETTINGS.adjustSeconds));
  document.getElementById("minus5")?.addEventListener("click", () => adjustSession(-TIMER_SETTINGS.adjustSeconds));
  document.getElementById("stopSession")?.addEventListener("click", stopSession);

  openSessionEventStream();
  await refreshDeviceStatus();
}

function renderBranchActivities(items) {
  const tbody = document.getElementById("branchActivityBody");
  if (!tbody) {
    return;
  }
  tbody.innerHTML = "";
  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="5">No branch activity yet.</td></tr>';
    return;
  }
  items.forEach((item) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${item.user}</td>
      <td>${item.station}</td>
      <td>${item.action}</td>
      <td>${money(item.amount)}</td>
      <td><span class="status-pill ${getStatusClass(item.status)}">${item.status}</span></td>
    `;
    tbody.appendChild(tr);
  });
}

function renderSuperActivities(items) {
  const tbody = document.getElementById("superActivityBody");
  if (!tbody) {
    return;
  }
  tbody.innerHTML = "";
  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="5">No cross-branch activity yet.</td></tr>';
    return;
  }
  items.forEach((item) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${item.branch}</td>
      <td>${item.user}</td>
      <td>${item.action}</td>
      <td>${item.target}</td>
      <td><span class="status-pill ${getStatusClass(item.status)}">${item.status}</span></td>
    `;
    tbody.appendChild(tr);
  });
}

async function setupDashboardPage() {
  const root = document.getElementById("adminDashboardRoot");
  if (!root) {
    return;
  }

  const dashboardType = root.dataset.dashboard;
  if (dashboardType === "branch") {
    const branch = root.dataset.branch || "branch1";
    const data = await fetchJson(`/api/admin/branch/${branch}/summary`);
    document.getElementById("metricActive").textContent = String(data.metrics.active_sessions);
    document.getElementById("metricDeclined").textContent = String(data.metrics.declined_payments);
    document.getElementById("metricSales").textContent = money(data.metrics.today_sales);
    renderBranchActivities(data.activities || []);
    return;
  }

  if (dashboardType === "super") {
    const data = await fetchJson("/api/admin/super/summary");
    document.getElementById("metricTotalSales").textContent = money(data.metrics.total_sales);
    document.getElementById("metricActivePlugs").textContent = String(data.metrics.active_plugs);
    document.getElementById("metricOnlineAdmins").textContent = String(data.metrics.online_admins);
    document.getElementById("metricOpenIssues").textContent = String(data.metrics.open_issues);
    renderSuperActivities(data.activities || []);
  }
}

const GAMING_QUOTES = [
  "Gaming isn’t just about winning—it’s about the journey, the challenge, and the memories you create along the way.",
  "A true gamer doesn’t fear defeat; they simply see another chance to level up.",
  "Every game is a new world waiting to be explored.",
  "Great gamers don’t quit when they lose—they learn, adapt, and play again.",
  "Gaming turns ordinary moments into unforgettable adventures.",
  "The best victories are earned after the toughest battles.",
  "A controller in your hands is a passport to limitless adventures.",
  "Games remind us that persistence is often more powerful than talent.",
  "Gaming is where imagination meets determination.",
  "The joy of gaming isn’t in the destination—it’s in every mission, every challenge, and every triumph.",
];

let gamingQuoteInterval = null;
let previousQuoteIndex = -1;

function getRandomQuoteIndex(excludeIndex = -1) {
  let nextIndex = Math.floor(Math.random() * GAMING_QUOTES.length);
  while (nextIndex === excludeIndex && GAMING_QUOTES.length > 1) {
    nextIndex = Math.floor(Math.random() * GAMING_QUOTES.length);
  }
  return nextIndex;
}

function updateGamingQuote(nextIndex) {
  const quoteText = document.getElementById("gamingQuoteText");
  const quoteRotator = document.getElementById("gamingQuoteRotator");
  if (!quoteText || !quoteRotator) {
    return;
  }

  quoteRotator.style.opacity = "0";
  window.setTimeout(() => {
    quoteText.textContent = GAMING_QUOTES[nextIndex];
    quoteRotator.style.opacity = "1";
  }, 650);
}

function startGamingQuoteRotation() {
  const quoteText = document.getElementById("gamingQuoteText");
  const quoteRotator = document.getElementById("gamingQuoteRotator");
  if (!quoteText || !quoteRotator) {
    return;
  }

  const firstIndex = getRandomQuoteIndex();
  previousQuoteIndex = firstIndex;
  quoteText.textContent = GAMING_QUOTES[firstIndex];
  quoteRotator.style.opacity = "1";
  quoteRotator.style.transition = "opacity 650ms ease-in-out";

  if (gamingQuoteInterval) {
    window.clearInterval(gamingQuoteInterval);
  }

  gamingQuoteInterval = window.setInterval(() => {
    const nextIndex = getRandomQuoteIndex(previousQuoteIndex);
    previousQuoteIndex = nextIndex;
    updateGamingQuote(nextIndex);
  }, 15000);
}

function setupPaymentPage() {
  document.getElementById("paymentForm")?.addEventListener("submit", startSessionFromPayment);
}

document.addEventListener("DOMContentLoaded", () => {
  setupPaymentPage();
  setupSessionPage();
  startGamingQuoteRotation();
  loadSwitchWorkflow();
  setupDashboardPage().catch((error) => {
    const root = document.getElementById("adminDashboardRoot");
    if (root) {
      const alert = document.createElement("div");
      alert.className = "alert alert-warning mt-3";
      alert.textContent = `Dashboard load failed: ${error.message}`;
      root.insertAdjacentElement("afterend", alert);
    }
  });
});
