"""
RuneFetch QueueManager — thread-safe download queue with:
  • Configurable concurrency (max_concurrent)
  • Speed throttling (throttle_kbps; 0 = unlimited)
  • Pause / resume (via threading.Event)
  • Cancel and remove
  • GUI event queue (poll_events) for thread-safe UI updates
"""

import logging
import threading
import uuid
import queue as q_module
from dataclasses import dataclass, field
from typing import Callable, Optional

_log = logging.getLogger(__name__)

# ── States ──────────────────────────────────────────────────────────────────
STATE_QUEUED      = "Queued"
STATE_DOWNLOADING = "Downloading"
STATE_COMPLETE    = "Complete"
STATE_ERROR       = "Error"
STATE_PAUSED      = "Paused"
STATE_CANCELLED   = "Cancelled"


@dataclass
class DownloadItem:
    id: str
    url: str
    title: str
    source_label: str
    source_icon: str
    fmt: str
    quality: str
    save_path: str
    dl_type: str
    fragment_threads: int = 4

    # Per-download settings (copied from QueueManager at add() time)
    throttle_kbps: int = 0
    proxy: str = ""

    # Runtime state
    state:     str   = STATE_QUEUED
    progress:  float = 0.0      # 0–100
    speed:     str   = ""
    speed_bps: float = 0.0      # numeric bytes/s for aggregation
    eta:       str   = ""
    size:      str   = ""
    error_msg: str   = ""

    # Log lines for GUI display: list of (text, colour) tuples
    # Written by worker thread, consumed by GUI poll loop
    _log_lines: list = field(default_factory=list)

    # Threading primitives
    cancel_event: threading.Event = field(default_factory=threading.Event)
    pause_event:  threading.Event = field(default_factory=threading.Event)
    _thread: Optional[threading.Thread] = field(default=None, repr=False)

    def __post_init__(self):
        # pause_event is SET when running, CLEARED when paused
        self.pause_event.set()


