"""
RuneFetch settings — read/write user preferences to config.json.
"""

import json
import os

CONFIG_DIR  = os.path.join(os.path.expanduser("~"), ".runefetch")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "save_path":         os.path.join(os.path.expanduser("~"), "Downloads", "RuneFetch"),
    "prompt_per_file":   False,
    "max_concurrent":    2,
    "throttle_kbps":     0,
    "fragment_threads":  4,
    "proxy":             "",
    "autostart":         True,
    "keep_history":      True,
    "default_quality":   "Best quality",
    "default_format":    "Video (MP4)",
    "theme":             "dark",
}


def load() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                stored = json.load(f)
            cfg = dict(DEFAULTS)
            cfg.update(stored)
            return cfg
        except Exception:
            pass
    return dict(DEFAULTS)


def save(cfg: dict):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[RuneFetch] Warning: could not save settings: {e}")
