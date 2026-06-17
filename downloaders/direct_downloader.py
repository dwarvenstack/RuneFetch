"""
Direct downloader — handles plain file URLs.

Enhancements over the prototype
─────────────────────────────────
• Resume support: if a partial .part file exists, sends Range header
• Honours item.pause_event for pause/resume
• Respects throttle_kbps from item
• Correct filename from Content-Disposition (RFC 5987 / UTF-8 encoded)
"""

import os
import re
import time
import requests
from urllib.parse import urlparse, unquote

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

CHUNK = 65_536   # 64 KB


def download_direct(item, progress_cb):
    save_dir = item.save_path
    os.makedirs(save_dir, exist_ok=True)

    progress_cb(2, "", "Connecting…")

    proxy = getattr(item, "proxy", "") or ""
    proxies = {"http": proxy, "https": proxy} if proxy else None

    # Determine filename from a HEAD request first (cheap)
    try:
        head = requests.head(item.url, headers=HEADERS, allow_redirects=True,
                             timeout=10, proxies=proxies)
        filename = _get_filename(item.url, head.headers)
    except Exception:
        filename = "download.bin"

    dest      = _unique_path(save_dir, filename)
    part_file = dest + ".part"

    # Resume: check if a partial download exists
    resume_pos = 0
    req_headers = dict(HEADERS)
    if os.path.exists(part_file):
        resume_pos = os.path.getsize(part_file)
        if resume_pos > 0:
            req_headers["Range"] = f"bytes={resume_pos}-"
            progress_cb(1, "", f"Resuming from {_fmt_bytes(resume_pos)}…")

    # Speed throttle
    throttle_kbps = getattr(item, "throttle_kbps", 0)
    min_chunk_time = (CHUNK / (throttle_kbps * 1024)) if throttle_kbps > 0 else 0

    with requests.get(item.url, headers=req_headers, stream=True, timeout=30,
                      proxies=proxies) as r:
        # 416 = Range Not Satisfiable → server doesn't support resume, restart
        if r.status_code == 416:
            resume_pos = 0
            req_headers.pop("Range", None)
            r = requests.get(item.url, headers=req_headers, stream=True, timeout=30)
        r.raise_for_status()

        # Accept-Ranges check
        total = int(r.headers.get("Content-Length", 0))
        if resume_pos and total:
            total += resume_pos   # Content-Length is the *remaining* bytes

        if total:
            item.size = _fmt_bytes(total)

        downloaded = resume_pos
        t0 = time.monotonic()
        last_t = t0

        mode = "ab" if resume_pos > 0 else "wb"
        with open(part_file, mode) as f:
            for chunk in r.iter_content(chunk_size=CHUNK):
                # Pause support
                item.pause_event.wait()

                if item.cancel_event.is_set():
                    return   # leave .part file for future resume

                chunk_start = time.monotonic()
                f.write(chunk)
                downloaded += len(chunk)

                now = time.monotonic()
                if now - last_t >= 0.25:
                    elapsed = now - t0
                    speed = downloaded / elapsed if elapsed > 0 else 0
                    pct   = (downloaded / total * 100) if total else 0
                    eta   = _eta(downloaded, total, speed) if total else ""
                    progress_cb(min(pct, 99.9), _fmt_speed(speed), eta,
                                _fmt_bytes(total), speed_bps=speed)
                    last_t = now

                # Throttle: sleep if we wrote too fast
                if min_chunk_time > 0:
                    elapsed_chunk = time.monotonic() - chunk_start
                    sleep_for = min_chunk_time - elapsed_chunk
                    if sleep_for > 0:
                        time.sleep(sleep_for)

    # Rename .part → final filename
    if os.path.exists(part_file):
        os.replace(part_file, dest)

    item.title = os.path.basename(dest)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_filename(url: str, headers) -> str:
    cd = headers.get("Content-Disposition", "")
    if cd:
        # RFC 5987: filename*=UTF-8''encoded-name
        m = re.search(
            r"filename\*\s*=\s*[Uu][Tt][Ff]-8''([^;\r\n]+)", cd
        )
        if m:
            return unquote(m.group(1).strip().strip('"'))
        # Plain filename=
        m = re.search(r'filename\s*=\s*["\']?([^"\';\r\n]+)', cd,
                      re.IGNORECASE)
        if m:
            return unquote(m.group(1).strip().strip('"'))

    path = urlparse(url).path
    name = os.path.basename(unquote(path))
    if name and "." in name:
        return name

    ct = headers.get("Content-Type", "")
    ext_map = {
        "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
        "image/webp": ".webp", "video/mp4": ".mp4", "audio/mpeg": ".mp3",
        "application/pdf": ".pdf", "application/zip": ".zip",
        "application/octet-stream": ".bin",
    }
    ext = ext_map.get(ct.split(";")[0].strip(), ".bin")
    return f"download{ext}"


def _unique_path(directory: str, filename: str) -> str:
    base, ext = os.path.splitext(filename)
    dest = os.path.join(directory, filename)
    counter = 1
    while os.path.exists(dest) or os.path.exists(dest + ".part"):
        dest = os.path.join(directory, f"{base} ({counter}){ext}")
        counter += 1
    return dest


def _fmt_speed(bps: float) -> str:
    if bps >= 1_048_576:
        return f"{bps/1_048_576:.1f} MB/s"
    if bps >= 1024:
        return f"{bps/1024:.0f} KB/s"
    return f"{bps:.0f} B/s"


def _fmt_bytes(b: int) -> str:
    if not b:
        return ""
    if b >= 1_073_741_824:
        return f"{b/1_073_741_824:.1f} GB"
    if b >= 1_048_576:
        return f"{b/1_048_576:.1f} MB"
    if b >= 1024:
        return f"{b/1024:.0f} KB"
    return f"{b} B"


def _eta(downloaded: int, total: int, speed: float) -> str:
    if not speed or not total:
        return ""
    remaining = (total - downloaded) / speed
    if remaining < 60:
        return f"~{remaining:.0f}s"
    return f"~{remaining/60:.0f}m"
