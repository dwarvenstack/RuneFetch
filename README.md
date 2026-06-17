# ⛩ RuneFetch
### by DwarvenStack

A production-grade, open-source Internet Download Manager built in Python + PyQt6.  
Download from YouTube, Spotify, 1 000+ sites, and any direct file URL — with a waveform
progress visualiser, concurrent queue management, browser extension capture, and full
pause/resume support.

---

## What's New (v2.0)

| Area | Change |
|---|---|
| **Browser Extension** | Chromium MV3 extension captures media links from any tab and sends them to the app via a local WebSocket bridge |
| **Segmented Downloads** | Direct file downloads use parallel Range-header connections for faster speeds |
| **Queue Persistence** | Queue is saved on close and restored on next launch — interrupted downloads resume automatically |
| **System Tray** | App stays alive in the system tray when the window is closed; full tray menu with live status |
| **Clipboard Monitor** | Automatically detects URLs copied to the clipboard and offers to download them |
| **Proxy Support** | Per-download proxy wired through all backends (yt-dlp, spotdl, direct HTTP) |
| **SHA-256 Verification** | ffmpeg auto-download is verified against the official release checksum before extraction |
| **Per-entry History Delete** | Right-click any history row to delete that single entry |
| **Accessibility** | All icon-only buttons carry `accessibleName` labels for screen readers |
| **Bug fixes** | `www.`-strip regex fix, large playlist stall fix, speed aggregation locale fix, silent exception logging |

---

## Features

| Feature | Details |
|---|---|
| **Waveform progress** | Animated sine-wave fill — four brand gradients per state |
| **Batch / playlist** | YouTube playlists, Spotify playlists/albums, channel pages — detected automatically |
| **Concurrent downloads** | Up to N simultaneous downloads (configurable in Settings) |
| **Pause / Resume** | Per-download pause blocks the worker thread without killing it |
| **Segmented HTTP** | Parallel byte-range connections; auto-falls back to single-stream if server doesn't support ranges |
| **Speed throttle** | Optional global KB/s cap (0 = unlimited) |
| **Download history** | Last 500 completed downloads; double-click to re-download; right-click to delete single entry |
| **Browser capture** | Floating chip on recognised media pages; toolbar popup for manual URL entry |
| **System tray** | Window close minimises to tray; right-click tray icon to quit |
| **Clipboard monitor** | Detects pasted URLs and pre-fills the download bar |
| **Queue persistence** | QUEUED/PAUSED items survive app restart |
| **DRM detection** | Netflix, Prime, Hotstar, Disney+, etc. blocked with a clear explanation |
| **Proxy support** | Per-download HTTP/HTTPS proxy; all backends obey it |
| **ffmpeg integrity** | SHA-256 sidecar verified before extracting the auto-downloaded ffmpeg bundle |

---

## Supported Sources

| Platform | What downloads |
|---|---|
| YouTube | Videos, audio, playlists, channel pages |
| Spotify | Tracks, albums, playlists (via spotdl + yt-dlp match) |
| Twitter / X | Videos, GIFs, images |
| Instagram | Public posts, Reels |
| TikTok | Videos |
| Vimeo | High-quality video |
| Twitch | VODs, clips |
| SoundCloud | Tracks, playlists |
| Reddit | Videos, images |
| Pinterest | Images, videos |
| Dailymotion, Bilibili, Rumble, Odysee… | Via yt-dlp (1 000+ extractors) |
| Direct URL | Images, video, audio, documents, archives |
| HLS / DASH streams | `.m3u8` and `.mpd` links |
| **Netflix / Prime / Hotstar / Disney+** | ⛔ DRM — cannot be downloaded |

---

## Quick Start

### 1 — Prerequisites

| Tool | Minimum | Install |
|---|---|---|
| Python | 3.10+ | https://python.org (3.11 or 3.12 recommended) |
| ffmpeg | any | RuneFetch auto-downloads ffmpeg on first launch, **or** install manually (see below) |

Manual ffmpeg install (optional):

```bash
# Windows
winget install Gyan.FFmpeg

# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg
```

### 2 — Install

```bash
# Windows — one-click
setup.bat

# macOS / Linux
pip install -r requirements.txt
```

### 3 — Run

```bash
python main.py
```

---

## Browser Extension Setup

The browser extension lets you capture downloadable media from any tab and send it to RuneFetch with one click.

### Step 1 — Get your token

1. Open RuneFetch and go to **Settings → Browser Extension**.
2. Copy the token shown (it is auto-generated on first launch).

### Step 2 — Load the extension in Chrome / Edge / Brave

1. Open `chrome://extensions` (or `edge://extensions`).
2. Enable **Developer mode** (toggle, top-right).
3. Click **Load unpacked** and select the `browser_extension/` folder inside the RuneFetch project directory.
4. The ⛩ RuneFetch icon appears in the toolbar.

### Step 3 — Pair the extension

1. Click the ⛩ toolbar icon.
2. Paste the token from Step 1 into the **Token pairing** field and click **Save**.
3. The status dot turns green — the extension is now connected.

### How it works

