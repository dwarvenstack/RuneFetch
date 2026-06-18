"""
RuneFetch settings — read/write user preferences to config.json.
"""

import json
import logging
import os
import secrets

_log = logging.getLogger(__name__)

CONFIG_DIR  = os.path.join(os.path.expanduser("~"), ".runefetch")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "save_path":            os.path.join(os.path.expanduser("~"), "Downloads", "RuneFetch"),
    "prompt_per_file":      False,
    "max_concurrent":       2,
    "throttle_kbps":        0,
    "fragment_threads":     4,
    "segments":             8,       # parallel connections for segmented direct downloads
    "proxy":                "",
    "autostart":            True,
    "keep_history":         True,
    "default_quality":      "Best quality",
    "default_format":       "Video (MP4)",
    "theme":                "dark",
    "bridge_token":         "",      # set on first run by get_or_create_bridge_token()
    "bridge_port":          8765,
    "ui_token":             "",      # set on first run by app.py for the web UI server
    "ui_port":              8770,
    "clipboard_monitor":    False,   # auto-detect URLs copied to clipboard
    "close_to_tray":        True,    # X button minimises to tray
}


def load() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                stored = json.load(f)
            cfg = dict(DEFAULTS)
            cfg.update(stored)
            return cfg
        except Exception as e:
            _log.warning("Could not load config from %s: %s — using defaults", CONFIG_PATH, e)
    return dict(DEFAULTS)


def save(cfg: dict):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        _log.warning("Could not save settings to %s: %s", CONFIG_PATH, e)


def get_or_create_bridge_token(cfg: dict) -> str:
    """Return the bridge shared token, generating and persisting one if absent."""
    if not cfg.get("bridge_token"):
        cfg["bridge_token"] = secrets.token_hex(32)
        save(cfg)
        _log.info("Generated new bridge token and saved to config.")
    return cfg["bridge_token"]
