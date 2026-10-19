"""
EngineFacade — UI-agnostic wrapper over QueueManager.

Adds JSON-safe serialisation, a secondary event stream for the WebSocket
layer, and in-memory + on-disk history (same file as the Qt UI uses so
both entry points share one history).
"""

import json
import logging
import os
import threading
import queue as q_module
from pathlib import Path
from typing import Optional

from core.queue_manager import (
    QueueManager,
    STATE_COMPLETE, STATE_CANCELLED, STATE_ERROR,
)

_log = logging.getLogger(__name__)

_TERMINAL = {STATE_COMPLETE, STATE_CANCELLED, STATE_ERROR}

HISTORY_PATH = Path.home() / ".runefetch" / "runefetch_history.json"


def item_to_dict(it) -> dict:
    """Return a JSON-serialisable snapshot of a DownloadItem."""
    return {
        "id":           it.id,
        "url":          it.url,
        "title":        it.title,
        "source_label": it.source_label,
        "source_icon":  it.source_icon,
        "state":        it.state,
        "progress":     round(it.progress, 1),
        "speed":        it.speed,
        "speed_bps":    it.speed_bps,
        "eta":          it.eta,
        "size":         it.size,
        "error_msg":    it.error_msg,
        "fmt":          it.fmt,
        "quality":      it.quality,
        "dl_type":      it.dl_type,
        "save_path":    it.save_path,
        "series":       getattr(it, "series", {}),
    }


# ── On-disk history helpers ────────────────────────────────────────────────────

def _load_history_file() -> list[dict]:
    try:
        if HISTORY_PATH.exists():
            data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
    except Exception as exc:
        _log.warning("Could not load history file: %s", exc)
    return []


def _save_history_file(records: list[dict]):
    try:
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_PATH.write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        _log.warning("Could not save history file: %s", exc)


