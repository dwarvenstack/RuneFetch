"""
RuneFetch auto-updater.

Flow, matching the behaviour the user asked for:

    you push a tag  →  release.yml publishes a GitHub Release
                    →  app checks the Releases API and finds it
                    →  UI prompts "Update available"
                    →  user clicks Update
                    →  installer downloads, app quits, installer runs, app restarts

Why an installer rather than swapping files in place: on Windows a running
executable cannot overwrite itself, and hand-rolled file swapping leaves a
half-updated install if it fails midway. The Inno Setup installer already
handles closing the app, replacing files atomically, and relaunching.

GitHub Releases is a pull system — there is no channel that reaches an
installed app. "Push to all users" therefore means every client asks on
startup; from the user's side that is indistinguishable from a push.
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from core.version import __version__, is_newer

_log = logging.getLogger(__name__)

REPO = "dwarvenstack/RuneFetch"
_API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
_RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"

_UA = f"RuneFetch/{__version__} (+https://github.com/{REPO})"
_TIMEOUT = 15

# Don't nag: only check once per this interval unless the user clicks the button.
_CHECK_INTERVAL_SEC = 24 * 60 * 60


# ── Version check ─────────────────────────────────────────────────────────────

def check_for_update(force: bool = False, cfg: dict = None) -> dict:
    """
    Ask GitHub whether a newer release exists.

    Returns a dict the UI can render directly::

        {"available": bool, "version": str, "current": str,
         "notes": str, "url": str, "asset_url": str, "asset_size": int,
         "error": str}

    Never raises — no network, rate limiting, or a malformed response must not
    break app startup, so failures come back as {"available": False, "error": …}.
    """
    result = {
        "available": False, "version": "", "current": __version__,
        "notes": "", "url": _RELEASES_PAGE, "asset_url": "",
        "asset_size": 0, "error": "",
    }

    if not force and cfg is not None and not _due_for_check(cfg):
        result["error"] = "skipped_recent_check"
        return result

    try:
        req = urllib.request.Request(_API_LATEST, headers={
            "User-Agent": _UA,
            "Accept": "application/vnd.github+json",
        })
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # 404 simply means no release published yet — not an error worth showing.
        if exc.code == 404:
            _log.info("Update check: no releases published yet")
            result["error"] = "no_releases"
        else:
            _log.warning("Update check failed: HTTP %s", exc.code)
            result["error"] = f"http_{exc.code}"
        return result
    except Exception as exc:
        _log.info("Update check failed (offline?): %s", exc)
        result["error"] = "network"
        return result

    if cfg is not None:
        cfg["last_update_check"] = int(time.time())

    tag = (data.get("tag_name") or "").strip()
    if not tag:
        result["error"] = "no_tag"
        return result

    result["version"] = tag.lstrip("vV")
    result["notes"]   = (data.get("body") or "").strip()
    result["url"]     = data.get("html_url") or _RELEASES_PAGE

    # Prefer the installer asset; fall back to the portable zip.
    for asset in data.get("assets") or []:
        name = (asset.get("name") or "").lower()
        if name.endswith(".exe") and "setup" in name:
            result["asset_url"]  = asset.get("browser_download_url", "")
            result["asset_size"] = asset.get("size", 0)
            break
    else:
        for asset in data.get("assets") or []:
            if (asset.get("name") or "").lower().endswith(".zip"):
                result["asset_url"]  = asset.get("browser_download_url", "")
                result["asset_size"] = asset.get("size", 0)
                break

    if is_newer(tag):
        result["available"] = True
        _log.info("Update available: %s (current %s)", result["version"], __version__)
    else:
        _log.info("Up to date (%s)", __version__)

    return result


def _due_for_check(cfg: dict) -> bool:
    last = cfg.get("last_update_check", 0)
    try:
        return (time.time() - float(last)) >= _CHECK_INTERVAL_SEC
    except (TypeError, ValueError):
        return True


# ── Download ──────────────────────────────────────────────────────────────────

def download_update(asset_url: str, progress_cb=None, expected_size: int = 0) -> str:
    """
    Download the installer to a temp file and return its path.

    progress_cb(percent, downloaded_bytes, total_bytes) is called as it streams
    so the UI can show a real progress bar. Raises on failure.

    GitHub's asset endpoint redirects to a CDN that does not always send
    Content-Length, so *expected_size* (from the Releases API) is used as a
    fallback — without it the bar would sit at zero for the whole download.
    """
    if not asset_url:
        raise ValueError("no asset URL")

    suffix = ".exe" if asset_url.lower().endswith(".exe") else ".zip"
    fd, path = tempfile.mkstemp(prefix="RuneFetch-update-", suffix=suffix)
    os.close(fd)

    _log.info("Downloading update from %s", asset_url)
    req = urllib.request.Request(asset_url, headers={"User-Agent": _UA})

    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(path, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0) or expected_size
            done = 0
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress_cb:
                    # With no size at all, report -1 so the UI can switch to an
                    # indeterminate bar rather than showing a bogus percentage.
                    pct = (done * 100.0 / total) if total else -1
                    progress_cb(pct, done, total)
            if total and done != total:
                raise RuntimeError(f"Incomplete update download: expected {total} bytes, received {done}")
    except Exception:
        # Never leave a partial installer behind — it could be run later.
        try:
            os.unlink(path)
        except OSError:
            pass
        raise

    if os.path.getsize(path) == 0:
        os.unlink(path)
        raise RuntimeError("downloaded file is empty")

    _log.info("Update downloaded to %s (%d bytes)", path, os.path.getsize(path))
    return path


# ── Install ───────────────────────────────────────────────────────────────────

def install_and_restart(installer_path: str, on_quit=None) -> bool:
    """
    Launch the installer and quit RuneFetch so it can replace the app.

    The installer is started detached — it must outlive this process, since
    this process is exactly what it needs to replace. /SILENT keeps the user
    on one confirmation (the one they already gave in the app) and the Inno
    script's `runafter` relaunches RuneFetch when it finishes.

    Only meaningful for a frozen build; from source there is nothing to install.
    """
    if not os.path.isfile(installer_path):
        _log.error("Installer missing: %s", installer_path)
        return False

    if not installer_path.lower().endswith(".exe"):
        # Portable zip: we cannot safely self-replace, so reveal it instead.
        _log.info("Update is a zip — opening its folder for manual install")
        _reveal(installer_path)
        return False

    if not getattr(sys, "frozen", False):
        _log.warning("Running from source — skipping install, revealing file")
        _reveal(installer_path)
        return False

    try:
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP so the installer survives
        # our exit; without this it dies with the parent and the update silently
        # does nothing.
        flags = 0x00000008 | 0x00000200
        subprocess.Popen(
            [installer_path, "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
            creationflags=flags, close_fds=True,
        )
        _log.info("Installer launched — quitting for update")
    except Exception as exc:
        _log.error("Failed to launch installer: %s", exc)
        return False

    # Give the installer a moment to start before we vanish.
    def _quit():
        time.sleep(1.5)
        if on_quit:
            try:
                on_quit()
            except Exception as exc:
                _log.warning("on_quit failed: %s", exc)
        os._exit(0)

    threading.Thread(target=_quit, daemon=True, name="rf-update-quit").start()
    return True


def _reveal(path: str):
    """Open the folder containing *path* in the OS file manager."""
    try:
        folder = str(Path(path).parent)
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", folder])
    except Exception as exc:
        _log.warning("Could not reveal %s: %s", path, exc)


def open_releases_page():
    """Fallback path: send the user to the release page in their browser."""
    import webbrowser
    webbrowser.open(_RELEASES_PAGE)
