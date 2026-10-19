/**
 * RuneFetch web UI — full-parity app module.
 *
 * Features:
 *   Titlebar drag (JS + api.move_window) · Maximize/restore · Edge resize
 *   Download queue cards with progress, open-folder, collapsible log panel
 *   Quality modal with Download Later checkbox · prompt_per_file folder picker
 *   History (JSON-backed) with delete, clear, double-click redownload
 *   File-exists check before redownload · Browser-extension confirm dialog
 *   Settings panel covering all Qt-equivalent options
 *   Live status bar (speed + save path) · Tray live tooltip via engine
 */

import { ws } from './ws.js';

// ── State ─────────────────────────────────────────────────────────────────────

const S = {
  items:    new Map(),   // id → item dict
  history:  [],          // newest-first
  settings: {},
  view:     'queue',
  connected: false,
  maximized: false,

  // quality modal
  pendingUrl:        '',
  pendingDet:        null,
  pendingReqId:      '',
  pendingFormats:    null,
  selectedFmt:       '',
  selectedIsAudio:   false,
  selectedQualLabel: '',

  // history selection
  selectedHistIds: new Set(),

  // confirm modal (bridge)
  confirmData: null,

  // exists modal
  existsCallback: null,
};

// ── DOM ───────────────────────────────────────────────────────────────────────

const $ = id => document.getElementById(id);
const uiIcon = name => `<svg class="ui-icon" aria-hidden="true"><use href="#icon-${name}"/></svg>`;

// ── Init ──────────────────────────────────────────────────────────────────────

(async () => {
  setupTitleBar();
  setupNav();
  setupUrlBar();
  setupQualityModal();
  setupQueueToolbar();
  setupHistoryToolbar();
  setupSettingsForm();
  setupConfirmModal();
  setupExistsModal();
  setupUpdates();

  ws.on('_connected',     onConnected);
  ws.on('_disconnected',  onDisconnected);
  ws.on('item_update',    onItemUpdate);
  ws.on('item_removed',   onItemRemoved);
  ws.on('item_log',       onItemLog);
  ws.on('history_added',  onHistoryAdded);
  ws.on('history_cleared',() => { S.history = []; renderHistory(); });
  ws.on('toast',          d  => toast(d.message, d.level));
  ws.on('formats_ready',  onFormatsReady);
  ws.on('settings',       onSettings);
  ws.on('bridge_url',     onBridgeUrl);

  await ws.init();

  // Automatic update check, a few seconds after startup so it never competes
  // with restoring the queue or the first paint. The backend throttles this to
  // once a day, so a frequently-restarted app does not hammer the API.
  setTimeout(() => {
    if (S.settings.auto_check_updates !== false) checkForUpdate(false);
  }, 4000);
})();

// ── Navigation ────────────────────────────────────────────────────────────────

function setupNav() {
  $('dwarvenstack-link').addEventListener('click', async e => {
    if (!window.pywebview?.api?.open_project_page) return;
    e.preventDefault();
    try {
      const opened = await window.pywebview.api.open_project_page();
      if (!opened) toast('Could not open your browser. Visit github.com/dwarvenstack.', 'warn');
    } catch {
      toast('Could not open your browser. Visit github.com/dwarvenstack.', 'warn');
    }
  });
  document.querySelectorAll('.nav-btn[data-view]').forEach(btn => {
    btn.addEventListener('click', () => switchView(btn.dataset.view));
  });
}

function switchView(name) {
  S.view = name;
  document.querySelectorAll('.view').forEach(v =>
    v.classList.toggle('active', v.id === `view-${name}`)
  );
  document.querySelectorAll('.nav-btn[data-view]').forEach(b =>
    b.classList.toggle('active', b.dataset.view === name)
  );
  if (name === 'history')  loadHistory();
  if (name === 'settings') renderSettings();
}

// ── Title bar (drag, resize, maximize) ────────────────────────────────────────

function setupTitleBar() {
  // Window controls
  $('win-minimize').addEventListener('click', () => pyApi('minimize'));
  $('win-close').addEventListener('click',    () => pyApi('close'));
  $('win-maximize').addEventListener('click', toggleMaximize);

  // Drag: listen on #titlebar itself, skip interactive children
  const titlebar = $('titlebar');
  let drag = null;

  titlebar.addEventListener('mousedown', e => {
    if (e.button !== 0) return;
    if (e.target.closest('button, input, a, select')) return;
    drag = { mx: e.screenX, my: e.screenY, wx: window.screenX, wy: window.screenY };
    e.preventDefault();
  });

  document.addEventListener('mousemove', e => {
    if (!drag) return;
    const nx = drag.wx + (e.screenX - drag.mx);
    const ny = drag.wy + (e.screenY - drag.my);
    pyApi('move_window', nx, ny);
  });

  document.addEventListener('mouseup', () => { drag = null; });

  // Double-click titlebar → toggle maximize (not on interactive elements)
  titlebar.addEventListener('dblclick', e => {
    if (e.target.closest('button, input, a, select')) return;
    toggleMaximize();
  });

  // Edge resize
  setupEdgeResize();
}

async function toggleMaximize() {
  try {
    S.maximized = await window.pywebview.api.toggle_maximize();
    $('win-maximize').textContent = S.maximized ? '❐' : '□';
    $('win-maximize').title = S.maximized ? 'Restore' : 'Maximize';
  } catch {}
}

// ── Edge resize ───────────────────────────────────────────────────────────────

const EDGE = 6;  // px detection margin

function setupEdgeResize() {
  let resizing = null;

  document.addEventListener('mousemove', e => {
    if (resizing) {
      applyResize(resizing, e);
      return;
    }
    const edge = getEdge(e);
    document.body.className = edge ? `resize-${dirClass(edge)}` : '';
  });

  document.addEventListener('mousedown', e => {
    if (e.button !== 0) return;
    const edge = getEdge(e);
    if (edge) {
      resizing = {
        edge, mx: e.screenX, my: e.screenY,
        wx: window.screenX, wy: window.screenY,
        ww: window.outerWidth, wh: window.outerHeight,
      };
      e.preventDefault();
    }
  });

  document.addEventListener('mouseup', () => { resizing = null; });
}