class QueueManager:
    """
    Manages a list of DownloadItems and dispatches them to worker threads.

    Thread-safety model
    ───────────────────
    All mutations to _items / _order happen inside _lock.
    Worker threads communicate back via _event_queue (a thread-safe Queue).
    The GUI thread calls poll_events() on its timer and processes the IDs.
    """

    def __init__(self, max_concurrent: int = 2, throttle_kbps: int = 0):
        self.max_concurrent = max_concurrent
        self.throttle_kbps  = throttle_kbps   # 0 = unlimited

        self._items: dict[str, DownloadItem] = {}
        self._order: list[str] = []
        self._lock  = threading.Lock()
        self._sem   = threading.Semaphore(max_concurrent)
        self._event_queue: q_module.Queue = q_module.Queue()

    # ── Public API ───────────────────────────────────────────────────────────

    def add(self, url: str, title: str, source_label: str, source_icon: str,
            fmt: str, quality: str, save_path: str, dl_type: str,
            fragment_threads: int = 4, proxy: str = "",
            start_paused: bool = False, is_playlist: bool = False) -> str:
        item_id = uuid.uuid4().hex[:8]
        item = DownloadItem(
            id=item_id, url=url, title=title,
            source_label=source_label, source_icon=source_icon,
            fmt=fmt, quality=quality, save_path=save_path,
            dl_type=dl_type, fragment_threads=fragment_threads,
            throttle_kbps=self.throttle_kbps,
            proxy=proxy,
        )
        item.is_playlist = is_playlist
        if start_paused:
            item.state = STATE_PAUSED
            item.pause_event.clear()
        with self._lock:
            self._items[item_id] = item
            self._order.append(item_id)
        self._notify(item_id)
        if not start_paused:
            self._dispatch_next()
        return item_id

    def pause(self, item_id: str):
        item = self._get(item_id)
        if item and item.state == STATE_DOWNLOADING:
            item.pause_event.clear()   # worker will block on wait()
            item.state = STATE_PAUSED
            self._notify(item_id)

    def resume(self, item_id: str):
        item = self._get(item_id)
        if item and item.state == STATE_PAUSED:
            item.pause_event.set()     # unblocks the worker (if running)
            if item._thread is None or not item._thread.is_alive():
                # Thread was never started (added with start_paused=True)
                item.state = STATE_QUEUED
                self._notify(item_id)
                self._dispatch_next()
            else:
                item.state = STATE_DOWNLOADING
                self._notify(item_id)

    def cancel(self, item_id: str):
        item = self._get(item_id)
        if item and item.state in (STATE_QUEUED, STATE_DOWNLOADING, STATE_PAUSED):
            item.cancel_event.set()
            item.pause_event.set()     # unblock if paused so it can exit
            item.state = STATE_CANCELLED
            self._notify(item_id)

    def remove(self, item_id: str):
        self.cancel(item_id)
        with self._lock:
            self._items.pop(item_id, None)
            if item_id in self._order:
                self._order.remove(item_id)
        self._notify(item_id)

    def get_items(self) -> list:
        with self._lock:
            return [self._items[i] for i in self._order if i in self._items]

    def poll_events(self) -> list:
        """Drain and return all pending event IDs. Call from GUI thread."""
        events = []
        while True:
            try:
                events.append(self._event_queue.get_nowait())
            except q_module.Empty:
                break
        return events

    def set_concurrency(self, n: int):
        """Adjust max concurrent downloads. Takes effect for new slots."""
        self.max_concurrent = max(1, n)
        # Recreate semaphore conservatively
        self._sem = threading.Semaphore(self.max_concurrent)
        self._dispatch_next()

    def set_throttle(self, kbps: int):
        """Set global speed cap in KB/s. 0 = unlimited."""
        self.throttle_kbps = kbps

    # ── Internal ─────────────────────────────────────────────────────────────

    def _get(self, item_id: str) -> Optional[DownloadItem]:
        return self._items.get(item_id)

    def _notify(self, item_id: str = None):
        self._event_queue.put(item_id)

    def _dispatch_next(self):
        """Start worker threads for all QUEUED items up to concurrency limit."""
        with self._lock:
            queued = [
                self._items[i] for i in self._order
                if i in self._items and self._items[i].state == STATE_QUEUED
            ]
        for item in queued:
            t = threading.Thread(
                target=self._run,
                args=(item,),
                daemon=True,
                name=f"rf-dl-{item.id}",
            )
            item._thread = t
            t.start()

    def _run(self, item: DownloadItem):
        # Block until a concurrency slot is free
        acquired = self._sem.acquire(timeout=3600)
        if not acquired:
            item.state = STATE_ERROR
            item.error_msg = "Timed out waiting for a download slot."
            self._notify(item.id)
            return

        try:
            if item.cancel_event.is_set():
                return

            item.state = STATE_DOWNLOADING
            self._notify(item.id)
            _log.info("[%s] Starting download  %s", item.id[:8], item.url[:80])

            from downloaders.router import run_download
            run_download(item, self._make_progress_cb(item))

            if not item.cancel_event.is_set():
                item.state    = STATE_COMPLETE
                item.progress = 100.0
                item.speed    = ""
                item.eta      = "Done"
                _log.info("[%s] Download complete  %s", item.id[:8], item.title[:60])

        except Exception as exc:
            if not item.cancel_event.is_set():
                item.state     = STATE_ERROR
                item.error_msg = str(exc)
                _log.error("[%s] Download error  %s  —  %s", item.id[:8], item.url[:60], exc)
        finally:
            self._sem.release()
            self._notify(item.id)
            self._dispatch_next()

    def _make_progress_cb(self, item: DownloadItem) -> Callable:
        """Returns a progress callback bound to `item`."""
        def cb(pct: float, speed: str = "", eta: str = "", size: str = "",
               speed_bps: float = 0.0):
            # Honour pause
            item.pause_event.wait()   # blocks while paused

            if item.cancel_event.is_set():
                return

            item.progress  = float(pct)
            item.speed     = speed
            item.speed_bps = float(speed_bps)
            item.eta       = eta
            if size:
                item.size = size
            self._notify(item.id)

        return cb
