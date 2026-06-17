"use strict";

const $ = id => document.getElementById(id);

const dot       = $("status-dot");
const statusTxt = $("status-text");
const tokenIn   = $("token-input");
const urlIn     = $("url-input");
const chipChk   = $("chip-toggle");
const msgEl     = $("msg");

let _pollTimer = null;

function showMsg(text, isError = false) {
  msgEl.textContent = text;
  msgEl.className = isError ? "error" : "";
  if (text) setTimeout(() => { msgEl.textContent = ""; }, 3000);
}

function setStatus(state, text) {
  // state: true = connected, "connecting" = animating, false = error/disconnected
  dot.className = "dot " + (
    state === true         ? "connected"  :
    state === "connecting" ? "connecting" :
                             "error"
  );
  statusTxt.textContent = text;
}

// ── Status polling ────────────────────────────────────────────────────────────
// Polls background.js every 800 ms until connected or maxAttempts reached.

function startPolling(maxAttempts = 10) {
  stopPolling();
  let attempts = 0;
  _pollTimer = setInterval(() => {
    attempts++;
    chrome.runtime.sendMessage({ type: "RF_STATUS" }, resp => {
      if (chrome.runtime.lastError || !resp) {
        stopPolling();
        setStatus(false, "Extension error — try reloading the extension");
        return;
      }
      if (resp.connected) {
        stopPolling();
        setStatus(true, `Connected · ${resp.wsUrl}`);
        showMsg("Connected to RuneFetch ✓");
        return;
      }
      if (attempts >= maxAttempts) {
        stopPolling();
        if (!resp.token) {
          setStatus(false, "No token — paste one below");
        } else {
          setStatus(false, "Could not connect — is RuneFetch running?");
          showMsg("Check that RuneFetch is open and the token matches", true);
        }
      }
      // else keep polling — still connecting
    });
  }, 800);
}

function stopPolling() {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
}

// ── On open ───────────────────────────────────────────────────────────────────

(async () => {
  const data = await chrome.storage.local.get(["rf_token", "rf_port", "rf_chip_enabled"]);

  tokenIn.value = data.rf_token ? "••••••••" : "";
  chipChk.checked = data.rf_chip_enabled !== false;

  if (!data.rf_token) {
    setStatus(false, "No token — paste one below");
    return;
  }

  // Check status immediately — no spinner flash if already connected
  chrome.runtime.sendMessage({ type: "RF_STATUS" }, resp => {
    if (chrome.runtime.lastError || !resp) {
      setStatus(false, "Extension error — try reloading the extension");
      return;
    }
    if (resp.connected) {
      setStatus(true, `Connected · ${resp.wsUrl}`);
    } else {
      // Not yet connected — show spinner and start polling
      setStatus("connecting", "Connecting…");
      startPolling(8);
    }
  });
})();

// ── Token save ────────────────────────────────────────────────────────────────

$("btn-save").addEventListener("click", async () => {
  const raw = tokenIn.value.trim();
  if (!raw || raw === "••••••••") {
    showMsg("Enter a token to save", true);
    return;
  }
  const portData = await chrome.storage.local.get("rf_port");
  const port = portData.rf_port || 8765;

  setStatus("connecting", "Saving token — connecting…");

  chrome.runtime.sendMessage({ type: "RF_SET_TOKEN", token: raw, port }, resp => {
    if (!resp || !resp.ok) {
      setStatus(false, "Failed to save token");
      showMsg("Failed to save token", true);
      return;
    }
    tokenIn.value = "••••••••";
    showMsg("Token saved — connecting…");
    // Poll until the WS connection is confirmed (up to 12 × 800 ms = ~10 s)
    startPolling(12);
  });
});

// ── Clear token ───────────────────────────────────────────────────────────────

$("btn-clear").addEventListener("click", async () => {
  stopPolling();
  await chrome.storage.local.remove(["rf_token"]);
  chrome.runtime.sendMessage({ type: "RF_SET_TOKEN", token: "", port: 8765 });
  tokenIn.value = "";
  setStatus(false, "Token cleared");
  showMsg("Token removed");
});

// ── Manual URL send ───────────────────────────────────────────────────────────

$("btn-send").addEventListener("click", () => {
  const url = urlIn.value.trim();
  if (!url) { showMsg("Enter a URL first", true); return; }
  try { new URL(url); } catch { showMsg("Invalid URL", true); return; }
  chrome.runtime.sendMessage({ type: "RF_SEND_URL", url, title: "" }, resp => {
    if (resp && resp.ok) {
      showMsg("Sent to RuneFetch ✓");
      urlIn.value = "";
    } else {
      showMsg("Not connected — is RuneFetch running?", true);
    }
  });
});

// Allow Enter key in URL field
urlIn.addEventListener("keydown", e => { if (e.key === "Enter") $("btn-send").click(); });

// ── Chip toggle ───────────────────────────────────────────────────────────────

chipChk.addEventListener("change", async () => {
  await chrome.storage.local.set({ rf_chip_enabled: chipChk.checked });
  showMsg(chipChk.checked ? "Capture chip enabled" : "Capture chip disabled");
});

// ── Scan current tab ──────────────────────────────────────────────────────────

$("btn-scan").addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return;
  chrome.tabs.sendMessage(tab.id, { type: "RF_SCAN_PAGE" }, () => {
    if (chrome.runtime.lastError) showMsg("Could not reach page", true);
  });
  window.close();
});

// Stop polling when popup closes (avoids orphaned intervals)
window.addEventListener("unload", stopPolling);