function getEdge(e) {
  const { clientX: x, clientY: y } = e;
  const w = window.innerWidth, h = window.innerHeight;
  const t = e.target;
  // Don't resize when hovering interactive elements
  if (t && t.closest('button,input,select,textarea,a,[data-view],.url-bar-wrap')) return null;
  const l = x <= EDGE, r = x >= w - EDGE, top = y <= EDGE, bot = y >= h - EDGE;
  if (top && l)  return 'nw';
  if (top && r)  return 'ne';
  if (bot && l)  return 'sw';
  if (bot && r)  return 'se';
  if (l)   return 'w';
  if (r)   return 'e';
  if (top) return 'n';
  if (bot) return 's';
  return null;
}

function dirClass(edge) {
  return { nw:'nw', ne:'ne', sw:'sw', se:'se', w:'w', e:'e', n:'n', s:'s' }[edge] || '';
}

function applyResize(r, e) {
  const dx = e.screenX - r.mx, dy = e.screenY - r.my;
  let x = r.wx, y = r.wy, w = r.ww, h = r.wh;
  const minW = 800, minH = 560;

  if (r.edge.includes('e')) w = Math.max(minW, r.ww + dx);
  if (r.edge.includes('s')) h = Math.max(minH, r.wh + dy);
  if (r.edge.includes('w')) { const nw = Math.max(minW, r.ww - dx); x = r.wx + (r.ww - nw); w = nw; }
  if (r.edge.includes('n')) { const nh = Math.max(minH, r.wh - dy); y = r.wy + (r.wh - nh); h = nh; }

  if (r.edge === 'e' || r.edge === 's' || r.edge === 'se') {
    pyApi('resize_window', w, h);
  } else {
    pyApi('move_and_resize', x, y, w, h);
  }
}

// ── URL bar ───────────────────────────────────────────────────────────────────

function setupUrlBar() {
  $('btn-paste').addEventListener('click', async () => {
    try {
      let text = '';
      // navigator.clipboard.readText() is blocked in WebView2 from file:// (not a secure context).
      // Use the Python API first; fall back to navigator.clipboard for dev/browser usage.
      if (window.pywebview?.api?.read_clipboard) {
        text = await window.pywebview.api.read_clipboard();
      } else {
        text = await navigator.clipboard.readText();
      }
      if (text) {
        $('url-input').value = text.trim();
        $('url-input').focus();
      } else {
        toast('Clipboard is empty', 'warn');
      }
    } catch { toast('Clipboard read failed', 'warn'); }
  });

  $('btn-add').addEventListener('click', () => startDownload());
  $('url-input').addEventListener('keydown', e => { if (e.key === 'Enter') startDownload(); });
}

async function startDownload(urlOverride, detOverride) {
  const raw = (urlOverride || $('url-input').value || '').trim();
  if (!raw) { toast('Paste or type a URL first', 'warn'); return; }
  if (!S.connected) { toast('Not connected to server — please wait a moment', 'warn'); return; }
  const url = /^https?:\/\//i.test(raw) ? raw : 'https://' + raw;

  let det = detOverride;
  if (!det) {
    try {
      const res = await ws.send('detect', { url });
      det = res.detection;
    } catch (err) { toast('Could not detect URL: ' + err.message, 'error'); return; }
  }

  if (det.type === 'drm') {
    toast(`${det.label} uses DRM — cannot download`, 'error');
    return;
  }

  if (det.series_capable) {
    if (S.inspectingSeries) return;
    S.inspectingSeries = true;
    $('btn-add').disabled = true;
    toast('Looking up the episode list…', 'info');
    try {
      const response = await ws.send('inspect_series', { url });
      det = { ...det, series: response.series };
    } catch (err) {
      toast('Could not read the episode list: ' + err.message, 'error');
      return;
    } finally {
      S.inspectingSeries = false;
      $('btn-add').disabled = false;
    }
  }

  // prompt_per_file: ask for folder before quality
  let savePathOverride = '';
  if (S.settings.prompt_per_file) {
    try { savePathOverride = await window.pywebview.api.choose_folder() || ''; } catch {}
  }

  // Direct files (images, PDFs, archives, docs) — skip modal entirely
  if (det.type === 'direct') {
    try {
      await ws.send('add', {
        url,
        opts: {
          title:        det.label || '',
          source_label: det.label || '',
          source_icon:  det.icon  || '',
          fmt:          'best',
          quality:      '',
          dl_type:      'direct',
          save_path:    savePathOverride || S.settings.save_path || '',
          start_paused: false,
          is_playlist:  false,
        },
      });
      toast('Download started', 'info');
      if (S.view !== 'queue') switchView('queue');
      if (!urlOverride) $('url-input').value = '';
    } catch (err) { toast('Failed to add: ' + err.message, 'error'); }
    return;
  }

  S.pendingUrl        = url;
  S.pendingDet        = det;
  S.pendingFormats    = null;
  S.selectedFmt       = '';
  S.selectedIsAudio   = false;
  S.selectedQualLabel = '';
  S.pendingSavePath   = savePathOverride;

  // Spotify / audio-only platforms: show simplified audio quality options
  if (det.type === 'spotify') {
    openAudioQualityModal(det);
    if (!urlOverride) $('url-input').value = '';
    return;
  }

  openQualityModal(det);
  if (!urlOverride) $('url-input').value = '';
}

// ── Audio-only quality modal (Spotify, SoundCloud, etc.) ─────────────────────

