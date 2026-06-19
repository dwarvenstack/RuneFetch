"""
RuneFetch — First-run dependency checker.

Runs before the main window opens. Checks for ffmpeg (required for
audio extraction and video/audio merging). If missing, offers to
auto-download a portable build into ~/.runefetch/bin/.
"""

import io
import logging
import os
import shutil
import sys
import threading
import zipfile
from pathlib import Path

_log = logging.getLogger(__name__)

# Persistent ffmpeg location (survives app updates)
_RF_BIN = Path.home() / ".runefetch" / "bin"
_FFMPEG_EXE = _RF_BIN / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")

# Gyan.dev offers a stable, versioned essentials build (~75 MB zipped)
_FFMPEG_ZIP_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


# ── Public entry point ────────────────────────────────────────────────────────

def run():
    """
    Check all required external dependencies and prompt the user to fix
    any that are missing.  Call this before creating the pywebview window.
    """
    _ensure_ffmpeg()


# ── ffmpeg ────────────────────────────────────────────────────────────────────

def _find_ffmpeg() -> str | None:
    """Return the path to an ffmpeg binary, or None if not found."""
    # 1. Already on PATH
    found = shutil.which("ffmpeg")
    if found:
        return found
    # 2. In our persistent bin dir
    if _FFMPEG_EXE.exists():
        return str(_FFMPEG_EXE)
    # 3. Next to the frozen EXE
    if getattr(sys, "frozen", False):
        local = Path(sys.executable).parent / _FFMPEG_EXE.name
        if local.exists():
            return str(local)
    return None


def _add_to_path(binary_path: str):
    """Prepend the directory containing *binary_path* to this process's PATH."""
    d = str(Path(binary_path).parent)
    if d not in os.environ.get("PATH", ""):
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


def _ensure_ffmpeg():
    found = _find_ffmpeg()
    if found:
        _add_to_path(found)
        _log.info("ffmpeg found: %s", found)
        return

    _log.info("ffmpeg not found — prompting user")
    _prompt_and_download()


def _prompt_and_download():
    """Show a tkinter dialog; download ffmpeg if the user agrees."""
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        _log.warning("tkinter not available — skipping ffmpeg prompt")
        return

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    answer = messagebox.askyesno(
        "RuneFetch — Setup",
        "FFmpeg is needed for:\n"
        "  • Merging HD video + audio tracks\n"
        "  • Converting to MP3 / AAC\n"
        "  • Audio-only downloads\n\n"
        "FFmpeg was not found on your system.\n\n"
        "Download it automatically now?\n"
        "(~75 MB  ·  saved to your user profile)\n\n"
        'Click "No" to skip — some downloads may fail.',
        icon="question",
    )
    root.destroy()

    if answer:
        _download_ffmpeg_ui()
    else:
        _log.info("User skipped ffmpeg download")


def _download_ffmpeg_ui():
    """Download ffmpeg in a background thread; show progress in a small window."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        _download_ffmpeg_silent()
        return

    root = tk.Tk()
    root.title("RuneFetch — Downloading FFmpeg")
    root.geometry("440x130")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    tk.Label(root, text="Downloading FFmpeg, please wait…", pady=12,
             font=("Segoe UI", 10)).pack()
    bar = ttk.Progressbar(root, mode="indeterminate", length=400)
    bar.pack(pady=4)
    bar.start(12)
    status_var = tk.StringVar(value="Connecting…")
    tk.Label(root, textvariable=status_var, fg="gray",
             font=("Segoe UI", 9)).pack()

    result = {"ok": False}

    def _work():
        try:
            import urllib.request
            status_var.set("Downloading (~75 MB)…")
            data = urllib.request.urlopen(_FFMPEG_ZIP_URL, timeout=180).read()

            status_var.set("Extracting…")
            _RF_BIN.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                # The zip has a top-level folder; ffmpeg.exe is inside bin/
                for name in zf.namelist():
                    if name.endswith("/ffmpeg.exe") or name == "ffmpeg.exe":
                        with zf.open(name) as src:
                            _FFMPEG_EXE.write_bytes(src.read())
                        break

            if _FFMPEG_EXE.exists():
                _add_to_path(str(_FFMPEG_EXE))
                result["ok"] = True
                status_var.set("Done! FFmpeg is ready.")
                _log.info("ffmpeg downloaded to %s", _FFMPEG_EXE)
            else:
                status_var.set("Error: ffmpeg.exe not found in archive.")
                _log.error("ffmpeg.exe not found after extracting zip")
        except Exception as exc:
            status_var.set(f"Download failed: {exc}")
            _log.error("ffmpeg download failed: %s", exc)
        finally:
            root.after(2000, root.destroy)

    threading.Thread(target=_work, daemon=True).start()
    root.mainloop()

    if not result["ok"]:
        _log.warning("ffmpeg download did not complete successfully")


def _download_ffmpeg_silent():
    """Fallback: download without UI (e.g. tkinter unavailable)."""
    try:
        import urllib.request
        _log.info("Downloading ffmpeg silently from %s", _FFMPEG_ZIP_URL)
        _RF_BIN.mkdir(parents=True, exist_ok=True)
        data = urllib.request.urlopen(_FFMPEG_ZIP_URL, timeout=180).read()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if name.endswith("/ffmpeg.exe") or name == "ffmpeg.exe":
                    with zf.open(name) as src:
                        _FFMPEG_EXE.write_bytes(src.read())
                    break
        if _FFMPEG_EXE.exists():
            _add_to_path(str(_FFMPEG_EXE))
            _log.info("ffmpeg installed silently to %s", _FFMPEG_EXE)
    except Exception as exc:
        _log.error("Silent ffmpeg download failed: %s", exc)
