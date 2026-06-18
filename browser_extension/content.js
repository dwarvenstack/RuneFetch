/**
 * RuneFetch — Content Script
 *
 * Two-mode detection:
 *
 *  MODE A — Content page (single video/post):
 *    Floating chip in the bottom-right corner.
 *    URL is read from location.href after a settle delay — never from the
 *    <video> element (that element belongs to the PREVIOUS video during
 *    SPA navigation and would give the wrong URL).
 *
 *  MODE B — Feed / home page (multiple thumbnails):
 *    A small ↓ button is injected onto each thumbnail and revealed on hover.
 *    Clicking sends that video's URL to RuneFetch immediately.
 *    This matches IDM's per-thumbnail behaviour.
 *
 *  URL changes are detected via a 600 ms interval poll — more reliable than
 *  overriding history.pushState, which YouTube itself also overrides.
 */

"use strict";

// ── Platform tables ───────────────────────────────────────────────────────────

const RECOGNISED_HOSTS = new Set([
  "youtube.com", "www.youtube.com", "youtu.be", "music.youtube.com",
  "open.spotify.com",
  "twitter.com", "x.com",
  "instagram.com", "www.instagram.com",
  "facebook.com", "www.facebook.com", "fb.watch",
  "tiktok.com", "www.tiktok.com",
  "reddit.com", "www.reddit.com", "v.redd.it",
  "vimeo.com", "www.vimeo.com",
  "twitch.tv", "www.twitch.tv",
  "soundcloud.com", "www.soundcloud.com",
  "dailymotion.com", "bilibili.com", "rumble.com", "odysee.com",
  "bandcamp.com", "mixcloud.com", "archive.org",
]);

const DRM_HOSTS = new Set([
  "netflix.com", "primevideo.com", "amazon.com", "hotstar.com",
  "disneyplus.com", "hulu.com", "max.com", "peacocktv.com",
  "paramountplus.com", "crunchyroll.com",
]);

const DIRECT_EXTS = new Set([
  "mp4","mkv","avi","mov","webm","m4v","mp3","flac","wav","aac",
  "ogg","m4a","opus","zip","rar","7z","tar","gz","pdf","apk","dmg",
]);

// Patterns that identify a single-content page (show floating chip).
// null = any non-root path counts.
const CONTENT_PATHS = {
  "youtube.com":    ["/watch", "/shorts/", "/live/", "/embed/"],
  "youtu.be":       null,
  "twitter.com":    ["/status/"],
  "x.com":          ["/status/"],
  "instagram.com":  ["/p/", "/reel/", "/tv/"],
  "facebook.com":   ["/videos/", "/watch/", "/reel/"],
  "tiktok.com":     ["/video/"],
  "reddit.com":     ["/comments/"],
  "vimeo.com":      null,
  "twitch.tv":      ["/clip", "/videos/"],
  "dailymotion.com":["/video/"],
  "bilibili.com":   ["/video/", "/bangumi/"],
  "rumble.com":     ["/v"],
  "odysee.com":     ["/@"],
};

// CSS selectors to find thumbnail anchor tags on feed pages, per site.
const THUMB_SELECTORS = {
  "youtube.com":    "ytd-thumbnail a#thumbnail[href], a.ytd-thumbnail[href]",
  "twitter.com":    "article a[href*='/status/']",
  "x.com":          "article a[href*='/status/']",
  "instagram.com":  "article a[href*='/p/'], article a[href*='/reel/']",
  "tiktok.com":     "a[href*='/video/']",
  "reddit.com":     "a[href*='/comments/']",
  "vimeo.com":      "a[href^='/'][href*='/']:not([href*='//'])",
  "dailymotion.com":"a[href*='/video/']",
  "rumble.com":     "a[href*='/v']",
};

const CHIP_ID = "rf-capture-chip";

let chipVisible      = false;
let lastDismissedUrl = "";
let suppressedSites  = new Set();
let chipEnabled      = true;

// ── Helpers ───────────────────────────────────────────────────────────────────

const _host = () => location.hostname.replace(/^www\./, "");