function openAudioQualityModal(det) {
  $('series-options').hidden = true;
  $('btn-download').textContent = 'Download';
  $('qual-title').textContent    = 'Select Audio Quality';
  $('qual-subtitle').textContent = (det.batch_label || det.label || '').slice(0, 60);
  $('btn-download').disabled     = false;
  $('chk-download-later').checked = false;
  $('qual-status').textContent   = 'Choose audio quality:';
  showQualityOptions([
    { label: 'Best quality (320 kbps)', fmt: 'bestaudio/best', isAudio: true, sz: '' },
    { label: 'Standard (128 kbps)',     fmt: 'bestaudio[abr<=128]/bestaudio/best', isAudio: true, sz: '' },
  ], false);
  pickQuality({ label: 'Best quality (320 kbps)', fmt: 'bestaudio/best', isAudio: true });
  $('quality-modal').showModal();
}

// ── Quality modal ─────────────────────────────────────────────────────────────

function setupQualityModal() {
  const dlg = $('quality-modal');
  $('btn-cancel-qual').addEventListener('click', () => dlg.close());
  $('btn-close-qual').addEventListener('click',  () => dlg.close());
  $('btn-download').addEventListener('click', confirmDownload);
  $('series-scope').addEventListener('change', updateSeriesChoice);
  $('series-zip').addEventListener('change', updateSeriesChoice);
  // Close on backdrop click
  dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close(); });
}

function openQualityModal(det) {
  $('series-options').hidden = !det.series;
  $('btn-download').textContent = 'Download';
  $('qual-title').textContent    = 'Select Quality';
  $('qual-subtitle').textContent = (det.batch_label || det.label || det.host || '').slice(0, 60);
  $('btn-download').disabled     = true;
  $('qual-options').innerHTML    = '';
  $('chk-download-later').checked = false;
  clearTimeout(S._qualTimeout);

  if (det.series) {
    const series = det.series;
    $('qual-title').textContent = 'Download episodes';
    $('qual-subtitle').textContent = series.title;
    $('series-title').textContent = `${series.count} episodes found`;
    const one = $('series-scope').querySelector('[value="one"]');
    one.disabled = !series.current_episode;
    one.textContent = series.current_episode ? `This episode (${series.current_episode.number})` : 'Open an episode link to choose one';
    $('series-scope').value = series.current_episode ? 'one' : 'all';
    $('series-zip').checked = false;
    updateSeriesChoice();
    $('quality-modal').showModal();
    return;
  }

  const needsFetch = (det.type === 'youtube' || det.type === 'ytdlp') && !det.is_playlist;

  if (det.is_playlist) {
    $('qual-status').textContent = 'Playlist — quality applies to all videos:';
    showFallbackQualities();
  } else if (needsFetch) {
    $('qual-status').innerHTML = 'Fetching available qualities<span class="loading-dots"></span>';
    S.pendingReqId = Math.random().toString(36).slice(2);
    ws.fire('fetch_formats', {
      url: S.pendingUrl, request_id: S.pendingReqId,
      proxy: S.settings.proxy || '',
    });
    S._qualTimeout = setTimeout(() => {
      if (!S.pendingFormats) {
        $('qual-status').textContent = "Couldn't fetch formats — using standard list:";
        showFallbackQualities();
      }
    }, 15000);
  } else {
    $('qual-status').textContent = 'Choose download quality:';
    showFallbackQualities();
  }

  $('quality-modal').showModal();
}

function updateSeriesChoice() {
  const series = S.pendingDet?.series;
  if (!series) return;
  const all = $('series-scope').value === 'all';
  $('series-zip').disabled = !all;
  $('series-note').hidden = !all || !$('series-zip').checked;
  $('btn-download').textContent = all ? `Download ${series.count} episodes` : 'Download episode';
  if (all) {
    S.pendingReqId = '';
    clearTimeout(S._qualTimeout);
    $('qual-status').textContent = 'Quality applies to every episode; availability can vary.';
    showFallbackQualities();
  } else {
    $('qual-status').textContent = 'Fetching this episode’s qualities…';
    S.pendingReqId = Math.random().toString(36).slice(2);
    ws.fire('fetch_formats', { url: series.current_episode.url, request_id: S.pendingReqId, proxy: S.settings.proxy || '' });
    showFallbackQualities();
  }
}

function onFormatsReady(data) {
  if (data.request_id !== S.pendingReqId) return;
  clearTimeout(S._qualTimeout);
  if (!$('quality-modal').open) return;

  const formats = data.formats || [];
  if (data.error || !formats.length) {
    $('qual-status').textContent = "Couldn't fetch formats — using standard list:";
    showFallbackQualities(); return;
  }

  const seen = new Set(); const opts = [];
  for (const f of [...formats].reverse()) {
    const h = f.height;
    // Some HLS manifests provide resolution without codec metadata.
    if (!h || f.vcodec?.toLowerCase() === 'none' || seen.has(h)) continue;
    seen.add(h);
    const res = h === 2160 ? '4K · 2160p' : h === 1440 ? '2K · 1440p' : `${h}p`;
    const sz  = f.filesize || f.filesize_approx;
    opts.push({
      label: res, isAudio: false, sz: sz ? fmtBytes(sz) : '',
      fmt: `bestvideo[height<=${h}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=${h}]+bestaudio/best[height<=${h}]/best`,
    });
  }
  opts.sort((a, b) => heightOf(b.label) - heightOf(a.label));
  opts.push({ label: 'Audio only  (MP3 · 320 kbps)', fmt: 'bestaudio/best', isAudio: true, sz: '' });

  if (!opts.length) { showFallbackQualities(); return; }

  S.pendingFormats = formats;
  $('qual-status').textContent = data.title
    ? `Available qualities: ${data.title.slice(0, 46)}`
    : 'Available qualities for this video:';
  showQualityOptions(opts, true);
}

