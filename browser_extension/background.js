/**
 * RuneFetch Extension — Background Service Worker (MV3)
 *
 * Responsibilities:
 *  1. Maintain one persistent WebSocket connection to the RuneFetch bridge.
 *  2. Intercept browser download-intent events and offer them to RuneFetch.
 *  3. Accept messages from content.js and the popup to relay to the bridge.
 *  4. Update the toolbar badge with connection status.
 */

const DEFAULT_PORT = 8765;
const RECONNECT_DELAY_MS = 5000;

let ws = null;
let reconnectTimer = null;
let token = "";
let port = DEFAULT_PORT;
let isConnected = false;

// ── Storage ───────────────────────────────────────────────────────────────────

async function loadConfig() {
  const data = await chrome.storage.local.get(["rf_token", "rf_port"]);
  token = data.rf_token || "";
  port  = data.rf_port  || DEFAULT_PORT;
}

// ── WebSocket connection ───────────────────────────────────────────────────────

function wsUrl() {
  return `ws://127.0.0.1:${port}`;
}

function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  if (!token) {
    setBadge("?", "#ff9f0a");
    return;
  }

  try {
    ws = new WebSocket(wsUrl());
  } catch (e) {
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    isConnected = true;
    setBadge("", "#2dd4a0");
    clearTimeout(reconnectTimer);
    // Ping to verify token and get app info
    send({ action: "ping" });
  };

  ws.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data);
      if (!msg.ok && msg.error === "unauthorized") {
        setBadge("!", "#ff6b6b");
        // Mark disconnected immediately so no further messages are sent
        // with the wrong token. onclose will fire next and schedule reconnect.
        isConnected = false;
        ws.close();
      }
    } catch (_) {}
  };

  ws.onerror = () => {};

  ws.onclose = () => {
    isConnected = false;
    setBadge("✕", "#ff6b6b");
    scheduleReconnect();
  };
}

function scheduleReconnect() {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
}

function send(payload) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return false;
  if (!token) return false;
  ws.send(JSON.stringify({ token, ...payload }));
  return true;
}

// ── Badge helpers ─────────────────────────────────────────────────────────────

function setBadge(text, color) {
  chrome.action.setBadgeText({ text });
  chrome.action.setBadgeBackgroundColor({ color });
}

// ── Download interception ─────────────────────────────────────────────────────

chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
  suggest();   // always let browser proceed normally

  if (!isConnected || !token) return;

  const url = item.finalUrl || item.url;
  const title = item.filename || "";

  // Offer to RuneFetch — non-blocking; bridge queues it
  send({ url, suggestedTitle: title });

  // Show a notification so the user knows RuneFetch intercepted it
  chrome.notifications.create({
    type: "basic",
    iconUrl: "icons/icon48.png",
    title: "RuneFetch",
    message: `Added to RuneFetch queue:\n${title || url.slice(0, 60)}`,
    priority: 0,
  });
});

// ── Message routing (from content.js / popup) ─────────────────────────────────

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "RF_SEND_URL") {
    const ok = send({ url: msg.url, suggestedTitle: msg.title || "" });
    sendResponse({ ok });
    return true;
  }

  if (msg.type === "RF_STATUS") {
    sendResponse({
      connected: isConnected,
      token: token ? "set" : "",
      wsUrl: wsUrl(),
    });
    return true;
  }

  if (msg.type === "RF_SET_TOKEN") {
    token = msg.token;
    port  = msg.port || DEFAULT_PORT;
    chrome.storage.local.set({ rf_token: token, rf_port: port });
    ws && ws.close();   // reconnect with new credentials
    connect();
    sendResponse({ ok: true });
    return true;
  }
});

// ── Startup ───────────────────────────────────────────────────────────────────

(async () => {
  await loadConfig();
  connect();
})();

// Reconnect when service worker wakes from suspension
chrome.runtime.onStartup.addListener(async () => {
  await loadConfig();
  connect();
});
