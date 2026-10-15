"""
RuneFetch version — single source of truth.

The version used to be hardcoded in four places and had already drifted
(app.py and ui_server.py said 2.0.0 while bridge.py still said 1.0.0). Update
checking compares versions, so a stale copy means the app misjudges whether a
release is newer than itself. Everything now reads the VERSION file instead.
"""

import logging
import pathlib
import sys

_log = logging.getLogger(__name__)

# Fallback used only if the VERSION file is missing from a build. Keep it in
# sync with VERSION so a packaging mistake degrades quietly rather than
# reporting something wildly wrong.
_FALLBACK = "2.0.1"


def _version_file() -> pathlib.Path:
    """Locate VERSION in both a source checkout and a PyInstaller bundle."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return pathlib.Path(sys._MEIPASS) / "VERSION"
    return pathlib.Path(__file__).resolve().parent.parent / "VERSION"


def _read() -> str:
    try:
        text = _version_file().read_text(encoding="utf-8").strip()
        if text:
            return text
    except Exception as exc:
        _log.warning("Could not read VERSION file (%s) — using %s", exc, _FALLBACK)
    return _FALLBACK


__version__ = _read()


def parse(version: str) -> tuple:
    """
    Turn "2.1.0" into (2, 1, 0) for comparison.

    Tolerates a leading "v" and trailing pre-release suffixes ("2.1.0-beta.1"),
    which GitHub tags commonly carry. Non-numeric parts are dropped rather than
    raising, because a malformed upstream tag must never crash the update check.
    """
    cleaned = version.strip().lstrip("vV").split("-")[0].split("+")[0]
    parts = []
    for chunk in cleaned.split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            break
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer(candidate: str, current: str = None) -> bool:
    """True if *candidate* is a strictly newer version than *current*."""
    return parse(candidate) > parse(current or __version__)