class EngineFacade:
    """
    Thread-safe facade over QueueManager for the WebSocket UI layer.

    The relay thread continuously drains QueueManager's internal event queue,
    converts raw item IDs into rich event dicts, and posts them to
    ``self._events`` for the WS server to broadcast.
    """

    def __init__(self, cfg: dict):
        self._cfg = cfg
        self._qm = QueueManager(
            max_concurrent=cfg.get("max_concurrent", 2),
            throttle_kbps=cfg.get("throttle_kbps", 0),
        )
        self._events: q_module.Queue = q_module.Queue()

        # Load history from disk (shared with Qt UI)
        self._history: list[dict] = list(reversed(_load_history_file()))
        self._seen_terminal: set[str] = set()
        self._lock = threading.Lock()

        self._relay = threading.Thread(
            target=self._relay_events, daemon=True, name="rf-engine-relay"
        )
        self._relay.start()

    # ── Queue operations ──────────────────────────────────────────────────────

    def add(self, url: str, opts: dict) -> str:
        series = None
        if opts.get('dl_type') == 'hianime_series':
            from downloaders.hianime_series import validate_batch
            series = validate_batch(url, opts.get('series'))
        item_id = self._qm.add(
            url=url,
            title=opts.get("title", ""),
            source_label=opts.get("source_label", ""),
            source_icon=opts.get("source_icon", ""),
            fmt=opts.get("fmt", "bestvideo+bestaudio/best"),
            quality=opts.get("quality", ""),
            save_path=opts.get("save_path") or self._cfg.get("save_path", ""),
            dl_type=opts.get("dl_type", "ytdlp"),
            fragment_threads=int(opts.get("fragment_threads") or
                                 self._cfg.get("fragment_threads", 4)),
            proxy=opts.get("proxy") or self._cfg.get("proxy", ""),
            start_paused=bool(opts.get("start_paused", False)),
            is_playlist=bool(opts.get("is_playlist", False)),
            series=series,
        )
        return item_id

    def pause(self, item_id: str):
        self._qm.pause(item_id)

    def resume(self, item_id: str):
        self._qm.resume(item_id)

    def cancel(self, item_id: str):
        self._qm.cancel(item_id)

    def remove(self, item_id: str):
        self._qm.remove(item_id)
        self._emit({"event": "item_removed", "data": {"id": item_id}})

    def pause_all(self):
        for item in self._qm.get_items():
            self._qm.pause(item.id)

    def resume_all(self):
        for item in self._qm.get_items():
            self._qm.resume(item.id)

    def clear_completed(self):
        for item in self._qm.get_items():
            if item.state in _TERMINAL:
                self._qm.remove(item.id)

    def set_concurrency(self, n: int):
        self._qm.set_concurrency(n)

    def set_throttle(self, kbps: int):
        self._qm.set_throttle(kbps)

    # ── Read ──────────────────────────────────────────────────────────────────

    def snapshot(self) -> list[dict]:
        return [item_to_dict(it) for it in self._qm.get_items()]

    def get_item_dict(self, item_id: str) -> Optional[dict]:
        item = self._qm._items.get(item_id)
        return item_to_dict(item) if item else None

    # ── History ───────────────────────────────────────────────────────────────

    def get_history(self) -> list[dict]:
        with self._lock:
            return list(self._history)

    def delete_history_entry(self, entry_id: str) -> bool:
        """Remove a history entry by its item id. Returns True if found."""
        with self._lock:
            before = len(self._history)
            self._history = [e for e in self._history if e.get("id") != entry_id]
            if len(self._history) < before:
                _save_history_file(list(reversed(self._history)))
                return True
        return False

    def clear_history(self):
        with self._lock:
            self._history = []
        _save_history_file([])

    def _record_history(self, d: dict):
        if not self._cfg.get("keep_history", True):
            return
        from datetime import datetime
        entry = dict(d)
        entry["date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        # Normalise fmt label to match Qt history format
        fmt = entry.get("fmt", "")
        extension = Path(entry.get("title", "")).suffix.lstrip('.').upper()
        if entry.get('dl_type') == 'hianime_series' and entry.get('series', {}).get('zip'):
            entry['fmt_display'] = 'ZIP'
        elif entry.get("dl_type") == "direct" and extension:
            entry["fmt_display"] = extension
        elif "mp3" in fmt.lower() or ("audio" in fmt.lower() and "video" not in fmt.lower()):
            entry["fmt_display"] = "MP3"
        elif "mp4" in fmt.lower() or "video" in fmt.lower() or "bestvideo" in fmt.lower():
            entry["fmt_display"] = "MP4"
        else:
            entry["fmt_display"] = fmt or "—"

        with self._lock:
            self._history.insert(0, entry)
            if len(self._history) > 500:
                self._history = self._history[:500]
            snapshot = list(reversed(self._history))   # oldest-first for file

        _save_history_file(snapshot)
        self._emit({"event": "history_added", "data": entry})

    # ── Events ────────────────────────────────────────────────────────────────

    def drain_events(self) -> list[dict]:
        events = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except q_module.Empty:
                break
        return events

    def push_toast(self, message: str, level: str = "info"):
        self._emit({"event": "toast", "data": {"message": message, "level": level}})

    def _emit(self, payload: dict):
        self._events.put(payload)

    def _relay_events(self):
        import time
        while True:
            try:
                ids = self._qm.poll_events()
                for item_id in ids:
                    item = self._qm._items.get(item_id)
                    if item is None:
                        self._emit({"event": "item_removed",
                                    "data": {"id": item_id}})
                        continue
                    d = item_to_dict(item)
                    self._emit({"event": "item_update", "data": d})

                    while item._log_lines:
                        try:
                            text, colour = item._log_lines.pop(0)
                            self._emit({"event": "item_log",
                                        "data": {"id": item_id,
                                                 "text": text,
                                                 "colour": colour}})
                        except IndexError:
                            break

                    if item.state in _TERMINAL and item_id not in self._seen_terminal:
                        self._seen_terminal.add(item_id)
                        self._record_history(d)

                time.sleep(0.1)
            except Exception as exc:
                _log.error("EngineFacade relay error: %s", exc, exc_info=True)
                time.sleep(1)
