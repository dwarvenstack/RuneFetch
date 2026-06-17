# ⛩ RuneFetch
### by DwarvenStack

A production-grade, open-source Internet Download Manager built in Python + PyQt6.
Download from YouTube, Spotify, 1 000+ sites, and any direct file URL — with a
waveform progress visualiser, concurrent queue management, and full pause/resume support.

---

## Features

| Feature | Details |
|---|---|
| **Waveform progress** | Animated sine-wave fill — one of four brand gradients per state |
| **Batch / playlist** | YouTube playlists, Spotify playlists/albums, channel pages — detected automatically |
| **Concurrent downloads** | Up to N simultaneous downloads (configurable in Settings) |
| **Pause / Resume** | Per-download pause that blocks the worker thread without killing it |
| **Resume interrupted** | Direct file downloads send a `Range` header to skip already-downloaded bytes |
| **Speed throttle** | Optional global KB/s cap (0 = unlimited) |
| **Download history** | Last 500 completed downloads, searchable, one-click re-download |
| **Settings panel** | Default path, per-file prompt, concurrency, throttle, proxy |
| **DRM detection** | Netflix, Prime, Hotstar, Disney+, etc. blocked with a clear explanation |

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
| Direct URL | Images, video, audio, documents, archives, executables |
| HLS / DASH streams | `.m3u8` and `.mpd` links |
| **Netflix / Prime / Hotstar / Disney+** | ⛔ DRM — cannot be downloaded |

---

## Quick Start

### 1 — Prerequisites

| Tool | Install |
|---|---|
| Python 3.10+ | https://python.org |
| ffmpeg | `winget install Gyan.FFmpeg` · `brew install ffmpeg` · `sudo apt install ffmpeg` |

### 2 — Install dependencies

```bash
# Windows
setup.bat

# macOS / Linux
pip install -r requirements.txt
```

### 3 — Run

```bash
python main.py
```

---

## Project Structure

```
RuneFetch/
├── main.py                        Entry point
├── requirements.txt
├── setup.bat                      Windows one-click setup
│
├── core/
│   ├── detector.py                URL classifier (DRM, YouTube, Spotify, direct…)
│   └── queue_manager.py           Thread-safe download queue + pause/resume
│
├── downloaders/
│   ├── router.py                  Dispatches items to the right backend
│   ├── ytdlp_downloader.py        YouTube + 1 000 sites via yt-dlp
│   ├── spotdl_downloader.py       Spotify via spotdl
│   └── direct_downloader.py       Plain HTTP with resume + throttle
│
├── gui/
│   ├── main_window.py             Main window, layout, nav, poll loop
│   ├── download_card.py           Per-item card widget
│   ├── waveform.py                Animated waveform progress widget
│   ├── settings_panel.py          Preferences UI
│   ├── history_panel.py           Download history log
│   ├── stylesheet.py              Global QSS stylesheet
│   └── theme.py                   Design tokens (colours, gradients, sizes)
│
└── utils/
    └── settings.py                JSON config read/write (~/.runefetch/config.json)
```

---

## Colour System

| Gradient | Use |
|---|---|
| Cyan → Blue `#00d9ff → #0099ff` | Active / downloading state |
| Purple → Cyan `#9d4edd → #00d9ff` | Queued state |
| Orange → Red `#ff9f43 → #ff6b6b` | Error state |
| Pink → Orange `#ff6b9d → #ff9f43` | Used in accent UI elements |
| Green `#2dd4a0` | Complete state |

---

## Configuration

Settings are stored at `~/.runefetch/config.json`.
All preferences are exposed in the **Settings** panel in the app.

Key settings:

| Key | Default | Description |
|---|---|---|
| `save_path` | `~/Downloads/RuneFetch` | Default download folder |
| `prompt_per_file` | `false` | Ask for folder on each download |
| `max_concurrent` | `2` | Simultaneous downloads |
| `throttle_kbps` | `0` | Speed cap (0 = unlimited) |
| `fragment_threads` | `4` | Parallel fragment fetchers per download |
| `keep_history` | `true` | Log completed downloads |

---

## Open-Source Licences

| Dependency | Licence |
|---|---|
| PyQt6 | GPL v3 |
| yt-dlp | Unlicense |
| spotdl | GPL v3 |
| requests | Apache 2.0 |
| Pillow | HPND |
| mutagen | GPL v2 |

RuneFetch itself is released under the **MIT Licence**.

---

## Links

🔗 **DwarvenStack** — https://github.com/dwarvenstack

> For more free apps like this, visit DwarvenStack on GitHub.
