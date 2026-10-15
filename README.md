# RuneFetch
### by DwarvenStack

A production-grade, open-source download manager built in Python + pywebview.  
Download from YouTube, Spotify, 1000+ sites, and any direct file URL — with a browser extension that captures media links from any tab.

---

## Requirements

| Tool | Minimum |
|---|---|
| Python | 3.10+ (3.12 recommended) |
| ffmpeg | Any — auto-downloaded on first launch if missing |

---

## Setup

```bash
pip install -r requirements.txt
python app.py
```

On first launch RuneFetch checks for ffmpeg. If missing, it offers to auto-download it to `~/.runefetch/bin/`.

---

## Project Structure

```
RuneFetch/
├── app.py                          Entry point
├── requirements.txt
│
├── core/
│   ├── detector.py                 URL classifier (YouTube, Spotify, direct, DRM…)
│   ├── engine.py                   Download engine
│   ├── queue_manager.py            Thread-safe queue + pause/resume
│   ├── bridge.py                   Local WebSocket bridge (127.0.0.1 only)
│   ├── ui_server.py                Internal HTTP server for webui
│   ├── queue_persistence.py        Save/restore queue across restarts
│   └── first_run.py                ffmpeg check + auto-download on first launch
│
├── downloaders/
│   ├── router.py                   Dispatches to the right backend
│   ├── ytdlp_downloader.py         YouTube + 1000+ sites via yt-dlp
│   ├── spotdl_downloader.py        Spotify via spotdl
│   ├── direct_downloader.py        Single-stream HTTP with resume
│   └── segmented_downloader.py     Multi-connection HTTP via Range headers
│
├── webui/                          Frontend (HTML/CSS/JS served via pywebview)
│   ├── index.html
│   └── js/app.js
│
├── utils/
│   ├── settings.py                 JSON config (~/.runefetch/config.json)
│   └── net_guard.py                Blocks private/loopback URLs from dispatch
│
└── browser_extension/              Chrome/Edge/Brave extension (load unpacked)
    ├── manifest.json
    ├── background.js
    ├── content.js
    ├── popup.html / popup.js
    └── icons/
```

---

## Browser Extension Setup

### Step 1 — Get your token

1. Open RuneFetch → **Settings → Browser Extension**
2. Copy the token shown

### Step 2 — Load in Chrome / Edge / Brave

1. Go to `chrome://extensions`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked** → select the `browser_extension/` folder
4. The RuneFetch icon appears in the toolbar

### Step 3 — Pair

1. Click the toolbar icon
2. Paste your token → **Save**
3. Status dot turns green — connected

---

## Supported Sources

| Platform | What downloads |
|---|---|
| YouTube | Videos, audio, playlists |
| Spotify | Tracks, albums, playlists (via spotdl) |
| Twitter / X | Videos, GIFs, images |
| Instagram | Public posts, Reels |
| TikTok | Videos |
| Vimeo, Twitch, SoundCloud, Reddit… | Via yt-dlp (1000+ extractors) |
| Direct URL | Any file, HLS/DASH streams |
| Netflix / Prime / Disney+ | DRM — not supported |

---

## Configuration

Stored at `~/.runefetch/config.json`. All options exposed in the Settings panel.

| Key | Default | Description |
|---|---|---|
| `save_path` | `~/Downloads/RuneFetch` | Download folder |
| `max_concurrent` | `2` | Simultaneous downloads |
| `throttle_kbps` | `0` | Speed cap (0 = unlimited) |
| `segments` | `8` | Parallel connections for direct downloads |
| `bridge_port` | `8765` | WebSocket bridge port |
| `bridge_token` | *(auto)* | Shared secret for browser extension |

---

## Windows release builds

Install Inno Setup 6, run `./setup.ps1`, then install the build tool with
`.\.venv\Scripts\python.exe -m pip install pyinstaller`.
Run `./packaging/build.ps1` to validate the project and build the version in
`VERSION`. The installer and its SHA-256 checksum are written to `dist_installer/`.
The installer upgrades an existing per-user installation using the same AppId.
The browser extension is included in the installation's `browser_extension/` folder.

For automatic update detection, publish a GitHub release with a version greater
than the installed app's version and attach the `RuneFetch-Setup-X.Y.Z.exe` asset.
Changing the file on an older release does not trigger a version update.

## Licence

MIT — see [LICENSE](LICENSE)

**DwarvenStack** — https://github.com/dwarvenstack
