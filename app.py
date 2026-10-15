#!/usr/bin/env python3
"""
RuneFetch — pywebview entry point (Path B).

Architecture:
  webui/ (HTML/CSS/JS rendered by pywebview)
    ↕  WebSocket port 8770
  core/ui_server.py  (asyncio WS server, token-auth)
    ↕
  core/engine.py  (EngineFacade over QueueManager)
    ↕
  downloaders/*  (unchanged)

  core/bridge.py  (port 8765, browser extension — unchanged)

Usage:
  python app.py
"""

import sys
import os
import logging
import logging.handlers
import secrets
import threading
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _setup_logging():
    log_dir = Path.home() / ".runefetch"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "runefetch.log"

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(fh)
    root.addHandler(ch)
    logging.info("RuneFetch (web) starting — log: %s", log_file)


_log = logging.getLogger(__name__)


# ── Native API exposed to JS ──────────────────────────────────────────────────

class Api:
    """
    Methods callable from JS via window.pywebview.api.*

    Window management methods (move, resize, maximize) are needed because
    pywebview frameless windows can't be dragged/resized purely via CSS in
    all backends — we drive them from JS mouse events instead.
    """

    def __init__(self, window_ref_holder: list, cfg: dict):
        self._win  = window_ref_holder   # mutable list set after window creation
        self._cfg  = cfg
        self._maximized = False

    def _window(self):
        return self._win[0] if self._win else None

    # ── Window movement (called on every mousemove while dragging titlebar) ──

    def move_window(self, x: int, y: int):
        """Move the window to absolute screen coordinates."""
        w = self._window()
        if w:
            try:
                w.move(int(x), int(y))
            except Exception as exc:
                _log.debug("move_window error: %s", exc)

    # ── Window resize (called from JS edge-drag) ─────────────────────────────

    def resize_window(self, width: int, height: int):
        """Resize the window to the given dimensions."""
        w = self._window()
        if w:
            try:
                w.resize(max(800, int(width)), max(560, int(height)))
            except Exception as exc:
                _log.debug("resize_window error: %s", exc)

    def move_and_resize(self, x: int, y: int, width: int, height: int):
        """Atomically reposition and resize (used for left/top edge drag)."""
        w = self._window()
        if w:
            try:
                w.move(int(x), int(y))
                w.resize(max(800, int(width)), max(560, int(height)))
            except Exception as exc:
                _log.debug("move_and_resize error: %s", exc)

    # ── Maximize / restore ────────────────────────────────────────────────────

    def toggle_maximize(self):
        """Toggle between maximized and normal window state."""
        w = self._window()
        if not w:
            return
        try:
            if self._maximized:
                w.restore()
                self._maximized = False
            else:
                w.maximize()
                self._maximized = True
        except Exception as exc:
            _log.debug("toggle_maximize error: %s", exc)
        return self._maximized

    def get_window_state(self) -> dict:
        """Return current window state for JS to sync its maximize button."""
        return {"maximized": self._maximized}

    # ── Standard window controls ──────────────────────────────────────────────

    def minimize(self):
        w = self._window()
        if w:
            w.minimize()

    def close(self):
        """Close or minimise-to-tray depending on the setting."""
        w = self._window()
        if not w:
            return
        if self._cfg.get("close_to_tray", True):
            w.hide()
            _show_tray_balloon("RuneFetch is still running in the tray.")
        else:
            w.destroy()

    def minimize_to_tray(self):
        w = self._window()
        if w:
            w.hide()

    # ── File / folder dialogs ─────────────────────────────────────────────────

    def choose_folder(self) -> str | None:
        import webview
        w = self._window()
        if not w:
            return None
        result = w.create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else None

    def open_folder(self, path: str):
        """Open a folder in the OS file explorer."""
        try:
            path = os.path.normpath(path)
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", path])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            _log.warning("open_folder(%s) failed: %s", path, exc)

    # ── App info ──────────────────────────────────────────────────────────────

    def get_tokens(self) -> dict:
        return {
            "ui_token":     self._cfg.get("ui_token", ""),
            "bridge_token": self._cfg.get("bridge_token", ""),
        }

    def get_version(self) -> str:
        from core.version import __version__
        return __version__

    def read_clipboard(self) -> str:
        """Read plain text from the system clipboard (called from JS Paste button)."""
        try:
            if sys.platform == "win32":
                import subprocess
                result = subprocess.check_output(
                    ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                    timeout=3, text=True, stderr=subprocess.DEVNULL,
                    creationflags=0x08000000,  # CREATE_NO_WINDOW
                )
                return result.strip()
            else:
                import subprocess
                # macOS
                result = subprocess.check_output(["pbpaste"], timeout=3, text=True)
                return result.strip()
        except Exception as exc:
            _log.debug("read_clipboard: %s", exc)
        return ""

    def check_file_exists(self, save_path: str, title: str) -> dict:
        """Check whether a file matching `title` already exists in `save_path`."""
        try:
            if not save_path or not title or not os.path.isdir(save_path):
                return {"exists": False, "filename": ""}
            safe = title[:60].replace("/", "_").replace("\\", "_")
            for fname in os.listdir(save_path):
                if safe.lower()[:20] in fname.lower():
                    return {"exists": True, "filename": fname}
        except Exception as exc:
            _log.warning("check_file_exists: %s", exc)
        return {"exists": False, "filename": ""}