const FALLBACK_QUALITIES = [
  { label: 'Best quality (auto)', isAudio: false, fmt: 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best' },
  { label: '1080p HD',            isAudio: false, fmt: 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best' },
  { label: '720p HD',             isAudio: false, fmt: 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best' },
  { label: '480p',                isAudio: false, fmt: 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]/best' },
  { label: '360p',                isAudio: false, fmt: 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best[height<=360]/best' },
  { label: 'Audio only (MP3 320k)', isAudio: true, fmt: 'bestaudio/best' },
];

function showFallbackQualities() { showQualityOptions(FALLBACK_QUALITIES, false); }

function showQualityOptions(opts, withSize) {
  $('qual-options').innerHTML = '';
  opts.forEach((opt, i) => {
    const row = document.createElement('div');
    row.className = 'quality-option';
    const rb = document.createElement('input');
    rb.type = 'radio'; rb.name = 'quality'; rb.id = `q${i}`;
    if (i === 0) { rb.checked = true; pickQuality(opt); }
    rb.addEventListener('change', () => pickQuality(opt));
    const lbl = document.createElement('label'); lbl.htmlFor = `q${i}`; lbl.textContent = opt.label;
    row.append(rb, lbl);
    if (withSize && opt.sz) {
      const sz = document.createElement('span'); sz.className = 'size-hint'; sz.textContent = `~${opt.sz}`; row.append(sz);
    }
    row.addEventListener('click', e => { if (e.target !== rb) { rb.checked = true; pickQuality(opt); } });
    $('qual-options').appendChild(row);
  });
  $('btn-download').disabled = false;
}

function pickQuality(opt) {
  S.selectedFmt       = opt.fmt;
  S.selectedIsAudio   = opt.isAudio;
  S.selectedQualLabel = opt.label;
}

async function confirmDownload() {
  if (!S.pendingUrl || !S.selectedFmt) return;
  $('quality-modal').close();
  const det = S.pendingDet || {};
  const startPaused = $('chk-download-later').checked;
  const series = det.series;
  const batch = series && $('series-scope').value === 'all';
  const downloadUrl = series && !batch ? series.current_episode.url : S.pendingUrl;
  try {
    await ws.send('add', {
      url: downloadUrl,
      opts: {
        title:        batch ? series.title : '',
        source_label: det.label  || '',
        source_icon:  det.icon   || '',
        fmt:          S.selectedFmt,
        quality:      S.selectedQualLabel,
        dl_type:      batch ? 'hianime_series' : (det.type || 'ytdlp'),
        series:       batch ? { ...series, zip: $('series-zip').checked } : undefined,
        save_path:    S.pendingSavePath || S.settings.save_path || '',
        start_paused: startPaused,
        is_playlist:  det.is_playlist || false,
      },
    });
    toast(startPaused ? 'Added to queue (paused)' : 'Download started', 'info');
    if (S.view !== 'queue') switchView('queue');
  } catch (err) { toast('Failed to add: ' + err.message, 'error'); }
}

// ── Browser extension confirm modal ───────────────────────────────────────────

function setupConfirmModal() {
  const dlg = $('confirm-modal');
  const closeConfirm = () => { S.confirmData = null; dlg.close(); };
  $('btn-confirm-cancel').addEventListener('click', closeConfirm);
  $('btn-close-confirm').addEventListener('click',  closeConfirm);
  $('btn-confirm-ok').addEventListener('click', async () => {
    const d = S.confirmData;
    S.confirmData = null;
    dlg.close();
    if (!d) return;
    const startPaused = $('chk-confirm-later').checked;
    await startDownload(d.url, { type: d.type, label: d.label, icon: d.icon,
                                  is_playlist: d.is_playlist, _startPaused: startPaused });
  });
  // Close on backdrop click
  dlg.addEventListener('click', e => { if (e.target === dlg) closeConfirm(); });
}

function onBridgeUrl(data) {
  S.confirmData = data;
  $('confirm-title').textContent = `Download from ${data.label || 'browser'}?`;
  $('confirm-url').textContent   = data.url.slice(0, 120);
  $('chk-confirm-later').checked = false;
  $('confirm-modal').showModal();
}

// ── File-exists modal ─────────────────────────────────────────────────────────

function setupExistsModal() {
  const dlg = $('exists-modal');
  const closeExists = () => { dlg.close(); S.existsCallback = null; };
  $('btn-close-exists').addEventListener('click',      closeExists);
  $('btn-exists-open').addEventListener('click', () => {
    dlg.close();
    if (S.existsCallback) S.existsCallback('open');
  });
  $('btn-exists-redownload').addEventListener('click', () => {
    dlg.close();
    if (S.existsCallback) S.existsCallback('redownload');
  });
  // Close on backdrop click
  dlg.addEventListener('click', e => { if (e.target === dlg) closeExists(); });
}

function showExistsModal(filename, savePath, callback) {
  $('exists-info').textContent = `"${filename}" already exists in your downloads folder. Open the folder or download again?`;
  S.existsCallback = callback;
  S._existsSavePath = savePath;
  $('exists-modal').showModal();
}

// ── Queue toolbar ─────────────────────────────────────────────────────────────

function setupQueueToolbar() {
  $('btn-resume-all').addEventListener('click', () => ws.fire('resume_all'));
  $('btn-pause-all').addEventListener('click',  () => ws.fire('pause_all'));
  $('btn-clear-done').addEventListener('click', () => ws.fire('clear_completed'));
  $('btn-clear-all').addEventListener('click',  () => {
    for (const id of S.items.keys()) ws.fire('remove', { id });
  });
}

// ── History toolbar ────────────────────────────────────────────────────────────

function setupHistoryToolbar() {
  $('btn-history-delete-sel').addEventListener('click', deleteSelectedHistory);
  $('btn-history-clear').addEventListener('click', async () => {
    if (!confirm('Remove all history records? This cannot be undone.')) return;
    await ws.send('clear_history');
  });
}

async function loadHistory() {
  try {
    const res = await ws.send('get_history');
    S.history = res.history || [];
    renderHistory();
  } catch {}
}

function renderHistory() {
  S.selectedHistIds.clear();
  $('btn-history-delete-sel').disabled = true;

  const list = $('history-list');
  list.innerHTML = '';
  const empty = $('history-empty');

  if (!S.history.length) {
    empty.style.display = 'flex'; return;
  }
  empty.style.display = 'none';
  $('history-count').textContent = `${S.history.length} item${S.history.length !== 1 ? 's' : ''}`;

  S.history.forEach(item => list.appendChild(buildHistCard(item)));
}

function buildHistCard(item) {
  const ok    = item.state === 'Complete';
  const card  = document.createElement('div');
  card.className = 'hist-card';
  card.dataset.histId = item.id;

  const fmt = item.fmt_display || item.fmt || '—';
  const sub = [item.source_label, fmt, item.size, item.date].filter(Boolean).join('  ·  ');

  card.innerHTML = `
    <span class="hist-icon">${uiIcon('file')}</span>
    <div class="hist-meta">
      <div class="hist-title" title="${esc(item.title || item.url || '')}">${esc(item.title || item.url || '—')}</div>
      <div class="hist-sub">
        <span>${esc(sub)}</span>
        <span class="${ok ? 'hist-ok' : 'hist-err'}">${ok ? '✓ Complete' : `✗ ${esc(item.error_msg || 'Error')}`}</span>
      </div>
    </div>
    <div class="hist-actions">
      <button class="icon-btn" data-hist-action="redownload" title="Re-download">↺</button>
      <button class="icon-btn danger" data-hist-action="delete" title="Delete entry" aria-label="Delete entry">${uiIcon('trash')}</button>
    </div>`;

  // Select on click (anywhere except action buttons)
  card.addEventListener('click', e => {
    if (e.target.closest('[data-hist-action]')) return;
    card.classList.toggle('is-selected', !S.selectedHistIds.has(item.id));
    if (S.selectedHistIds.has(item.id)) S.selectedHistIds.delete(item.id);
    else S.selectedHistIds.add(item.id);
    $('btn-history-delete-sel').disabled = S.selectedHistIds.size === 0;
  });

  // Double-click → redownload
  card.addEventListener('dblclick', () => triggerRedownload(item));

  card.querySelector('[data-hist-action="redownload"]')
      .addEventListener('click', () => triggerRedownload(item));

  card.querySelector('[data-hist-action="delete"]')
      .addEventListener('click', () => deleteHistEntry(item.id));

  return card;
}

async function triggerRedownload(item) {
  const savePath = item.save_path || S.settings.save_path || '';
  const title    = item.title || '';

  if (savePath && title) {
    try {
      const res = await ws.send('check_file_exists', { save_path: savePath, title });
      if (res.exists) {
        showExistsModal(res.filename, savePath, async action => {
          if (action === 'open') {
            ws.fire('open_folder', { path: savePath });
          } else {
            await doRedownload(item.id);
          }
        });
        return;
      }
    } catch {}
  }
  await doRedownload(item.id);
}

async function doRedownload(id) {
  try {
    const res = await ws.send('redownload', { id });
    toast('Re-download queued', 'info');
    switchView('queue');
  } catch (err) { toast('Redownload failed: ' + err.message, 'error'); }
}

async function deleteHistEntry(id) {
  try {
    await ws.send('delete_history', { id });
    S.history = S.history.filter(e => e.id !== id);
    const card = document.querySelector(`.hist-card[data-hist-id="${id}"]`);
    if (card) card.remove();
    $('history-count').textContent = `${S.history.length} item${S.history.length !== 1 ? 's' : ''}`;
    if (!S.history.length) $('history-empty').style.display = 'flex';
  } catch (err) { toast('Delete failed: ' + err.message, 'error'); }
}

async function deleteSelectedHistory() {
  const ids = [...S.selectedHistIds];
  for (const id of ids) await deleteHistEntry(id);
  S.selectedHistIds.clear();
  $('btn-history-delete-sel').disabled = true;
}

// ── Settings ──────────────────────────────────────────────────────────────────

function renderSettings() {
  const s = S.settings;
  const set = (id, val) => { const el = $(id); if (el) { if (el.type === 'checkbox') el.checked = !!val; else el.value = val ?? ''; } };
  $('setting-save-path').textContent  = s.save_path || '—';
  const tok = s.bridge_token || s.extension_token || '';
  $('setting-ext-token').textContent  = tok || '(not set)';
  set('setting-prompt-per-file',  s.prompt_per_file);
  set('setting-max-concurrent',   s.max_concurrent ?? 2);
  set('setting-throttle',         s.throttle_kbps  ?? 0);
  set('setting-fragments',        s.fragment_threads ?? 4);
  set('setting-proxy',            s.proxy || '');
  set('setting-autostart',        s.autostart !== false);
  set('setting-keep-history',     s.keep_history !== false);
  set('setting-clipboard',        s.clipboard_monitor);
  set('setting-close-to-tray',    s.close_to_tray !== false);
  set('setting-theme',            s.theme || 'dark');
  set('setting-auto-update',      s.auto_check_updates !== false);
}

function setupSettingsForm() {
  $('btn-copy-token').addEventListener('click', async () => {
    const tok = $('setting-ext-token').textContent;
    if (!tok || tok === '(not set)') { toast('No token configured', 'warn'); return; }
    try {
      await navigator.clipboard.writeText(tok);
      toast('Token copied to clipboard', 'info');
    } catch { toast('Clipboard write failed', 'warn'); }
  });

  $('btn-choose-folder').addEventListener('click', async () => {
    try {
      const folder = await window.pywebview.api.choose_folder();
      if (folder) {
        S.settings.save_path = folder;
        $('setting-save-path').textContent = folder;
      }
    } catch { toast('Folder picker failed', 'warn'); }
  });

  $('settings-form').addEventListener('submit', async e => {
    e.preventDefault();
    const g = id => { const el = $(id); return el ? (el.type === 'checkbox' ? el.checked : el.value) : undefined; };
    const patch = {
      save_path:         S.settings.save_path || '',
      prompt_per_file:   !!g('setting-prompt-per-file'),
      max_concurrent:    parseInt(g('setting-max-concurrent') || 2),
      throttle_kbps:     parseInt(g('setting-throttle') || 0),
      fragment_threads:  parseInt(g('setting-fragments') || 4),
      proxy:             (g('setting-proxy') || '').trim(),
      autostart:         !!g('setting-autostart'),
      keep_history:      !!g('setting-keep-history'),
      clipboard_monitor: !!g('setting-clipboard'),
      close_to_tray:     !!g('setting-close-to-tray'),
      theme:             g('setting-theme') || 'dark',
      auto_check_updates: !!g('setting-auto-update'),
    };
    try {
      await ws.send('save_settings', { settings: patch });
      toast('Settings saved', 'info');
    } catch (err) { toast('Save failed: ' + err.message, 'error'); }
  });
}

// ── Updates ───────────────────────────────────────────────────────────────────

// Holds the last check result so the Update button knows what to download.
let _pendingUpdate = null;

function setupUpdates() {
  // Show the running version immediately — it comes from the native API, so it
  // is correct even when GitHub is unreachable.
  window.pywebview?.api?.get_version?.()
    .then(v => {
      $('update-status').textContent   = `RuneFetch ${v}`;
    })
    .catch(() => {});

  $('btn-check-update').addEventListener('click', () => checkForUpdate(true));
  $('btn-close-update').addEventListener('click', () => $('update-modal').close());
  $('btn-update-later').addEventListener('click', () => $('update-modal').close());
  $('btn-update-now').addEventListener('click', startUpdate);

  ws.on('update_progress', d => {
    const mb = b => (b / 1048576).toFixed(1);
    if (d.percent < 0) {
      // Server could not determine the total size — show bytes only, and keep
      // the bar visibly busy rather than parked at 0%.
      $('update-bar-fill').style.width = '100%';
      $('update-bar-fill').classList.add('indeterminate');
      $('update-progress-text').textContent = `Downloading… ${mb(d.done)} MB`;
    } else {
      $('update-bar-fill').classList.remove('indeterminate');
      $('update-bar-fill').style.width = `${d.percent}%`;
      $('update-progress-text').textContent =
        `Downloading… ${d.percent}%  (${mb(d.done)} / ${mb(d.total)} MB)`;
    }
  });

  ws.on('update_ready', () => {
    $('update-progress-text').textContent = 'Installing — RuneFetch will restart…';
    $('update-bar-fill').style.width = '100%';
  });

  ws.on('update_failed', d => {
    $('update-progress').style.display = 'none';
    $('btn-update-now').disabled = false;
    $('btn-update-later').disabled = false;
    toast('Update failed: ' + (d.error || 'unknown error'), 'error');
  });
}

/** Ask the backend to check GitHub. `manual` shows "up to date" feedback. */
async function checkForUpdate(manual = false) {
  const statusEl = $('update-status');
  if (manual) statusEl.textContent = 'Checking…';

  let info;
  try {
    const res = await ws.send('check_update', { force: manual });
    info = res.update || {};
  } catch (err) {
    if (manual) {
      statusEl.textContent = 'Check failed';
      toast('Update check failed: ' + err.message, 'error');
    }
    return;
  }

  // The status label is replaced while checking, so its original version span
  // no longer exists. Render the result directly into the persistent label.
  if (!manual && info.error === 'skipped_recent_check') return;

  if (info.available) {
    _pendingUpdate = info;
    statusEl.innerHTML =
      `RuneFetch ${info.current} — <strong>v${info.version} available</strong>`;
    markUpdateBadge(true);
    showUpdateModal(info);
    return;
  }

  markUpdateBadge(false);

  if (!manual) return;   // silent when it was the automatic startup check

  // Distinguish "no newer version" from "could not reach GitHub" — telling a
  // user they are up to date when the check actually failed is misleading.
  if (info.error === 'network') {
    statusEl.textContent = `RuneFetch ${info.current} — could not reach GitHub`;
    toast('Could not check for updates — you appear to be offline', 'warn');
  } else if (info.error === 'no_releases') {
    statusEl.textContent = `RuneFetch ${info.current} — no releases published yet`;
  } else if (info.error && info.error !== 'skipped_recent_check') {
    statusEl.textContent = `RuneFetch ${info.current} — check failed`;
    toast('Update check failed (' + info.error + ')', 'warn');
  } else {
    statusEl.textContent = `RuneFetch ${info.current} — up to date`;
    toast('You are on the latest version', 'info');
  }
}

function showUpdateModal(info) {
  $('update-version').textContent = `Version ${info.version}  ·  you have ${info.current}`;
  $('update-notes').textContent   = info.notes || '';
  $('update-progress').style.display = 'none';
  $('update-bar-fill').style.width   = '0%';
  $('btn-update-now').disabled   = false;
  $('btn-update-later').disabled = false;

  // No downloadable asset (or running from source) — send them to the page.
  $('btn-update-now').textContent = info.asset_url ? 'Update & restart' : 'Open download page';

  $('update-modal').showModal();
}

async function startUpdate() {
  if (!_pendingUpdate) return;

  if (!_pendingUpdate.asset_url) {
    ws.fire('open_releases_page');
    $('update-modal').close();
    return;
  }

  $('btn-update-now').disabled   = true;
  $('btn-update-later').disabled = true;
  $('update-progress').style.display = 'block';
  $('update-progress-text').textContent = 'Starting download…';

  try {
    await ws.send('install_update', {
      asset_url:  _pendingUpdate.asset_url,
      asset_size: _pendingUpdate.asset_size || 0,
    });
  } catch (err) {
    $('btn-update-now').disabled   = false;
    $('btn-update-later').disabled = false;
    $('update-progress').style.display = 'none';
    toast('Update failed: ' + err.message, 'error');
  }
}

/** Small dot on the Settings nav button so the update is discoverable. */
function markUpdateBadge(show) {
  const btn = document.querySelector('.nav-btn[data-view="settings"]');
  if (!btn) return;
  const existing = btn.querySelector('.update-dot');
  if (show && !existing) {
    const dot = document.createElement('span');
    dot.className = 'update-dot';
    btn.appendChild(dot);
  } else if (!show && existing) {
    existing.remove();
  }
}

// ── WS event handlers ─────────────────────────────────────────────────────────

function onConnected() {
  S.connected = true;
  $('status-dot').classList.add('active');
  $('status-text').textContent = 'Connected';
}

function onDisconnected() {
  S.connected = false;
  $('status-dot').classList.remove('active');
  $('status-text').textContent = 'Reconnecting…';
}

function onItemUpdate(item) {
  S.items.set(item.id, item);
  upsertCard(item);
  updateStatusBar();
  updateEmpty();
}

function onItemRemoved(data) {
  S.items.delete(data.id);
  const el = $('queue-list').querySelector(`[data-id="${data.id}"]`);
  if (el) el.remove();
  updateEmpty();
  updateStatusBar();
}

function onItemLog(data) {
  const card = $('queue-list').querySelector(`[data-id="${data.id}"]`);
  if (!card) return;
  const body = card.querySelector('.log-body');
  const toggle = card.querySelector('.log-toggle');
  if (!body) return;
  const line = document.createElement('div');
  line.className = 'log-line';
  line.style.color = data.colour || 'var(--text-muted)';
  line.textContent = data.text;
  body.appendChild(line);
  body.scrollTop = body.scrollHeight;
  if (toggle) toggle.style.display = '';
}

function onHistoryAdded(item) {
  S.history.unshift(item);
  if (S.view === 'history') {
    const list = $('history-list');
    list.prepend(buildHistCard(item));
    $('history-empty').style.display = 'none';
    $('history-count').textContent = `${S.history.length} item${S.history.length !== 1 ? 's' : ''}`;
  }
}

function onSettings(cfg) {
  S.settings = cfg;
  applyTheme(cfg.theme || 'dark');
  $('status-path').textContent = cfg.save_path || '';
  $('status-sep2').style.display = cfg.save_path ? '' : 'none';
  if (S.view === 'settings') renderSettings();
}

// ── Card rendering ────────────────────────────────────────────────────────────

const BADGE_CLS = {
  Queued:'badge-queued', Downloading:'badge-downloading',
  Complete:'badge-complete', Error:'badge-error',
  Paused:'badge-paused', Cancelled:'badge-cancelled',
};

function upsertCard(item) {
  const list = $('queue-list');
  let card = list.querySelector(`[data-id="${item.id}"]`);
  const isNew = !card;

  if (isNew) {
    card = document.createElement('div');
    card.className = 'card';
    card.dataset.id = item.id;
    list.prepend(card);
    card.addEventListener('click', onCardClick);
  }

  const st       = item.state || 'Queued';
  card.dataset.state = st;
  const badgeCls = BADGE_CLS[st] || 'badge-queued';
  const active   = st === 'Downloading';
  const paused   = st === 'Paused';
  const queued   = st === 'Queued';
  const done     = ['Complete','Error','Cancelled'].includes(st);
  const canPause  = active || paused;
  const canCancel = active || paused || queued;
  const pct = Math.min(100, Math.max(0, item.progress || 0));
  const sub = [item.source_label, item.quality, item.size].filter(Boolean).join('  ·  ');

  if (isNew) {
    // First render — build full innerHTML once
    const progressHtml = (!done || item.progress > 0) ? `
      <div class="progress-row">
        <div class="progress-track">
          <div class="progress-fill${active ? ' active' : ''}" style="width:${pct}%"></div>
        </div>
        <span class="progress-pct">${pct.toFixed(0)}%</span>
      </div>
      <div class="speed-row">
        <span class="spd">${esc(item.speed || '')}</span>
        <span class="eta-txt">${esc(item.eta || '')}</span>
        <span class="sz">${esc(item.size || '')}</span>
      </div>` : '';

    card.innerHTML = `
      <div class="card-header">
        <div class="card-icon">${uiIcon('file')}</div>
        <div class="card-meta">
          <div class="card-title" title="${esc(item.title || item.url || '')}">${esc(item.title || item.url || 'Loading…')}</div>
          <div class="card-sub">
            <span class="card-badge ${badgeCls}">${st}</span>
            <span class="card-sub-txt">${sub ? esc(sub) : ''}</span>
          </div>
          <div class="card-error" style="${st === 'Error' ? '' : 'display:none'}" title="${esc(item.error_msg || '')}">${esc(item.error_msg || '')}</div>
        </div>
        <div class="card-actions">
          <button class="icon-btn" data-action="${paused ? 'resume' : 'pause'}"
            title="${paused ? 'Resume' : 'Pause'}"
            aria-label="${paused ? 'Resume' : 'Pause'}" ${!canPause ? 'disabled' : ''}>${uiIcon(paused ? 'play' : 'pause')}</button>
          <button class="icon-btn danger" data-action="cancel"
            title="Cancel" aria-label="Cancel" ${!canCancel ? 'disabled' : ''}>${uiIcon('close')}</button>
          <button class="icon-btn" data-action="open_folder"
            title="Open save folder" aria-label="Open save folder" ${queued ? 'disabled' : ''}>${uiIcon('folder')}</button>
          <button class="icon-btn danger" data-action="remove" title="Remove" aria-label="Remove">${uiIcon('trash')}</button>
        </div>
      </div>
      ${progressHtml}
      <button class="log-toggle" style="display:none">▶ Show log</button>
      <div class="log-body"></div>`;
    return;
  }

  // Subsequent updates — targeted DOM mutations only, never touch log section
  const badge = card.querySelector('.card-badge');
  if (badge) { badge.className = `card-badge ${badgeCls}`; badge.textContent = st; }

  const titleEl = card.querySelector('.card-title');
  if (titleEl && item.title) {
    titleEl.textContent = item.title || item.url || '…';
    titleEl.title = item.title || item.url || '';
  }

  const subTxt = card.querySelector('.card-sub-txt');
  if (subTxt) subTxt.textContent = sub;

  const errEl = card.querySelector('.card-error');
  if (errEl) {
    errEl.style.display = st === 'Error' ? '' : 'none';
    errEl.textContent   = item.error_msg || '';
    errEl.title         = item.error_msg || '';
  }

  // Progress row — create if missing, remove if done
  let progRow = card.querySelector('.progress-row');
  if (done && !item.progress) {
    progRow?.remove();
    card.querySelector('.speed-row')?.remove();
  } else {
    if (!progRow) {
      const frag = document.createElement('div');
      frag.innerHTML = `
        <div class="progress-row">
          <div class="progress-track"><div class="progress-fill" style="width:0%"></div></div>
          <span class="progress-pct">0%</span>
        </div>
        <div class="speed-row">
          <span class="spd"></span><span class="eta-txt"></span><span class="sz"></span>
        </div>`;
      const toggle = card.querySelector('.log-toggle');
      card.insertBefore(frag.children[0], toggle);
      card.insertBefore(frag.children[0], toggle);
      progRow = card.querySelector('.progress-row');
    }
    const fill = progRow?.querySelector('.progress-fill');
    if (fill) {
      fill.style.width = `${pct}%`;
      fill.classList.toggle('active', active);
    }
    const pctEl = progRow?.querySelector('.progress-pct');
    if (pctEl) pctEl.textContent = `${pct.toFixed(0)}%`;
    const sr = card.querySelector('.speed-row');
    if (sr) {
      const spd = sr.querySelector('.spd');   if (spd)  spd.textContent  = item.speed || '';
      const eta = sr.querySelector('.eta-txt'); if (eta) eta.textContent = item.eta   || '';
      const sz  = sr.querySelector('.sz');    if (sz)   sz.textContent   = item.size  || '';
    }
  }

  // Button states
  const [btnPause, btnCancel, btnFolder] = card.querySelectorAll('[data-action]');
  if (btnPause) {
    btnPause.dataset.action = paused ? 'resume' : 'pause';
    btnPause.title          = paused ? 'Resume' : 'Pause';
    btnPause.innerHTML      = uiIcon(paused ? 'play' : 'pause');
    btnPause.setAttribute('aria-label', paused ? 'Resume' : 'Pause');
    btnPause.disabled       = !canPause;
  }
  if (btnCancel) btnCancel.disabled = !canCancel;
  if (btnFolder) btnFolder.disabled = !!queued;
}

function onCardClick(e) {
  const card   = e.currentTarget;
  const id     = card.dataset.id;
  const btn    = e.target.closest('[data-action]');
  const toggle = e.target.closest('.log-toggle');

  if (toggle) {
    const body = card.querySelector('.log-body');
    body.classList.toggle('open');
    toggle.textContent = body.classList.contains('open') ? '▼ Hide log' : '▶ Show log';
    return;
  }

  if (!btn) return;
  const action = btn.dataset.action;

  if (action === 'open_folder') {
    const item = S.items.get(id);
    if (item?.save_path) {
      ws.fire('open_folder', { path: item.save_path });
    }
    return;
  }

  ws.fire(action, { id });
}

function updateEmpty() {
  $('empty-state').style.display = S.items.size === 0 ? 'flex' : 'none';
}

// ── Status bar ────────────────────────────────────────────────────────────────

function updateStatusBar() {
  const items  = [...S.items.values()];
  const active = items.filter(i => i.state === 'Downloading');
  const queued = items.filter(i => i.state === 'Queued');
  const total  = items.length;
  const bps    = active.reduce((s, i) => s + (i.speed_bps || 0), 0);

  if (active.length) {
    $('status-text').textContent = `● ${active.length} downloading · ${queued.length} queued`;
  } else if (queued.length) {
    $('status-text').textContent = `● ${queued.length} queued`;
  } else {
    $('status-text').textContent = total ? `● ${total} item${total !== 1 ? 's' : ''}` : '● Ready';
  }

  $('status-speed').textContent = bps > 0 ? fmtBytes(bps) + '/s' : '';
  $('queue-count').textContent = total ? `${total} item${total !== 1 ? 's' : ''}` : '';
}

// ── Theme ─────────────────────────────────────────────────────────────────────

function applyTheme(name) {
  document.documentElement.dataset.theme = name === 'light' ? 'light' : '';
}

// ── Toasts ────────────────────────────────────────────────────────────────────

function toast(message, level = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${level}`;
  el.textContent = message;
  $('toast-container').appendChild(el);
  setTimeout(() => {
    el.classList.add('out');
    setTimeout(() => el.remove(), 220);
  }, 3500);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function pyApi(method, ...args) {
  try {
    if (window.pywebview?.api?.[method])
      window.pywebview.api[method](...args);
  } catch {}
}

function fmtBytes(b) {
  if (!b) return '';
  if (b >= 1_073_741_824) return (b / 1_073_741_824).toFixed(1) + ' GB';
  if (b >= 1_048_576)     return (b / 1_048_576).toFixed(1) + ' MB';
  if (b >= 1024)          return Math.round(b / 1024) + ' KB';
  return b + ' B';
}

function esc(s) {
  return String(s ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function heightOf(label) {
  const m = label.match(/(\d+)p/);
  if (m) return parseInt(m[1]);
  if (label.startsWith('4K')) return 2160;
  if (label.startsWith('2K')) return 1440;
  return 0;
}
