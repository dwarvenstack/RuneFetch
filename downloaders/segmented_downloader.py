"""
Segmented (multi-connection) HTTP downloader.

Splits a file into N byte-range chunks, downloads them in parallel using a
ThreadPoolExecutor, then assembles the final file in order.

Used by router.py when the server advertises Accept-Ranges: bytes.
Falls back to single-stream download if Range requests are not supported.
"""

import logging
import math
import os
import threading
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from utils import net_guard

_log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

_CHUNK = 1 << 17          # 128 KB read chunk per segment
_MIN_SEG_SIZE = 1 << 20   # don't segment files smaller than 1 MB


def download(item, progress_cb=None) -> bool:
    """
    Download *item.url* into *item.save_path* using parallel range requests.

    The destination filename is derived from the server's Content-Disposition
    header (or the URL), sanitized, and contained within save_path.

    progress_cb(pct, speed_str, eta_str, size_str, speed_bps=float)

    Returns True on success, False on failure (item.error is set).
    """
    from downloaders.direct_downloader import (
        _get_filename, _unique_path, _contain, download_direct,
    )

    url    = item.url
    n_segs = int(getattr(item, "fragment_threads", 4))
    proxy  = getattr(item, "proxy", "") or ""
    proxies = {"http": proxy, "https": proxy} if proxy else None
    stop_evt: threading.Event = item.cancel_event
    report_done = threading.Event()
    range_ignored = threading.Event()

    save_dir = item.save_path
    try:
        os.makedirs(save_dir, exist_ok=True)
    except OSError as exc:
        item.error = f"Cannot create save dir: {exc}"
        return False

    def _single() -> bool:
        # Single-stream fallback: direct_downloader handles its own dest +
        # filename from save_path and raises on failure.
        download_direct(item, progress_cb)
        return True

    # ── HEAD to discover size, Range support, and filename ─────────────────────
    try:
        head = net_guard.safe_request("HEAD", url, headers=HEADERS,
                                      allow_redirects=True, timeout=10, proxies=proxies)
        total = int(head.headers.get("content-length", 0))
        accepts_ranges = head.headers.get("accept-ranges", "").lower() == "bytes"
        filename = _get_filename(url, head.headers)
        head.close()
    except net_guard.BlockedAddressError as exc:
        _log.warning("Segmented download blocked by net guard: %s", exc)
        item.error = "URL resolves to a private/local address — blocked."
        return False
    except Exception as exc:
        item.error = str(exc)
        return False

    if not total or not accepts_ranges or total < _MIN_SEG_SIZE or n_segs <= 1 or getattr(item, 'throttle_kbps', 0):
        return _single()

    dest = Path(_contain(save_dir, _unique_path(save_dir, filename)))
    item.title = dest.name

    seg_size  = math.ceil(total / n_segs)
    ranges    = [(i * seg_size, min((i + 1) * seg_size - 1, total - 1)) for i in range(n_segs)]
    tmp_files = [Path(str(dest) + f".part{i}") for i in range(n_segs)]

    downloaded = [0] * n_segs   # bytes downloaded per segment
    lock = threading.Lock()

    def _fmt_bytes(b):
        if b >= 1 << 30: return f"{b/(1<<30):.1f} GB"
        if b >= 1 << 20: return f"{b/(1<<20):.1f} MB"
        if b >= 1 << 10: return f"{b/(1<<10):.0f} KB"
        return f"{b} B"

    def _fetch_segment(idx):
        lo, hi = ranges[idx]
        seg_headers = {**HEADERS, "Range": f"bytes={lo}-{hi}"}
        try:
            with net_guard.safe_request("GET", url, headers=seg_headers, stream=True,
                                        timeout=60, proxies=proxies) as r:
                r.raise_for_status()
                if r.status_code == 200:
                    range_ignored.set()
                    return False
                if r.status_code != 206 or r.headers.get('Content-Range', '') != f'bytes {lo}-{hi}/{total}':
                    raise RuntimeError('Server returned an invalid byte range')
                with open(tmp_files[idx], "wb") as f:
                    for chunk in r.iter_content(_CHUNK):
                        item.pause_event.wait()
                        if stop_evt.is_set():
                            return False
                        f.write(chunk)
                        with lock:
                            downloaded[idx] += len(chunk)
        except Exception as exc:
            _log.warning("Segment %d failed: %s", idx, exc)
            return False
        return downloaded[idx] == hi - lo + 1

    import time
    start_t = time.monotonic()
    last_pct = [0.0]

    def _report():
        done = sum(downloaded)
        pct  = min(done / total * 100, 99.9)
        elapsed = time.monotonic() - start_t or 0.001
        bps  = done / elapsed
        remaining = (total - done) / bps if bps > 0 else 0
        eta  = f"{int(remaining)}s" if remaining < 60 else f"{int(remaining/60)}m"
        if progress_cb and abs(pct - last_pct[0]) >= 0.5:
            last_pct[0] = pct
            spd_str = (
                f"{bps/1_048_576:.1f} MB/s" if bps >= 1_048_576 else
                f"{bps/1024:.0f} KB/s"      if bps >= 1024       else
                f"{bps:.0f} B/s"
            )
            progress_cb(pct, spd_str, eta, _fmt_bytes(total), speed_bps=bps)

    # ── Run segments ──────────────────────────────────────────────────────────
    timer = threading.Timer(0.3, _report)

    def _repeating_report():
        if report_done.is_set():
            return
        _report()
        if not report_done.is_set() and not stop_evt.is_set() and sum(downloaded) < total:
            timer2 = threading.Timer(0.4, _repeating_report)
            timer2.daemon = True
            timer2.start()

    timer = threading.Timer(0.4, _repeating_report)
    timer.daemon = True
    timer.start()

    success = True
    with ThreadPoolExecutor(max_workers=n_segs) as pool:
        futures = {pool.submit(_fetch_segment, i): i for i in range(n_segs)}
        for fut in as_completed(futures):
            if not fut.result():
                success = False

    report_done.set()
    timer.cancel()

    if not success or stop_evt.is_set():
        for tmp in tmp_files:
            try: tmp.unlink(missing_ok=True)
            except Exception: pass
        if range_ignored.is_set() and not stop_evt.is_set():
            return _single()
        if stop_evt.is_set():
            item.error = "cancelled"
        else:
            item.error = "One or more segments failed"
        return False

    # ── Assemble ──────────────────────────────────────────────────────────────
    try:
        assembled = Path(str(dest) + '.assembling')
        with open(assembled, "wb") as out:
            for tmp in tmp_files:
                with open(tmp, 'rb') as source:
                    shutil.copyfileobj(source, out)
                tmp.unlink(missing_ok=True)
        os.replace(assembled, dest)
    except Exception as exc:
        item.error = f"Assembly failed: {exc}"
        assembled.unlink(missing_ok=True)
        for tmp in tmp_files:
            try: tmp.unlink(missing_ok=True)
            except Exception: pass
        return False

    if progress_cb:
        elapsed = time.monotonic() - start_t or 0.001
        bps = total / elapsed
        progress_cb(100.0, "", "", _fmt_bytes(total), speed_bps=bps)

    return True