- **Floating chip**: On recognised media sites (YouTube, Spotify, Twitter, etc.) a small capture chip appears in the corner. Click **↓ Download** to send the URL to RuneFetch.
- **Manual send**: Paste any URL into the popup and click **Send**.
- **Scan page**: Click **Scan current tab** in the popup to force-detect links on the current page.
- **Download interception**: Any file the browser tries to download natively is offered to RuneFetch automatically.
- **Chip toggle**: Disable the floating chip globally from the popup without disconnecting the bridge.
- **Per-site suppression**: Click *Don't show on this site* in the chip to silence it on that domain.

> The bridge listens only on `127.0.0.1` — it is never reachable from the network. Private and loopback URLs are blocked before dispatch.

---

## Project Structure

```
RuneFetch/
├── main.py                         Entry point
├── requirements.txt
├── setup.bat                       Windows one-click setup
├── build_exe.bat                   Build Windows EXE with PyInstaller
├── build_exe.sh                    Build Linux / macOS binary
├── RuneFetch.spec                  PyInstaller spec
│
├── core/
│   ├── detector.py                 URL classifier (DRM, YouTube, Spotify, direct…)
│   ├── queue_manager.py            Thread-safe download queue + pause/resume
│   ├── bridge.py                   Local WebSocket bridge (127.0.0.1 only)
│   └── queue_persistence.py        Save/restore queue across restarts
│
├── downloaders/
│   ├── router.py                   Dispatches items to the right backend
│   ├── ytdlp_downloader.py         YouTube + 1 000 sites via yt-dlp
│   ├── spotdl_downloader.py        Spotify via spotdl
│   ├── direct_downloader.py        Single-stream HTTP with resume + throttle
│   └── segmented_downloader.py     Multi-connection HTTP via Range headers
│
├── gui/
│   ├── main_window.py              Main window, layout, nav, tray, clipboard, poll loop
│   ├── download_card.py            Per-item card widget
│   ├── waveform.py                 Animated waveform progress widget
│   ├── settings_panel.py           Preferences UI (including bridge token display)
│   ├── history_panel.py            Download history with per-entry delete
│   ├── stylesheet.py               Global QSS stylesheet
│   └── theme.py                    Design tokens (colours, gradients, sizes)
│
├── utils/
│   └── settings.py                 JSON config read/write (~/.runefetch/config.json)
│
└── browser_extension/
    ├── manifest.json               Chromium MV3 manifest
    ├── background.js               Service worker — WebSocket client + download interception
    ├── content.js                  Capture chip injected into pages
    ├── popup.html / popup.js       Toolbar popup UI
    ├── styles.css                  Chip and popup styling
    └── icons/                      Extension icons (16 / 48 / 128 px)
```

---

## Configuration

Settings are stored at `~/.runefetch/config.json`.  
Queue state is stored at `~/.runefetch/queue_state.json` (auto-managed).  
All preferences are exposed in the **Settings** panel in the app.

| Key | Default | Description |
|---|---|---|
| `save_path` | `~/Downloads/RuneFetch` | Default download folder |
| `prompt_per_file` | `false` | Ask for folder on each download |
| `max_concurrent` | `2` | Simultaneous downloads |
| `throttle_kbps` | `0` | Speed cap (0 = unlimited) |
| `segments` | `8` | Parallel range connections per direct download |
| `fragment_threads` | `4` | yt-dlp fragment threads |
| `keep_history` | `true` | Log completed downloads |
| `bridge_port` | `8765` | Local WebSocket bridge port |
| `bridge_token` | *(auto)* | Shared secret for browser extension auth |
| `clipboard_monitor` | `false` | Auto-detect URLs copied to clipboard |
| `close_to_tray` | `true` | Closing the window hides to tray instead of quitting |

---

## Colour System

| Gradient | Use |
|---|---|
| Cyan → Blue `#00d9ff → #0099ff` | Active / downloading state |
| Purple → Cyan `#9d4edd → #00d9ff` | Queued state |
| Orange → Red `#ff9f43 → #ff6b6b` | Error state |
| Pink → Orange `#ff6b9d → #ff9f43` | Accent UI elements |
| Green `#2dd4a0` | Complete state |

---

## Building a Standalone EXE

```bash
# Windows
build_exe.bat

# macOS / Linux
chmod +x build_exe.sh && ./build_exe.sh
```

Output lands in `dist/RuneFetch` (or `dist/RuneFetch.exe` on Windows).  
ffmpeg is **not** bundled — users need it on PATH or will be prompted to auto-download it on first launch.

---

## Open-Source Licences

| Dependency | Licence |
|---|---|
| PyQt6 | GPL v3 |
| yt-dlp | Unlicense |
| spotdl | GPL v3 |
| requests | Apache 2.0 |
| websockets | BSD 2-Clause |
| Pillow | HPND |
| mutagen | GPL v2 |
| beautifulsoup4 | MIT |

RuneFetch itself is released under the **MIT Licence**.

---

## Links

**DwarvenStack** — https://github.com/dwarvenstack

> For more free apps like this, visit DwarvenStack on GitHub.
