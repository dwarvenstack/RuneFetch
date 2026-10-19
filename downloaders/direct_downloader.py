"""
Direct downloader — handles plain file URLs.

• Resume support: if a partial .part file exists, sends Range header
• Honours item.pause_event for pause/resume
• Respects throttle_kbps from item
• Correct filename from Content-Disposition (RFC 5987 / UTF-8 encoded)
"""

import logging
import os
import re
import time
from contextlib import ExitStack
from urllib.parse import urlparse, unquote

import requests

from utils import net_guard

_log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Encoding": "identity",
}

CHUNK = 65_536   # 64 KB


def download_direct(item, progress_cb):
    _log.info("Direct start  url=%s", item.url[:80])
    save_dir = item.save_path
    try:
        os.makedirs(save_dir, exist_ok=True)
    except OSError as exc:
        _log.error("Cannot create save dir %r: %s", save_dir, exc)
        raise

    progress_cb(2, "", "Connecting…")

    proxy = getattr(item, "proxy", "") or ""
    proxies = {"http": proxy, "https": proxy} if proxy else None

    # HEAD request — determine filename (best effort)
    try:
        head = net_guard.safe_request("HEAD", item.url, headers=HEADERS,
                                      allow_redirects=True, timeout=10, proxies=proxies)
        filename = _get_filename(item.url, head.headers)
        _log.debug("HEAD ok  status=%s  filename=%r", head.status_code, filename)
        head.close()
    except net_guard.BlockedAddressError as exc:
        _log.warning("Direct download blocked by net guard: %s", exc)
        raise Exception(
            "⛔ Download blocked: the URL resolves to a private/local address."
        ) from exc
    except Exception as exc:
        _log.warning("HEAD request failed (%s) — using 'download.bin'", exc)
        filename = "download.bin"

    base_dest = _contain(save_dir, os.path.join(save_dir, filename))
    resume_matches = False
    try:
        with open(base_dest + '.part.url', encoding='utf-8') as metadata:
            resume_matches = metadata.read() == item.url and not os.path.exists(base_dest)
    except OSError:
        pass
    dest = base_dest if resume_matches else _contain(save_dir, _unique_path(save_dir, filename))
    part_file = dest + ".part"
    metadata_file = part_file + '.url'
    with open(metadata_file, 'w', encoding='utf-8') as metadata:
        metadata.write(item.url)

    # Resume: check if a partial download exists
    resume_pos = 0
    req_headers = dict(HEADERS)
    if os.path.exists(part_file):
        try:
            resume_pos = os.path.getsize(part_file)
        except OSError as exc:
            _log.warning("Could not stat part file (%s) — starting fresh", exc)
            resume_pos = 0
        if resume_pos > 0:
            req_headers["Range"] = f"bytes={resume_pos}-"
            _log.info("Resuming from %s", _fmt_bytes(resume_pos))
            progress_cb(1, "", f"Resuming from {_fmt_bytes(resume_pos)}…")

    # Speed throttle
    throttle_kbps = getattr(item, "throttle_kbps", 0)
    min_chunk_time = (CHUNK / (throttle_kbps * 1024)) if throttle_kbps and throttle_kbps > 0 else 0

    try:
        with ExitStack() as responses:
            r = responses.enter_context(net_guard.safe_request(
                "GET", item.url, headers=req_headers, stream=True, timeout=30, proxies=proxies))
            # 416 = Range Not Satisfiable → server doesn't support resume, restart
            if r.status_code == 416:
                _log.info("Server returned 416 — restarting without Range header")
                resume_pos = 0
                req_headers.pop("Range", None)
                r = responses.enter_context(net_guard.safe_request(
                    "GET", item.url, headers=req_headers, stream=True, timeout=30, proxies=proxies))
            r.raise_for_status()

            encoded = r.headers.get('Content-Encoding', '').lower() not in ('', 'identity')
            if resume_pos and encoded:
                req_headers.pop('Range', None)
                resume_pos = 0
                r = responses.enter_context(net_guard.safe_request(
                    "GET", item.url, headers=req_headers, stream=True, timeout=30, proxies=proxies))
                r.raise_for_status()
                encoded = r.headers.get('Content-Encoding', '').lower() not in ('', 'identity')

            if resume_pos and r.status_code == 200:
                resume_pos = 0  # Server ignored Range: overwrite rather than append.
            if resume_pos and not r.headers.get('Content-Range', '').startswith(f'bytes {resume_pos}-'):
                raise RuntimeError('Server returned an invalid resume range')

            # requests yields decoded bytes; Content-Length measures wire bytes.
            total = 0 if encoded else int(r.headers.get("Content-Length", 0))
            if resume_pos and total:
                total += resume_pos

            if total:
                item.size = _fmt_bytes(total)

            downloaded = resume_pos
            t0 = time.monotonic()
            last_t = t0

            mode = "ab" if resume_pos > 0 else "wb"
            try:
                with open(part_file, mode) as f:
                    for chunk in r.iter_content(chunk_size=CHUNK):
                        item.pause_event.wait()

                        if item.cancel_event.is_set():
                            _log.info("Direct download cancelled  file=%s", filename)
                            return

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

                        if min_chunk_time > 0:
                            elapsed_chunk = time.monotonic() - chunk_start
                            sleep_for = min_chunk_time - elapsed_chunk
                            if sleep_for > 0:
                                time.sleep(sleep_for)

            except OSError as exc:
                _log.error("Write error during download of %r: %s", filename, exc)
                raise Exception(f"Disk write failed: {exc}") from exc

            if total and downloaded != total:
                raise RuntimeError(f'Incomplete download: expected {total} bytes, received {downloaded}')

    except requests.RequestException as exc:
        _log.error("Network error downloading %s: %s", item.url[:80], exc)
        raise Exception(f"Network error: {exc}") from exc

    # Rename .part → final filename
    try:
        if os.path.exists(part_file):
            os.replace(part_file, dest)
            try:
                os.unlink(metadata_file)
            except OSError:
                pass
    except OSError as exc:
        _log.error("Could not rename part file to %r: %s", dest, exc)
        raise Exception(f"Could not finalise file: {exc}") from exc

    item.title = os.path.basename(dest)
    _log.info("Direct complete  file=%s  size=%s", item.title, item.size)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sanitize_filename(name: str) -> str:
    """
    Reduce an untrusted filename (from Content-Disposition or a URL path) to a
    bare, safe basename. Strips any directory components, drive letters, NUL
    bytes, and reserved path characters so the result can never escape the
    chosen save directory.
    """
    name = (name or "").replace("\x00", "").strip().strip('"').strip()
    # Collapse any path separators and take the final component only.
    name = name.replace("\\", "/")
    name = name.split("/")[-1]
    name = os.path.basename(name)
    # Strip a leading Windows drive prefix if one survived (e.g. "C:evil")
    name = re.sub(r"^[A-Za-z]:", "", name)
    # Disallow pure-dot names and trim characters illegal on Windows.
    name = re.sub(r'[<>:"/\\|?*]', "_", name).strip(". ")
    if not name:
        return "download.bin"
    # Windows treats device names as special even when an extension is present.
    stem = name.split('.')[0].rstrip().upper()
    if stem in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        name = "_" + name
    return name[:200]


