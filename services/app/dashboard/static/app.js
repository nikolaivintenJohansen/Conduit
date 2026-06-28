const API = "/wallet/v1";
const TOKEN_KEY = "uaw_token";

function microToUsd(micro) {
  return (micro / 1_000_000).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

function usdToMicro(usd) {
  return Math.round(Number(usd) * 1_000_000);
}

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

function show(el, visible) {
  el.classList.toggle("hidden", !visible);
}

function showMessage(el, message) {
  if (!message) {
    show(el, false);
    el.textContent = "";
    return;
  }
  el.textContent = message;
  show(el, true);
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API}${path}`, { ...options, headers });
  let body = null;
  const text = await response.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!response.ok) {
    const message =
      body?.detail?.error?.message ||
      body?.detail ||
      `Request failed (${response.status})`;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return body;
}

const authView = document.getElementById("auth-view");
const dashboardView = document.getElementById("dashboard-view");
const authError = document.getElementById("auth-error");
const dashboardError = document.getElementById("dashboard-error");
const dashboardSuccess = document.getElementById("dashboard-success");
const lowBalanceAlert = document.getElementById("low-balance-alert");

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    const isLogin = tab.dataset.tab === "login";
    show(document.getElementById("login-form"), isLogin);
    show(document.getElementById("register-form"), !isLogin);
    showMessage(authError, "");
  });
});

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  showMessage(authError, "");
  try {
    const data = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email: document.getElementById("login-email").value,
        password: document.getElementById("login-password").value,
      }),
    });
    setToken(data.access_token);
    await loadDashboard();
  } catch (err) {
    showMessage(authError, err.message);
  }
});

document.getElementById("register-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  showMessage(authError, "");
  try {
    const displayName = document.getElementById("register-name").value.trim();
    const data = await api("/auth/register", {
      method: "POST",
      body: JSON.stringify({
        email: document.getElementById("register-email").value,
        password: document.getElementById("register-password").value,
        ...(displayName ? { display_name: displayName } : {}),
      }),
    });
    setToken(data.access_token);
    await loadDashboard();
  } catch (err) {
    showMessage(authError, err.message);
  }
});

document.getElementById("logout-btn").addEventListener("click", async () => {
  try {
    await api("/auth/logout", { method: "POST" });
  } catch {
    /* session may already be invalid */
  }
  setToken(null);
  showAuth();
});

document.getElementById("topup-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  showMessage(dashboardError, "");
  showMessage(dashboardSuccess, "");
  try {
    const amount = document.getElementById("topup-amount").value;
    const data = await api("/topups/checkout", {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({ amount_microdollars: usdToMicro(amount) }),
    });
    window.location.href = data.checkout_url;
  } catch (err) {
    showMessage(dashboardError, err.message);
  }
});

document.getElementById("settings-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  showMessage(dashboardError, "");
  showMessage(dashboardSuccess, "");
  try {
    const spendRaw = document.getElementById("spend-limit").value.trim();
    const threshold = document.getElementById("low-balance-threshold").value;
    const payload = {
      low_balance_threshold_microdollars: usdToMicro(threshold),
      spend_limit_microdollars: spendRaw === "" ? null : usdToMicro(spendRaw),
    };
    await api("/wallet/settings", { method: "PATCH", body: JSON.stringify(payload) });
    showMessage(dashboardSuccess, "Spend settings saved.");
    await refreshWallet();
  } catch (err) {
    showMessage(dashboardError, err.message);
  }
});

document.getElementById("create-key-btn").addEventListener("click", async () => {
  showMessage(dashboardError, "");
  const name = prompt("Key name (optional):", "Default");
  if (name === null) return;
  try {
    const data = await api("/keys", {
      method: "POST",
      body: JSON.stringify({ name: name || undefined }),
    });
    showKeyReveal(data.key);
    await refreshKeys();
  } catch (err) {
    showMessage(dashboardError, err.message);
  }
});

document.getElementById("copy-key-btn").addEventListener("click", async () => {
  const text = document.getElementById("key-reveal-text").textContent;
  await navigator.clipboard.writeText(text);
  showMessage(dashboardSuccess, "Key copied to clipboard.");
});

function showKeyReveal(key) {
  document.getElementById("key-reveal-text").textContent = key;
  show(document.getElementById("key-reveal"), true);
}

function showAuth() {
  show(authView, true);
  show(dashboardView, false);
}

function showDashboard() {
  show(authView, false);
  show(dashboardView, true);
}

async function refreshWallet() {
  const wallet = await api("/wallet");
  document.getElementById("balance-display").textContent = microToUsd(wallet.balance_microdollars);
  document.getElementById("available-display").textContent = microToUsd(wallet.available_microdollars);
  document.getElementById("held-display").textContent = microToUsd(wallet.held_microdollars);
  document.getElementById("monthly-spend-display").textContent = microToUsd(
    wallet.monthly_spend_microdollars || 0
  );

  const limitEl = document.getElementById("spend-limit-display");
  if (wallet.spend_limit_microdollars != null) {
    limitEl.textContent = ` / ${microToUsd(wallet.spend_limit_microdollars)} cap`;
  } else {
    limitEl.textContent = "";
  }

  document.getElementById("spend-limit").value =
    wallet.spend_limit_microdollars != null
      ? (wallet.spend_limit_microdollars / 1_000_000).toFixed(2)
      : "";
  document.getElementById("low-balance-threshold").value = (
    wallet.low_balance_threshold_microdollars / 1_000_000
  ).toFixed(2);

  if (wallet.available_microdollars <= wallet.low_balance_threshold_microdollars) {
    showMessage(
      lowBalanceAlert,
      `Low balance warning: available ${microToUsd(wallet.available_microdollars)} is below your ${microToUsd(wallet.low_balance_threshold_microdollars)} threshold.`
    );
  } else {
    showMessage(lowBalanceAlert, "");
  }
}

async function refreshUsage() {
  const usage = await api("/usage?limit=50");
  const events = usage.data || [];

  const byModel = {};
  for (const event of events) {
    if (!byModel[event.model]) {
      byModel[event.model] = { count: 0, tokens: 0, spend: 0 };
    }
    byModel[event.model].count += 1;
    byModel[event.model].tokens += event.input_tokens + event.output_tokens;
    byModel[event.model].spend += event.charged_microdollars;
  }

  const modelBody = document.getElementById("usage-by-model-body");
  const modelRows = Object.entries(byModel).sort((a, b) => b[1].spend - a[1].spend);
  if (modelRows.length === 0) {
    modelBody.innerHTML = '<tr><td colspan="4" class="balance-meta">No usage yet</td></tr>';
  } else {
    modelBody.innerHTML = modelRows
      .map(
        ([model, stats]) => `
      <tr>
        <td class="mono">${escapeHtml(model)}</td>
        <td>${stats.count}</td>
        <td>${stats.tokens.toLocaleString()}</td>
        <td>${microToUsd(stats.spend)}</td>
      </tr>`
      )
      .join("");
  }

  const usageBody = document.getElementById("usage-body");
  if (events.length === 0) {
    usageBody.innerHTML = '<tr><td colspan="4" class="balance-meta">No usage yet</td></tr>';
  } else {
    usageBody.innerHTML = events
      .map(
        (event) => `
      <tr>
        <td>${new Date(event.created_at).toLocaleString()}</td>
        <td class="mono">${escapeHtml(event.model)}</td>
        <td>${(event.input_tokens + event.output_tokens).toLocaleString()}</td>
        <td>${microToUsd(event.charged_microdollars)}</td>
      </tr>`
      )
      .join("");
  }
}

async function refreshKeys() {
  const keys = await api("/keys");
  const active = (keys.data || []).filter((k) => !k.revoked_at);
  const body = document.getElementById("keys-body");

  if (active.length === 0) {
    body.innerHTML = '<tr><td colspan="4" class="balance-meta">No keys yet</td></tr>';
    return;
  }

  body.innerHTML = active
    .map(
      (key) => `
    <tr>
      <td>${escapeHtml(key.name || "—")}</td>
      <td class="mono">${escapeHtml(key.key_prefix)}…</td>
      <td>${key.rpm_limit} RPM / ${key.tpm_limit.toLocaleString()} TPM</td>
      <td>
        <div class="btn-group">
          <button type="button" class="btn btn-secondary btn-sm" data-rotate="${key.id}">Rotate</button>
          <button type="button" class="btn btn-danger btn-sm" data-revoke="${key.id}">Revoke</button>
        </div>
      </td>
    </tr>`
    )
    .join("");

  body.querySelectorAll("[data-rotate]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Rotate this key? The old key will stop working immediately.")) return;
      try {
        const data = await api(`/keys/${btn.dataset.rotate}/rotate`, { method: "POST" });
        showKeyReveal(data.key);
        await refreshKeys();
      } catch (err) {
        showMessage(dashboardError, err.message);
      }
    });
  });

  body.querySelectorAll("[data-revoke]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Revoke this key? This cannot be undone.")) return;
      try {
        await api(`/keys/${btn.dataset.revoke}`, { method: "DELETE" });
        await refreshKeys();
      } catch (err) {
        showMessage(dashboardError, err.message);
      }
    });
  });
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

async function loadDashboard() {
  showMessage(dashboardError, "");
  showMessage(dashboardSuccess, "");
  show(document.getElementById("key-reveal"), false);

  try {
    const me = await api("/me");
    document.getElementById("user-email").textContent = me.email;
    showDashboard();
    await Promise.all([refreshWallet(), refreshUsage(), refreshKeys()]);
  } catch {
    setToken(null);
    showAuth();
  }
}

const params = new URLSearchParams(window.location.search);
if (params.get("topup") === "success") {
  showMessage(dashboardSuccess, "Top-up completed. Your balance will update shortly.");
  window.history.replaceState({}, "", "/dashboard");
}

if (getToken()) loadDashboard();
else showAuth();
