/**
 * RuneFetch Extension — Content Script
 *
 * Detects downloadable media on the current page and shows a single
 * compact capture chip. The chip is stateful: one instance per tab,
 * three display modes (single / multiple / playlist).
 *
 * Attention-budget rules (§2.3 of the roadmap):
 *   • Only appears on high-confidence triggers (recognised-site or direct-download).
 *   • At most one chip visible per tab at a time.
 *   • Auto-dismisses after 6 s with no interaction.
 *   • Esc key or click-away dismisses it.
 *   • Per-site suppression stored in chrome.storage.local.
 *   • Global off-switch via chrome.storage.local.rf_chip_enabled.
 */

"use strict";

// ── Platform recognition (mirrors core/detector.py) ───────────────────────────

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
  "pinterest.com", "www.pinterest.com",
  "dailymotion.com", "bilibili.com", "rumble.com", "odysee.com",
  "bandcamp.com", "mixcloud.com", "archive.org",
]);

const DIRECT_EXTS = new Set([
  "mp4","mkv","avi","mov","webm","m4v","mp3","flac","wav","aac",
  "ogg","m4a","opus","zip","rar","7z","tar","gz","pdf","apk","dmg",
  "jpg","jpeg","png","gif","webp",
]);

const DRM_HOSTS = new Set([
  "netflix.com","primevideo.com","amazon.com","hotstar.com",
  "disneyplus.com","hulu.com","max.com","peacocktv.com",
  "paramountplus.com","crunchyroll.com",
]);

const AUTO_DISMISS_MS = 12000;
const CHIP_ID = "rf-capture-chip";

let chipDismissTimer = null;
let chipVisible = false;
let suppressedSites = new Set();
let chipEnabled = true;
let lastDismissedUrl = "";

// ── State init ────────────────────────────────────────────────────────────────

async function init() {
  const data = await chrome.storage.local.get(["rf_suppressed", "rf_chip_enabled"]);
  suppressedSites = new Set(data.rf_suppressed || []);
  chipEnabled = data.rf_chip_enabled !== false;   // default on

  const host = location.hostname.replace(/^www\./, "");

  if (!chipEnabled) return;
  if (DRM_HOSTS.has(host)) return;
  if (suppressedSites.has(host)) return;

  // High-confidence trigger: recognised media site — show chip immediately
  if (RECOGNISED_HOSTS.has(host)) {
    showChip([{ url: location.href, title: document.title, kind: "media-page" }]);
  }

  // Always observe DOM for direct-file links on any page
  observeMediaLinks();
}

// ── DOM observer ──────────────────────────────────────────────────────────────

function observeMediaLinks() {
  const scan = () => {
    if (!chipEnabled || chipVisible) return;
    const host = location.hostname.replace(/^www\./, "");
    if (suppressedSites.has(host) || DRM_HOSTS.has(host)) return;

    const found = [];
    document.querySelectorAll("a[href]").forEach(a => {
      try {
        const url = new URL(a.href);
        const ext = url.pathname.split(".").pop().toLowerCase();
        if (DIRECT_EXTS.has(ext) && !found.some(f => f.url === a.href)) {
          found.push({ url: a.href, title: a.textContent.trim() || a.href.split("/").pop(), kind: "direct" });
        }
      } catch (_) {}
    });
    if (found.length > 0) showChip(found);
  };

  const mo = new MutationObserver(scan);
  mo.observe(document.body, { childList: true, subtree: true });
  scan();   // initial scan
}

// ── Chip rendering ────────────────────────────────────────────────────────────

function showChip(items) {
  if (chipVisible) return;
  if (location.href === lastDismissedUrl) return;

  const existing = document.getElementById(CHIP_ID);
  if (existing) existing.remove();

  const chip = document.createElement("div");
  chip.id = CHIP_ID;
  chip.setAttribute("role", "dialog");
  chip.setAttribute("aria-label", "RuneFetch download capture");

  const single = items.length === 1;
  const label  = single
    ? (items[0].title || items[0].url).slice(0, 48)
    : `${items.length} downloadable items`;

  chip.innerHTML = `
    <div class="rf-chip-inner">
      <span class="rf-logo">⛩</span>
      <span class="rf-desc">${escHtml(label)}</span>
      <button class="rf-btn-dl" title="Download with RuneFetch">↓ Download</button>
      <button class="rf-btn-x" title="Dismiss (Esc)" aria-label="Dismiss">✕</button>
    </div>
    ${items.length > 1 ? `<div class="rf-list">${items.slice(0,5).map(i =>
      `<div class="rf-list-item" data-url="${escAttr(i.url)}">${escHtml((i.title||i.url).slice(0,40))}</div>`
    ).join("")}${items.length>5?`<div class="rf-list-more">…and ${items.length-5} more</div>`:""}</div>` : ""}
    <div class="rf-suppress"><a href="#" class="rf-suppress-link">Don't show on this site</a></div>
  `;

  document.body.appendChild(chip);
  chipVisible = true;

  // Button wiring
  chip.querySelector(".rf-btn-dl").addEventListener("click", () => {
    items.forEach(item => sendToRuneFetch(item.url, item.title));
    dismissChip(true);
  });
  chip.querySelector(".rf-btn-x").addEventListener("click", () => dismissChip(true));
  chip.querySelectorAll(".rf-list-item").forEach(el => {
    el.addEventListener("click", () => {
      sendToRuneFetch(el.dataset.url, el.textContent);
      dismissChip(true);
    });
  });
  const suppressLink = chip.querySelector(".rf-suppress-link");
  if (suppressLink) {
    suppressLink.addEventListener("click", e => {
      e.preventDefault();
      suppressSite();
      dismissChip(true);
    });
  }

  // Auto-dismiss
  resetDismissTimer();

  // Esc key
  document.addEventListener("keydown", onEsc);
}

function dismissChip(record) {
  const chip = document.getElementById(CHIP_ID);
  if (chip) chip.remove();
  chipVisible = false;
  clearTimeout(chipDismissTimer);
  document.removeEventListener("keydown", onEsc);
  if (record) lastDismissedUrl = location.href;
}

function resetDismissTimer() {
  clearTimeout(chipDismissTimer);
  chipDismissTimer = setTimeout(() => dismissChip(false), AUTO_DISMISS_MS);
}

function onEsc(e) {
  if (e.key === "Escape") dismissChip(true);
}

async function suppressSite() {
  const host = location.hostname.replace(/^www\./, "");
  suppressedSites.add(host);
  await chrome.storage.local.set({ rf_suppressed: [...suppressedSites] });
}

// ── Communication ─────────────────────────────────────────────────────────────

function sendToRuneFetch(url, title) {
  chrome.runtime.sendMessage({ type: "RF_SEND_URL", url, title }, () => {});
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function escHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
function escAttr(s) {
  return String(s).replace(/"/g,"&quot;");
}

// ── Message from popup (force scan) ──────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "RF_SCAN_PAGE") {
    dismissChip(false);
    lastDismissedUrl = "";
    const host = location.hostname.replace(/^www\./, "");
    if (!suppressedSites.has(host)) {
      showChip([{ url: location.href, title: document.title, kind: "manual" }]);
    }
  }
});

// ── Boot ──────────────────────────────────────────────────────────────────────

init();