def _contain(directory: str, candidate: str) -> str:
    """
    Guarantee *candidate* stays inside *directory*. If a (sanitized) path still
    somehow lands outside, fall back to a safe name within *directory*.
    """
    directory = os.path.realpath(directory)
    full = os.path.realpath(candidate)
    if full == directory or full.startswith(directory + os.sep):
        return candidate
    _log.warning("Path escape blocked: %r is outside %r — using fallback name",
                 candidate, directory)
    return os.path.join(directory, "download.bin")


def _get_filename(url: str, headers) -> str:
    try:
        cd = headers.get("Content-Disposition", "")
        if cd:
            m = re.search(r"filename\*\s*=\s*[Uu][Tt][Ff]-8''([^;\r\n]+)", cd)
            if m:
                return _sanitize_filename(unquote(m.group(1).strip().strip('"')))
            m = re.search(r'filename\s*=\s*["\']?([^"\';\r\n]+)', cd, re.IGNORECASE)
            if m:
                return _sanitize_filename(unquote(m.group(1).strip().strip('"')))

        path = urlparse(url).path
        name = _sanitize_filename(os.path.basename(unquote(path)))
        if name and "." in name and name != "download.bin":
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
    except Exception as exc:
        _log.warning("Filename detection failed: %s", exc)
        return "download.bin"


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