function _isContentPage(href) {
  try {
    const host = location.hostname.replace(/^www\./, "");
    const path = new URL(href).pathname;
    for (const [h, patterns] of Object.entries(CONTENT_PATHS)) {
      if (!host.endsWith(h)) continue;
      if (patterns === null) return path.length > 1;
      return patterns.some(p => path.includes(p));
    }
    // Other recognised hosts: any non-root path
    if (RECOGNISED_HOSTS.has(host) || RECOGNISED_HOSTS.has("www." + host)) {
      return path.length > 1;
    }
  } catch (_) {}
  return false;
}

function esc(s) {
  return String(s)
    .replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  const data = await chrome.storage.local.get(["rf_suppressed", "rf_chip_enabled"]);
  suppressedSites = new Set(data.rf_suppressed || []);
  chipEnabled     = data.rf_chip_enabled !== false;

  if (!chipEnabled) return;

  const host = _host();
  if (DRM_HOSTS.has(host) || suppressedSites.has(host)) return;

  // Start polling for URL changes
  _startUrlPoll();

  // Run immediately for the current page
  _handleCurrentPage();

  // Direct-file link scanner (any page)
  _startDirectLinkScanner();
}

// ── URL-change poll ───────────────────────────────────────────────────────────

let _pollHref    = location.href;
let _settleTimer = null;

function _startUrlPoll() {
  setInterval(() => {
    const cur = location.href;
    if (cur === _pollHref) return;
    _pollHref = cur;

    // URL just changed — dismiss stale chip immediately
    dismissChip(false);
    lastDismissedUrl = "";

    clearTimeout(_settleTimer);
    // Wait for the page title and DOM to settle before deciding what to show
    _settleTimer = setTimeout(_handleCurrentPage, 1200);
  }, 600);
}

// ── Page-mode router ──────────────────────────────────────────────────────────

function _handleCurrentPage() {
  if (!chipEnabled) return;
  const host = _host();
  if (DRM_HOSTS.has(host) || suppressedSites.has(host)) return;

  if (_isContentPage(location.href)) {
    // Mode A: single content page → floating chip
    _showContentChip();
  } else {
    // Mode B: feed / home → per-thumbnail buttons
    _startThumbnailInjector();
  }
}

// ── Mode A: Floating chip ─────────────────────────────────────────────────────

function _showContentChip() {
  if (chipVisible) return;
  if (location.href === lastDismissedUrl) return;

  // Capture URL and title NOW (after settle delay) — guaranteed current page
  const url   = location.href;
  const title = document.title || url;

  showChip([{ url, title, kind: "content-page" }]);
}

// ── Mode B: Thumbnail overlay buttons ────────────────────────────────────────

let _thumbObserver    = null;
let _thumbInjectedSet = new WeakSet();

function _startThumbnailInjector() {
  const host = _host();
  const sel  = THUMB_SELECTORS[host] || THUMB_SELECTORS["www." + host];
  if (!sel) return;

  const inject = (root) => {
    root.querySelectorAll(sel).forEach(anchor => {
      if (_thumbInjectedSet.has(anchor)) return;
      const href = anchor.href;
      if (!href || href === location.href) return;
      _thumbInjectedSet.add(anchor);

      const btn = document.createElement("button");
      btn.className   = "rf-thumb-btn";
      btn.title       = "Download with RuneFetch";
      btn.textContent = "↓ RF";
      btn.addEventListener("click", e => {
        e.preventDefault();
        e.stopPropagation();
        const label = anchor.getAttribute("aria-label") ||
                      anchor.querySelector("img")?.alt   || href;
        sendToRuneFetch(href, label);
        btn.textContent = "✓ Sent";
        btn.style.background = "#2dd4a0";
        setTimeout(() => { btn.textContent = "↓ RF"; btn.style.background = ""; }, 2000);
      });

      // Anchor needs relative positioning to host the absolute button
      const computed = getComputedStyle(anchor);
      if (computed.position === "static") anchor.style.position = "relative";
      anchor.appendChild(btn);
    });
  };

  // Inject into existing thumbnails
  inject(document);

  // Watch for new thumbnails (infinite scroll)
  if (_thumbObserver) _thumbObserver.disconnect();
  _thumbObserver = new MutationObserver(() => inject(document));
  _thumbObserver.observe(document.body, { childList: true, subtree: true });
}