# ── Win32 foreground helper ───────────────────────────────────────────────────

def _force_foreground(win_title: str = "RuneFetch", webview_window=None):
    """Bring window to front and force WebView2 to repaint."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        import ctypes.wintypes
        u32  = ctypes.windll.user32
        k32  = ctypes.windll.kernel32
        SW_RESTORE = 9

        hwnd = u32.FindWindowW(None, win_title)
        if not hwnd:
            return

        # 1. Allow foreground steal
        u32.AllowSetForegroundWindow(ctypes.wintypes.DWORD(-1))
        # 2. Restore / un-hide
        u32.ShowWindow(hwnd, SW_RESTORE)
        # 3. AttachThreadInput so SetForegroundWindow isn't silently blocked
        fg_hwnd = u32.GetForegroundWindow()
        fg_tid  = u32.GetWindowThreadProcessId(fg_hwnd, None)
        our_tid = k32.GetCurrentThreadId()
        attached = False
        if fg_tid and fg_tid != our_tid:
            u32.AttachThreadInput(our_tid, fg_tid, True)
            attached = True
        u32.SetForegroundWindow(hwnd)
        u32.BringWindowToTop(hwnd)
        if attached:
            u32.AttachThreadInput(our_tid, fg_tid, False)

        # 4. Force WebView2 compositor to wake up.
        #    InvalidateRect alone doesn't reach DirectComposition.
        #    WM_SIZE forces WebView2 to resize its compositor surface → resumes render.
        #    SetWindowPos with SWP_FRAMECHANGED triggers full window recomposition.
        WM_SIZE       = 0x0005
        SWP_NOMOVE    = 0x0002
        SWP_NOSIZE    = 0x0001
        SWP_FRAMECHANGED = 0x0020
        rect = ctypes.wintypes.RECT()
        u32.GetClientRect(hwnd, ctypes.byref(rect))
        cw = rect.right  - rect.left
        ch = rect.bottom - rect.top
        u32.PostMessageW(hwnd, WM_SIZE, 0, (ch << 16) | (cw & 0xFFFF))
        u32.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                         SWP_NOMOVE | SWP_NOSIZE | SWP_FRAMECHANGED)
        # Also invalidate for good measure
        u32.InvalidateRect(hwnd, None, True)
        u32.UpdateWindow(hwnd)

        # 5. Nudge layout from JS side after WebView2 has had time to resume
        if webview_window:
            def _nudge():
                import time; time.sleep(0.4)
                try:
                    webview_window.evaluate_js(
                        'window.dispatchEvent(new Event("resize"))'
                    )
                except Exception:
                    pass
            threading.Thread(target=_nudge, daemon=True).start()

    except Exception as exc:
        _log.debug("_force_foreground: %s", exc)


# ── Tray icon (pystray) ───────────────────────────────────────────────────────

_tray_icon_ref = []   # mutable so _show_tray_balloon can reach it


def _show_tray_balloon(message: str):
    if _tray_icon_ref:
        try:
            _tray_icon_ref[0].notify(message, "RuneFetch")
        except Exception:
            pass


def _start_tray(window_ref_holder: list, cfg: dict, engine=None):
    try:
        import pystray
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([2, 2, 62, 62], fill="#1E1812")
        draw.ellipse([8, 8, 56, 56], fill="#E3A65A")
        # "R" in the centre
        try:
            draw.text((20, 16), "R", fill="#1E1812", font=ImageFont.truetype("arial.ttf", 28))
        except Exception:
            draw.text((22, 20), "R", fill="#1E1812")

        def _show(_icon, _item):
            w = window_ref_holder[0] if window_ref_holder else None
            if w:
                w.show()
            _force_foreground("RuneFetch", webview_window=w)

        def _pause_all(_icon, _item):
            if engine:
                engine.pause_all()

        def _resume_all(_icon, _item):
            if engine:
                engine.resume_all()

        def _quit(_icon, _item):
            _icon.stop()
            w = window_ref_holder[0] if window_ref_holder else None
            if w:
                w.destroy()

        menu = pystray.Menu(
            pystray.MenuItem("Open RuneFetch", _show, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Pause all",  _pause_all),
            pystray.MenuItem("Resume all", _resume_all),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit RuneFetch", _quit),
        )
        icon = pystray.Icon("RuneFetch", img, "RuneFetch — idle", menu)
        _tray_icon_ref.append(icon)

        # Live tooltip thread: updates every 2 s
        def _tooltip_loop():
            import time
            while True:
                try:
                    if engine:
                        items  = engine._qm.get_items()
                        active = [i for i in items if i.state == "Downloading"]
                        queued = [i for i in items if i.state == "Queued"]
                        total_bps = sum(i.speed_bps for i in active)
                        if active:
                            spd = (f"{total_bps/1_048_576:.1f} MB/s" if total_bps >= 1_048_576
                                   else f"{total_bps/1024:.0f} KB/s" if total_bps >= 1024 else "")
                            icon.title = f"RuneFetch — {len(active)} downloading" + (f"  {spd}" if spd else "")
                        elif queued:
                            icon.title = f"RuneFetch — {len(queued)} queued"
                        else:
                            icon.title = "RuneFetch — idle"
                except Exception:
                    pass
                time.sleep(2)

        threading.Thread(target=_tooltip_loop, daemon=True, name="rf-tray-tip").start()
        threading.Thread(target=icon.run, daemon=True, name="rf-tray").start()
        _log.info("Tray icon started")
    except ImportError:
        _log.info("pystray/pillow not installed — tray icon disabled")
    except Exception as exc:
        _log.warning("Tray icon error: %s", exc)


# ── Clipboard monitor ─────────────────────────────────────────────────────────

def _start_clipboard_monitor(engine, cfg: dict, ui_server=None):
    if not cfg.get("clipboard_monitor", False):
        return
    try:
        import pyperclip
    except ImportError:
        _log.info("pyperclip not installed — clipboard monitor disabled")
        return

    def _monitor():
        import time
        last = ""
        while True:
            try:
                text = (pyperclip.paste() or "").strip()
                if text != last and text.startswith(("http://", "https://")):
                    last = text
                    from core.detector import detect
                    det = detect(text)
                    if det["type"] not in ("drm", "unknown"):
                        engine.push_toast(
                            f"Clipboard URL detected — click to add: {text[:60]}", "info"
                        )
            except Exception:
                pass
            time.sleep(1.5)

    threading.Thread(target=_monitor, daemon=True, name="rf-clipboard").start()
    _log.info("Clipboard monitor active")


# ── Restore persisted queue ───────────────────────────────────────────────────

def _restore_queue(engine, cfg: dict):
    if not cfg.get("autostart", True):
        return
    from core.queue_persistence import load_queue, clear_queue_state
    from core.detector import detect

    saved = load_queue()
    if not saved:
        return
    for rec in saved:
        url = rec.get("url", "")
        if not url:
            continue
        try:
            det = detect(url)
            engine.add(url, {
                "title":        rec.get("title", ""),
                "source_label": rec.get("source_label") or det.get("label", ""),
                "source_icon":  rec.get("source_icon")  or det.get("icon", ""),
                "fmt":          rec.get("fmt", "bestvideo+bestaudio/best"),
                "quality":      rec.get("quality", ""),
                "dl_type":      rec.get("dl_type", "ytdlp"),
                "save_path":    rec.get("dest") or cfg.get("save_path", ""),
                "start_paused": True,
            })
        except Exception as exc:
            _log.warning("Failed to restore queue item %s: %s", url[:60], exc)
    clear_queue_state()
    _log.info("Restored %d paused item(s) from previous session", len(saved))


# ── Main ──────────────────────────────────────────────────────────────────────

def _base_dir() -> Path:
    """Return the resource root — sys._MEIPASS when frozen, else repo root."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def main():
    _setup_logging()

    # First-run: check for ffmpeg and offer auto-download before window opens
    try:
        from core.first_run import run as first_run
        first_run()
    except Exception as exc:
        _log.warning("First-run check failed (non-fatal): %s", exc)

    import webview

    from utils.settings import load as load_cfg, save as save_cfg, get_or_create_bridge_token

    cfg = load_cfg()

    # Generate UI token if absent
    if not cfg.get("ui_token"):
        cfg["ui_token"] = secrets.token_hex(32)
        save_cfg(cfg)
        _log.info("Generated UI token")

    get_or_create_bridge_token(cfg)

    # Engine
    from core.engine import EngineFacade
    engine = EngineFacade(cfg)

    # Restore saved queue
    _restore_queue(engine, cfg)

    # Browser extension bridge
    try:
        from core.bridge import LocalBridge
        bridge = LocalBridge(token=cfg["bridge_token"], port=cfg.get("bridge_port", 8765))
        bridge.start()

        def _drain_bridge():
            import time
            while True:
                try:
                    while not bridge.incoming.empty():
                        url, title = bridge.incoming.get_nowait()
                        from core.detector import detect
                        det = detect(url)

                        # Bring window to front (restores from tray / behind other apps)
                        w = window_ref[0] if window_ref else None
                        if w:
                            try:
                                w.show()
                            except Exception:
                                pass
                        _force_foreground("RuneFetch", webview_window=w)

                        engine._emit({
                            "event": "bridge_url",
                            "data": {
                                "url":   url,
                                "title": title,
                                "label": det.get("label", ""),
                                "icon":  det.get("icon", ""),
                                "type":  det.get("type", "ytdlp"),
                                "is_playlist": det.get("is_playlist", False),
                            },
                        })
                except Exception as exc:
                    _log.warning("Bridge drain error: %s", exc)
                time.sleep(0.5)

        threading.Thread(target=_drain_bridge, daemon=True, name="rf-bridge-drain").start()
    except Exception as exc:
        _log.warning("Bridge failed to start: %s", exc)

    # UI WebSocket server
    from core.ui_server import UIServer
    ui_server = UIServer(engine=engine, cfg=cfg)
    ui_server.start()

    # Clipboard monitor
    _start_clipboard_monitor(engine, cfg, ui_server)

    # pywebview window
    webui_path = _base_dir() / "webui" / "index.html"
    window_ref = []

    api = Api(window_ref, cfg)

    window = webview.create_window(
        title="RuneFetch",
        url=str(webui_path),
        js_api=api,
        width=1100,
        height=720,
        min_size=(800, 560),
        frameless=True,
        easy_drag=False,      # we handle drag via JS + api.move_window()
        background_color="#1E1812",
    )
    window_ref.append(window)

    def _on_closed():
        try:
            from core.queue_persistence import save_queue
            save_queue(engine._qm.get_items())
        except Exception as exc:
            _log.warning("Failed to save queue on close: %s", exc)
        ui_server.stop()

    window.events.closed += _on_closed

    # Tray (pass engine for live tooltip)
    _start_tray(window_ref, cfg, engine)

    webview.start(debug=False)


if __name__ == "__main__":
    if "--spotdl-worker" in sys.argv:
        # A frozen executable is not a Python interpreter: dispatch explicitly.
        sys.argv.remove("--spotdl-worker")
        if sys.platform == "win32" and getattr(sys, "frozen", False):
            import ctypes
            import msvcrt
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetStdHandle.restype = ctypes.c_void_p
            for name, handle_id in (("stdout", -11), ("stderr", -12)):
                handle = kernel.GetStdHandle(handle_id)
                if handle and handle != ctypes.c_void_p(-1).value:
                    fd = msvcrt.open_osfhandle(handle, os.O_WRONLY)
                    setattr(sys, name, os.fdopen(fd, "w", encoding="utf-8", buffering=1))
        from spotdl.console.entry_point import console_entry_point
        console_entry_point()
    else:
        main()
