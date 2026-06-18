"""
Spotify downloader — uses spotdl to match Spotify tracks to YouTube
and download them as MP3 with full metadata + cover art.
"""

import logging
import os
import re
import subprocess
import sys

_log = logging.getLogger(__name__)

COL_NORMAL  = "#6b7280"
COL_OK      = "#2dd4a0"
COL_ERROR   = "#ff6b6b"
COL_INFO    = "#00d9ff"


def _ilog(item, text: str, colour: str = COL_NORMAL):
    item._log_lines.append((text, colour))


def download_spotify(item, progress_cb):
    save_dir = item.save_path
    try:
        os.makedirs(save_dir, exist_ok=True)
    except OSError as exc:
        _log.error("Cannot create save dir %r: %s", save_dir, exc)
        raise

    _log.info("Spotify start  url=%s", item.url[:80])
    progress_cb(3, "", "Fetching Spotify metadata…")
    _ilog(item, "Connecting to Spotify…", COL_INFO)

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
        _log.error("spotdl not found — is it installed?")
        raise Exception("spotdl is not installed.\nRun: pip install spotdl")
    except OSError as exc:
        _log.error("Failed to launch spotdl: %s", exc)
        raise Exception(f"Failed to launch spotdl: {exc}") from exc

    RE_TOTAL     = re.compile(r"Found\s+(\d+)\s+song", re.IGNORECASE)
    RE_PROGRESS  = re.compile(r"(\d+)/(\d+)")
    RE_DONE      = re.compile(r'(?:Downloaded|Saved)\s+"?([^"]+)"?', re.IGNORECASE)
    RE_SKIP      = re.compile(r'Skipping\s+"?([^"]+)"?', re.IGNORECASE)
    RE_FAIL      = re.compile(
        r"(?:Couldn'?t download|Failed to download|Error)\s+\"?([^\"]+)\"?",
        re.IGNORECASE,
    )
    RE_DLING     = re.compile(r'Downloading\s+"?([^"]+)"?', re.IGNORECASE)

    total_tracks  = 0
    done_tracks   = 0
    pct           = 5.0
    failed_tracks = []
    current_track = None

    try:
        for raw_line in proc.stdout:
            item.pause_event.wait()
            if item.cancel_event.is_set():
                try:
                    proc.terminate()
                except Exception:
                    pass
                _ilog(item, "⚠ Cancelled by user.", COL_ERROR)
                _log.info("Spotify download cancelled  url=%s", item.url[:60])
                return

            line = raw_line.strip()
            if not line:
                continue

            m = RE_TOTAL.search(line)
            if m:
                total_tracks = int(m.group(1))
                item.title = item.title.split("  (")[0] + f"  ({total_tracks} tracks)"
                _ilog(item, f"Found {total_tracks} track{'s' if total_tracks != 1 else ''}.", COL_INFO)
                progress_cb(5, "", f"Queuing {total_tracks} tracks…")
                continue

            m = RE_DLING.search(line)
            if m:
                current_track = m.group(1).strip()
                _ilog(item, f"  ↓  {current_track}", COL_NORMAL)
                continue

            m = RE_PROGRESS.search(line)
            if m:
                n_done  = int(m.group(1))
                n_total = int(m.group(2))
                if n_total > 1:
                    total_tracks = max(total_tracks, n_total)
                    done_tracks  = n_done
                    pct = 5 + (done_tracks / total_tracks * 90)
                    progress_cb(min(pct, 99.0), "", f"Track {done_tracks}/{total_tracks}")
                continue

            m = RE_DONE.search(line)
            if m:
                name = m.group(1).strip()
                done_tracks += 1
                pct = 5 + (done_tracks / total_tracks * 90) if total_tracks > 0 else min(pct + 10, 95)
                _ilog(item, f"  ✓  {name}", COL_OK)
                progress_cb(
                    min(pct, 99.0), "",
                    f"Track {done_tracks}" + (f"/{total_tracks}" if total_tracks else "")
                )
                current_track = None
                continue

            m = RE_SKIP.search(line)
            if m:
                name = m.group(1).strip()
                done_tracks += 1
                if total_tracks > 0:
                    pct = 5 + (done_tracks / total_tracks * 90)
                _ilog(item, f"  ↷  {name}  (already exists, skipped)", COL_NORMAL)
                progress_cb(
                    min(pct, 99.0), "",
                    f"Track {done_tracks}" + (f"/{total_tracks}" if total_tracks else "")
                )
                current_track = None
                continue

            m = RE_FAIL.search(line)
            if m:
                name = m.group(1).strip() or current_track or "Unknown track"
                failed_tracks.append((name, line))
                _ilog(item, f"  ✗  {name}", COL_ERROR)
                _ilog(item, f"     {line[:120]}", COL_ERROR)
                _log.warning("spotdl track failed: %s — %s", name, line[:120])
                current_track = None
                continue

            if len(line) > 3 and not line.startswith("━") and "%|" not in line:
                _ilog(item, f"     {line[:120]}", COL_NORMAL)

    except Exception as exc:
        _log.error("Error reading spotdl output: %s", exc)
        _ilog(item, f"⚠ Output read error: {exc}", COL_ERROR)

    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        _log.warning("spotdl process did not exit cleanly — terminating")
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception as exc:
            _log.error("Could not terminate spotdl: %s", exc)
    except Exception as exc:
        _log.error("Error waiting for spotdl: %s", exc)

    if failed_tracks:
        _ilog(item, "", COL_NORMAL)
        _ilog(item, f"── {len(failed_tracks)} track(s) failed ──", COL_ERROR)
        for name, reason in failed_tracks:
            _ilog(item, f"  ✗  {name}", COL_ERROR)
        item.error_msg = (
            f"{len(failed_tracks)} track(s) failed: "
            + ", ".join(n for n, _ in failed_tracks[:3])
            + ("…" if len(failed_tracks) > 3 else "")
        )

    ok_count = done_tracks
    if total_tracks > 0:
        _ilog(item, "", COL_NORMAL)
        _ilog(
            item,
            f"── Done: {ok_count}/{total_tracks} downloaded"
            + (f", {len(failed_tracks)} failed" if failed_tracks else ""),
            COL_OK if not failed_tracks else COL_ERROR,
        )

    rc = proc.returncode
    _log.info("spotdl exited  code=%s  url=%s", rc, item.url[:60])
    if rc not in (0, 1, None) and not item.cancel_event.is_set():
        raise Exception(f"spotdl exited with code {rc}")