// ── Direct-file link scanner ──────────────────────────────────────────────────

function _startDirectLinkScanner() {
  const scan = () => {
    if (!chipEnabled || chipVisible) return;
    const host = _host();
    if (suppressedSites.has(host) || DRM_HOSTS.has(host)) return;

    const found = [];
    document.querySelectorAll("a[href]").forEach(a => {
      try {
        const url = new URL(a.href);
        const ext = url.pathname.split(".").pop().toLowerCase();
        if (DIRECT_EXTS.has(ext) && !found.some(f => f.url === a.href)) {
          found.push({
            url:   a.href,
            title: a.textContent.trim() || a.href.split("/").pop(),
            kind:  "direct",
          });
        }
      } catch (_) {}
    });
    if (found.length > 0) showChip(found);
  };

  if (document.body) {
    new MutationObserver(scan).observe(document.body, { childList: true, subtree: true });
    scan();
  } else {
    document.addEventListener("DOMContentLoaded", () => {
      new MutationObserver(scan).observe(document.body, { childList: true, subtree: true });
      scan();
    });
  }
}

// ── Chip rendering ────────────────────────────────────────────────────────────

function showChip(items) {
  if (chipVisible) return;
  if (location.href === lastDismissedUrl) return;

  document.getElementById(CHIP_ID)?.remove();

  const chip = document.createElement("div");
  chip.id    = CHIP_ID;
  chip.setAttribute("role", "dialog");
  chip.setAttribute("aria-label", "RuneFetch download capture");

  const label = items.length === 1
    ? (items[0].title || items[0].url).slice(0, 52)
    : `${items.length} downloadable items`;

  chip.innerHTML = `
    <div class="rf-chip-inner">
      <span class="rf-logo">⛩</span>
      <span class="rf-desc">${esc(label)}</span>
      <button class="rf-btn-dl" title="Download with RuneFetch">↓ Download</button>
      <button class="rf-btn-x" title="Dismiss (Esc)" aria-label="Dismiss">✕</button>
    </div>
    ${items.length > 1 ? `
      <div class="rf-list">
        ${items.slice(0,5).map(i =>
          `<div class="rf-list-item" data-url="${esc(i.url)}">${esc((i.title||i.url).slice(0,44))}</div>`
        ).join("")}
        ${items.length > 5 ? `<div class="rf-list-more">…and ${items.length-5} more</div>` : ""}
      </div>` : ""}
    <div class="rf-suppress">
      <a href="#" class="rf-suppress-link">Don't show on this site</a>
    </div>`;

  document.body.appendChild(chip);
  chipVisible = true;

  chip.querySelector(".rf-btn-dl").addEventListener("click", () => {
    items.forEach(i => sendToRuneFetch(i.url, i.title));
  });
  chip.querySelector(".rf-btn-x").addEventListener("click", () => dismissChip(true));
  chip.querySelectorAll(".rf-list-item").forEach(el => {
    el.addEventListener("click", () => {
      sendToRuneFetch(el.dataset.url, el.textContent.trim());
    });
  });
  chip.querySelector(".rf-suppress-link").addEventListener("click", e => {
    e.preventDefault();
    suppressSite();
    dismissChip(true);
  });
}

function dismissChip(record) {
  document.getElementById(CHIP_ID)?.remove();
  chipVisible = false;
  if (record) lastDismissedUrl = location.href;
}


async function suppressSite() {
  const host = _host();
  suppressedSites.add(host);
  await chrome.storage.local.set({ rf_suppressed: [...suppressedSites] });
}

// ── Communication ─────────────────────────────────────────────────────────────

function sendToRuneFetch(url, title) {
  chrome.runtime.sendMessage({ type: "RF_SEND_URL", url, title: title || "" }, () => {});
}

// ── Message from popup ────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener(msg => {
  if (msg.type === "RF_SCAN_PAGE") {
    dismissChip(false);
    lastDismissedUrl = "";
    if (!suppressedSites.has(_host())) {
      showChip([{ url: location.href, title: document.title, kind: "manual" }]);
    }
  }
});

// ── Boot ──────────────────────────────────────────────────────────────────────

init();
