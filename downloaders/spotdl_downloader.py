"""
Spotify downloader — uses spotdl to match Spotify tracks to YouTube
and download them as MP3 with full metadata + cover art.

This version adds:
  • Full per-track log: "Downloading <name>…", "✓ Done: <name>", "✗ Error: <name> — <reason>"
  • Failed tracks are collected and appended as a summary at the end
  • item._log_lines is used to pipe logs to the card's LogPanel in the GUI
  • Robust spotdl output parsing handles multiple output formats
"""

import os
import re
import subprocess
import sys


# ── Log helpers ──────────────────────────────────────────────────────────────

COL_NORMAL  = "#6b7280"   # grey
COL_OK      = "#2dd4a0"   # green
COL_ERROR   = "#ff6b6b"   # red
COL_INFO    = "#00d9ff"   # cyan

def _log(item, text: str, colour: str = COL_NORMAL):
    """Append a (text, colour) tuple to item._log_lines for GUI pickup."""
    item._log_lines.append((text, colour))


# ── Main downloader ──────────────────────────────────────────────────────────

def download_spotify(item, progress_cb):
    save_dir = item.save_path
    os.makedirs(save_dir, exist_ok=True)

    progress_cb(3, "", "Fetching Spotify metadata…")
    _log(item, "Connecting to Spotify…", COL_INFO)

    proxy = getattr(item, "proxy", "") or ""

    cmd = [
        sys.executable, "-m", "spotdl",
        "--output",  os.path.join(save_dir, "{title} - {artists}.{output-ext}"),
        "--format",  "mp3",
        "--bitrate", "320k",
        "--threads", "4",
    ]
    if proxy:
        cmd += ["--proxy", proxy]
    cmd.append(item.url)

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        raise Exception(
            "spotdl is not installed.\n"
            "Run: pip install spotdl"
        )

    # ── Regex patterns ────────────────────────────────────────────────────
    RE_TOTAL     = re.compile(r"Found\s+(\d+)\s+song", re.IGNORECASE)
    RE_PROGRESS  = re.compile(r"(\d+)/(\d+)")
    # spotdl outputs lines like:
    #   Downloaded "Artist - Title"
    #   Skipping "Artist - Title" (already exists)
    #   Couldn't download "Artist - Title"  /  Failed to download ...
    RE_DONE      = re.compile(r'(?:Downloaded|Saved)\s+"?([^"]+)"?', re.IGNORECASE)
    RE_SKIP      = re.compile(r'Skipping\s+"?([^"]+)"?', re.IGNORECASE)
    RE_FAIL      = re.compile(
        r"(?:Couldn'?t download|Failed to download|Error)\s+\"?([^\"]+)\"?",
        re.IGNORECASE,
    )
    # "Downloading Artist - Title" (progress line)
    RE_DLING     = re.compile(r'Downloading\s+"?([^"]+)"?', re.IGNORECASE)

    total_tracks  = 0
    done_tracks   = 0
    pct           = 5.0
    failed_tracks = []    # [(name, reason)]
    current_track = None  # track name being attempted right now

    for raw_line in proc.stdout:
        # Honour pause / cancel
        item.pause_event.wait()
        if item.cancel_event.is_set():
            proc.terminate()
            _log(item, "⚠ Cancelled by user.", COL_ERROR)
            return

        line = raw_line.strip()
        if not line:
            continue

        # ── Track total count ──────────────────────────────────────────
        m = RE_TOTAL.search(line)
        if m:
            total_tracks = int(m.group(1))
            item.title = item.title.split("  (")[0] + f"  ({total_tracks} tracks)"
            _log(item, f"Found {total_tracks} track{'s' if total_tracks != 1 else ''}.", COL_INFO)
            progress_cb(5, "", f"Queuing {total_tracks} tracks…")
            continue

        # ── "Downloading <track>" — note which track we're on ─────────
        m = RE_DLING.search(line)
        if m:
            current_track = m.group(1).strip()
            _log(item, f"  ↓  {current_track}", COL_NORMAL)
            continue

        # ── n/n progress marker ────────────────────────────────────────
        m = RE_PROGRESS.search(line)
        if m:
            n_done  = int(m.group(1))
            n_total = int(m.group(2))
            if n_total > 1:     # avoid false positives on years/bitrates
                total_tracks = max(total_tracks, n_total)
                done_tracks  = n_done
                pct = 5 + (done_tracks / total_tracks * 90)
                progress_cb(
                    min(pct, 99.0), "",
                    f"Track {done_tracks}/{total_tracks}"
                )
            continue

        # ── Successfully downloaded ────────────────────────────────────
        m = RE_DONE.search(line)
        if m:
            name = m.group(1).strip()
            done_tracks += 1
            if total_tracks > 0:
                pct = 5 + (done_tracks / total_tracks * 90)
            else:
                pct = min(pct + 10, 95)
            _log(item, f"  ✓  {name}", COL_OK)
            progress_cb(
                min(pct, 99.0), "",
                f"Track {done_tracks}" + (f"/{total_tracks}" if total_tracks else "")
            )
            current_track = None
            continue

        # ── Skipped (already exists) ───────────────────────────────────
        m = RE_SKIP.search(line)
        if m:
            name = m.group(1).strip()
            done_tracks += 1
            if total_tracks > 0:
                pct = 5 + (done_tracks / total_tracks * 90)
            _log(item, f"  ↷  {name}  (already exists, skipped)", COL_NORMAL)
            progress_cb(
                min(pct, 99.0), "",
                f"Track {done_tracks}" + (f"/{total_tracks}" if total_tracks else "")
            )
            current_track = None
            continue

        # ── Failed to download ─────────────────────────────────────────
        m = RE_FAIL.search(line)
        if m:
            name = m.group(1).strip() or current_track or "Unknown track"
            reason = line
            failed_tracks.append((name, reason))
            _log(item, f"  ✗  {name}", COL_ERROR)
            _log(item, f"     {reason[:120]}", COL_ERROR)
            current_track = None
            continue

        # ── Any other line — pass through as grey info ─────────────────
        # Filter out noisy lines (progress bars, blank separators)
        if len(line) > 3 and not line.startswith("━") and "%|" not in line:
            _log(item, f"     {line[:120]}", COL_NORMAL)

    proc.wait()

    # ── Final summary ─────────────────────────────────────────────────────
    if failed_tracks:
        _log(item, f"", COL_NORMAL)
        _log(item, f"── {len(failed_tracks)} track(s) failed ──", COL_ERROR)
        for name, reason in failed_tracks:
            _log(item, f"  ✗  {name}", COL_ERROR)
        # Append summary to error_msg for history recording
        item.error_msg = (
            f"{len(failed_tracks)} track(s) failed: "
            + ", ".join(n for n, _ in failed_tracks[:3])
            + ("…" if len(failed_tracks) > 3 else "")
        )

    ok_count = done_tracks
    if total_tracks > 0:
        _log(item, f"", COL_NORMAL)
        _log(
            item,
            f"── Done: {ok_count}/{total_tracks} downloaded"
            + (f", {len(failed_tracks)} failed" if failed_tracks else ""),
            COL_OK if not failed_tracks else COL_ERROR,
        )

    if proc.returncode not in (0, 1) and not item.cancel_event.is_set():
        raise Exception(f"spotdl exited with code {proc.returncode}")
