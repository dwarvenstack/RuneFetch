"""
Persist QUEUED / PAUSED / DOWNLOADING items across restarts.

Saved to ~/.runefetch/queue_state.json as a JSON array of item dicts.
DOWNLOADING items are serialised as PAUSED so they resume rather than
re-start from scratch (the downloader will simply restart the transfer).
"""

import json
import logging
from pathlib import Path

_log = logging.getLogger(__name__)
_STATE_FILE = Path.home() / ".runefetch" / "queue_state.json"

_RESUMABLE = {"QUEUED", "PAUSED", "DOWNLOADING", "Queued", "Paused", "Downloading"}


def save_queue(items: list) -> None:
    """Serialise resumable items to disk.  Called on app shutdown."""
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        records = []
        for item in items:
            # Support both old (status/dest) and current (state/save_path) field names
            status = getattr(item, "state", getattr(item, "status", ""))
            if status not in _RESUMABLE:
                continue
            save_status = "PAUSED" if status in ("DOWNLOADING", "Downloading") else status
            records.append({
                "id":               getattr(item, "id",       ""),
                "url":              getattr(item, "url",      ""),
                "title":            getattr(item, "title",    ""),
                "dest":             str(getattr(item, "save_path",
                                       getattr(item, "dest", ""))),
                "status":           save_status,
                "progress":         getattr(item, "progress", 0.0),
                "proxy":            getattr(item, "proxy",    ""),
                "fragment_threads": getattr(item, "fragment_threads", 4),
                "fmt":              getattr(item, "fmt",      ""),
                "quality":          getattr(item, "quality",  ""),
                "dl_type":          getattr(item, "dl_type",  "ytdlp"),
                "source_label":     getattr(item, "source_label", ""),
                "source_icon":      getattr(item, "source_icon",  ""),
            })
        _STATE_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        _log.info("Queue saved: %d item(s) to %s", len(records), _STATE_FILE)
    except Exception as e:
        _log.warning("Failed to save queue state: %s", e)


def load_queue() -> list[dict]:
    """Return saved items as plain dicts, or an empty list."""
    try:
        if not _STATE_FILE.exists():
            return []
        data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        _log.info("Queue restored: %d item(s) from %s", len(data), _STATE_FILE)
        return data
    except Exception as e:
        _log.warning("Failed to load queue state: %s", e)
        return []


def clear_queue_state() -> None:
    """Remove the persisted state file (called after successful restore)."""
    try:
        if _STATE_FILE.exists():
            _STATE_FILE.unlink()
    except Exception as e:
        _log.warning("Failed to clear queue state: %s", e)
