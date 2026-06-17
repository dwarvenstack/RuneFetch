"""
RuneFetch First-Run Setup Wizard
─────────────────────────────────
Installs ffmpeg and spotdl on first run only.

Crash fixes applied
────────────────────
1. spotdl is installed by spawning the REAL Python interpreter found via
   'py' launcher or PATH — never sys.executable (which is RuneFetch.exe
   in a frozen build, causing an infinite relaunch loop).
2. Worker→UI communication uses only Qt signals (thread-safe). No direct
   widget calls from the worker thread.
3. Wizard runs inside a proper app.exec() loop, not a busy processEvents
   while-loop that races with the QThread.
4. Every step is wrapped in broad try/except so one failure can never
   silently crash the whole process — always shown in the UI.
5. Timeout added to subprocess calls (120 s) so pip never hangs forever.
"""

import hashlib
import os
import sys
import shutil
import zipfile
import subprocess
import ctypes
from pathlib import Path

# winreg is Windows-only
if sys.platform == "win32":
    import winreg
else:
    winreg = None  # type: ignore

# ── Paths ─────────────────────────────────────────────────────────────────────
APP_DATA    = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
RF_DIR      = APP_DATA / "RuneFetch"
FFMPEG_DIR  = RF_DIR / "ffmpeg"
FFMPEG_BIN  = FFMPEG_DIR / "bin"
MARKER_FILE = RF_DIR / ".setup_done"
LOG_FILE    = RF_DIR / "setup_log.txt"

FFMPEG_URL      = (
    "https://github.com/GyanD/codexffmpeg/releases/download/7.1.1/"
    "ffmpeg-7.1.1-essentials_build.zip"
)
FFMPEG_SHA256_URL = (
    "https://github.com/GyanD/codexffmpeg/releases/download/7.1.1/"
    "ffmpeg-7.1.1-essentials_build.zip.sha256"
)
FFMPEG_ZIP_NAME = "ffmpeg-7.1.1-essentials_build.zip"
FFMPEG_INNER    = "ffmpeg-7.1.1-essentials_build"


# ── SHA-256 verification ──────────────────────────────────────────────────────

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _fetch_expected_sha256(cb) -> str | None:
    """Download the .sha256 sidecar file and return the expected hex digest."""
    import urllib.request
    try:
        cb(0, "Fetching ffmpeg checksum file…")
        with urllib.request.urlopen(FFMPEG_SHA256_URL, timeout=15) as r:
            content = r.read().decode("utf-8", errors="replace").strip()
        # File may be "hexdigest  filename" or just "hexdigest"
        return content.split()[0].lower()
    except Exception as e:
        _log(f"Could not fetch SHA-256: {e}")
        return None


# ── Logging ───────────────────────────────────────────────────────────────────

def _log(msg: str):
    try:
        RF_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


# ── UAC ───────────────────────────────────────────────────────────────────────

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def relaunch_as_admin():
    exe = sys.executable
    params = " ".join(f'"{a}"' for a in sys.argv)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
    sys.exit(0)


# ── Find real Python (critical for frozen exe) ────────────────────────────────

def _find_real_python() -> str | None:
    """
    In a PyInstaller frozen exe sys.executable = RuneFetch.exe.
    We must find the actual python.exe to run pip with.
    Search order:
      1. 'py' Windows launcher  (most reliable on Windows)
      2. 'python' / 'python3' on PATH
      3. Common install locations
    """
    # Try 'py' launcher first
    py = shutil.which("py")
    if py:
        return py

    for name in ("python", "python3", "python3.12", "python3.11", "python3.10"):
        found = shutil.which(name)
        if found and found != sys.executable:
            return found

    # Common Windows install paths
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python",
        Path("C:/Python312"), Path("C:/Python311"), Path("C:/Python310"),
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Python312",
    ]
    for base in candidates:
        for exe_name in ("python.exe", "python3.exe"):
            p = base / exe_name
            if p.exists():
                return str(p)

    return None


# ── PATH helpers ──────────────────────────────────────────────────────────────

def add_to_user_path(new_dir: str) -> bool:
    if winreg is None:
        return False
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Environment",
            0, winreg.KEY_READ | winreg.KEY_WRITE,
        )
        try:
            current, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current = ""
        parts = [p for p in current.split(";") if p.strip()]
        if new_dir not in parts:
            parts.append(new_dir)
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, ";".join(parts))
        winreg.CloseKey(key)
        # Tell Explorer about the change
        HWND_BROADCAST, WM_SETTINGCHANGE = 0xFFFF, 0x001A
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", 0x0002, 5000, None
        )
        return True
    except Exception as e:
        _log(f"PATH update failed: {e}")
        return False


def ffmpeg_in_path() -> bool:
    return shutil.which("ffmpeg") is not None


# ── Marker ────────────────────────────────────────────────────────────────────

def check_needs_setup() -> bool:
    return not MARKER_FILE.exists()


def mark_done():
    RF_DIR.mkdir(parents=True, exist_ok=True)
    MARKER_FILE.write_text("1")


# ── Install steps (run in worker thread) ─────────────────────────────────────

def install_ffmpeg(progress_cb) -> tuple[bool, str]:
    def cb(p, m):
        _log(m)
        progress_cb(p, m)

    try:
        cb(0, "Checking for existing ffmpeg…")

        if ffmpeg_in_path():
            cb(100, "ffmpeg already installed ✓")
            return True, ""

        local_exe = FFMPEG_BIN / "ffmpeg.exe"
        if local_exe.exists():
            cb(85, "Found local ffmpeg, updating PATH…")
            add_to_user_path(str(FFMPEG_BIN))
            os.environ["PATH"] = str(FFMPEG_BIN) + os.pathsep + os.environ.get("PATH", "")
            cb(100, "ffmpeg ready ✓")
            return True, ""

        cb(5, "Downloading ffmpeg (~75 MB)…")
        FFMPEG_DIR.mkdir(parents=True, exist_ok=True)
        zip_path = FFMPEG_DIR / FFMPEG_ZIP_NAME

        import urllib.request
        downloaded_bytes = [0]

        def reporthook(count, block_size, total_size):
            downloaded_bytes[0] = count * block_size
            if total_size > 0:
                pct = min(int(downloaded_bytes[0] / total_size * 58), 58)
                mb = downloaded_bytes[0] / 1_048_576
                total_mb = total_size / 1_048_576
                cb(5 + pct, f"Downloading… {mb:.1f} / {total_mb:.1f} MB")

        urllib.request.urlretrieve(FFMPEG_URL, zip_path, reporthook)

        # Verify SHA-256 before extracting
        expected = _fetch_expected_sha256(lambda _p, m: cb(64, m))
        if expected:
            cb(64, "Verifying download integrity…")
            actual = _sha256_file(zip_path)
            if actual != expected:
                zip_path.unlink(missing_ok=True)
                return False, (
                    f"SHA-256 mismatch — download may be corrupt or tampered.\n"
                    f"Expected: {expected[:16]}…\n"
                    f"Got:      {actual[:16]}…\n"
                    "Please retry or download ffmpeg manually."
                )
            cb(65, "Integrity check passed ✓")
        else:
            cb(64, "⚠ Could not verify checksum (offline?) — proceeding with caution.")
            _log("SHA-256 check skipped: could not fetch sidecar file.")

        cb(66, "Extracting ffmpeg…")
        extract_dir = FFMPEG_DIR / "_extract"
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        cb(80, "Moving files into place…")
        import shutil as _shutil
        src_bin = extract_dir / FFMPEG_INNER / "bin"
        if FFMPEG_BIN.exists():
            _shutil.rmtree(FFMPEG_BIN)
        _shutil.copytree(src_bin, FFMPEG_BIN)
        _shutil.rmtree(extract_dir, ignore_errors=True)
        zip_path.unlink(missing_ok=True)

        cb(92, "Adding ffmpeg to PATH…")
        add_to_user_path(str(FFMPEG_BIN))
        os.environ["PATH"] = str(FFMPEG_BIN) + os.pathsep + os.environ.get("PATH", "")

        cb(100, "ffmpeg installed ✓")
        return True, ""

    except Exception as e:
        _log(f"ffmpeg install exception: {e}")
        return False, str(e)


def install_spotdl(progress_cb) -> tuple[bool, str]:
    def cb(p, m):
        _log(m)
        progress_cb(p, m)

    try:
        cb(0, "Checking spotdl…")

        # Check if spotdl binary is already on PATH (most reliable check)
        if shutil.which("spotdl"):
            cb(100, "spotdl already installed ✓")
            return True, ""

        # Find a real Python interpreter (not the frozen exe)
        python_exe = _find_real_python()
        if not python_exe:
            msg = (
                "Could not find Python interpreter.\n"
                "Spotify support unavailable — install Python from python.org."
            )
            cb(100, msg)
            _log(msg)
            return False, msg

        _log(f"Using Python: {python_exe}")
        cb(15, f"Installing spotdl via pip…")

        result = subprocess.run(
            [python_exe, "-m", "pip", "install", "spotdl",
             "--quiet", "--no-warn-script-location"],
            capture_output=True,
            text=True,
            timeout=180,        # 3-minute hard timeout
            creationflags=(
                subprocess.CREATE_NO_WINDOW   # suppress console flash on Windows
                if sys.platform == "win32" else 0
            ),
        )

        if result.returncode == 0:
            cb(100, "spotdl installed ✓")
            return True, ""
        else:
            err = (result.stderr or result.stdout or "unknown error").strip()[-300:]
            _log(f"pip stderr: {err}")
            return False, f"pip install spotdl failed:\n{err[:120]}"

    except subprocess.TimeoutExpired:
        return False, "pip install timed out after 3 minutes."
    except Exception as e:
        _log(f"spotdl install exception: {e}")
        return False, str(e)


# ── PyQt6 Wizard ──────────────────────────────────────────────────────────────

def run_wizard():
    from PyQt6.QtWidgets import (
        QApplication, QWidget, QDialog, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QProgressBar,
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
    from PyQt6.QtGui import QPainter, QColor

    app = QApplication.instance() or QApplication(sys.argv)

    # ── Worker ────────────────────────────────────────────────────────────

    class Worker(QThread):
        # All signals carry only simple Python types — safe across threads
        progress  = pyqtSignal(str, int, str)   # step_id, pct, message
        step_done = pyqtSignal(str, bool, str)  # step_id, ok, error
        all_done  = pyqtSignal()

        def run(self):
            _log("=== RuneFetch First-Run Setup ===")

            # ffmpeg
            def ffmpeg_cb(pct, msg):
                self.progress.emit("ffmpeg", int(pct), msg)

            ok, err = install_ffmpeg(ffmpeg_cb)
            self.step_done.emit("ffmpeg", ok, err)
            if not ok:
                self.all_done.emit()
                return

            # spotdl (non-fatal)
            def spotdl_cb(pct, msg):
                self.progress.emit("spotdl", int(pct), msg)

            ok, err = install_spotdl(spotdl_cb)
            self.step_done.emit("spotdl", ok, err)

            mark_done()
            self.all_done.emit()

    # ── Window ────────────────────────────────────────────────────────────

    class Wizard(QDialog):
        """
        Bug 3 fix: inherits QDialog so exec() runs a scoped modal loop.
        This replaces the previous app.exec()/app.quit() approach which
        terminated the entire application when the wizard closed.
        """
        finished = pyqtSignal()

        def __init__(self):
            super().__init__()
            self.setWindowTitle("RuneFetch — First Run Setup")
            self.setFixedSize(500, 400)
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.Dialog
            )
            self._drag_pos = None
            self._build()

        def _build(self):
            self.setStyleSheet("QWidget { background:#0d0f14; color:#eef2ff; font-family:'Segoe UI'; }")
            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)

            # Title bar
            tbar = QWidget()
            tbar.setFixedHeight(46)
            tbar.setStyleSheet("background:#13161e; border-bottom:1px solid #1e2430;")
            tbl = QHBoxLayout(tbar)
            tbl.setContentsMargins(20, 0, 16, 0)
            brand = QLabel("⛩  RuneFetch  —  Setting up for first use")
            brand.setStyleSheet("color:#00d9ff; font-size:13px; font-weight:700; background:transparent;")
            tbl.addWidget(brand)
            root.addWidget(tbar)

            # Body
            body = QWidget()
            bl = QVBoxLayout(body)
            bl.setContentsMargins(28, 22, 28, 18)
            bl.setSpacing(14)

            intro = QLabel(
                "RuneFetch needs to install a few dependencies.\n"
                "This only happens once and takes about a minute."
            )
            intro.setStyleSheet("color:#8b92a8; font-size:12px;")
            intro.setWordWrap(True)
            bl.addWidget(intro)

            # Step cards
            self._steps: dict = {}
            for sid, label in [
                ("ffmpeg", "ffmpeg  —  video merging & audio extraction"),
                ("spotdl", "spotdl  —  Spotify playlist support"),
            ]:
                card = QWidget()
                card.setStyleSheet("background:#13161e; border:1px solid #1e2430; border-radius:8px;")
                cl = QVBoxLayout(card)
                cl.setContentsMargins(14, 10, 14, 10)
                cl.setSpacing(6)

                top = QHBoxLayout()
                icon = QLabel("○")
                icon.setStyleSheet("color:#4a5070; font-size:16px; background:transparent;")
                icon.setFixedWidth(22)
                top.addWidget(icon)
                lbl = QLabel(label)
                lbl.setStyleSheet("color:#8b92a8; font-size:12px; background:transparent;")
                top.addWidget(lbl, stretch=1)
                status = QLabel("Waiting…")
                status.setStyleSheet("color:#4a5070; font-size:11px; background:transparent;")
                top.addWidget(status)
                cl.addLayout(top)

                bar = QProgressBar()
                bar.setRange(0, 100)
                bar.setValue(0)
                bar.setTextVisible(False)
                bar.setFixedHeight(4)
                bar.setStyleSheet("""
                    QProgressBar { background:#1e2430; border:none; border-radius:2px; }
                    QProgressBar::chunk {
                        background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                            stop:0 #00d9ff,stop:1 #0099ff);
                        border-radius:2px;
                    }
                """)
                cl.addWidget(bar)

                detail = QLabel("")
                detail.setStyleSheet("color:#4a5070; font-size:10px; background:transparent;")
                cl.addWidget(detail)

                bl.addWidget(card)
                self._steps[sid] = {"icon": icon, "status": status, "bar": bar, "detail": detail}

            self._overall = QLabel("")
            self._overall.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._overall.setStyleSheet("color:#4a5070; font-size:11px;")
            bl.addWidget(self._overall)

            bl.addStretch()

            btn_row = QHBoxLayout()
            btn_row.addStretch()
            self._skip_btn = QPushButton("Skip (not recommended)")
            self._skip_btn.setStyleSheet("""
                QPushButton { background:transparent; color:#4a5070; border:none;
                              font-size:11px; padding:6px 12px; }
                QPushButton:hover { color:#8b92a8; }
            """)
            self._skip_btn.clicked.connect(self._skip)
            btn_row.addWidget(self._skip_btn)
            bl.addLayout(btn_row)
            root.addWidget(body, stretch=1)

            # Footer
            foot = QWidget()
            foot.setFixedHeight(28)
            foot.setStyleSheet("background:#13161e; border-top:1px solid #1e2430;")
            fl = QHBoxLayout(foot)
            fl.setContentsMargins(18, 0, 18, 0)
            fl.addStretch()
            QLabel("by DwarvenStack · github.com/dwarvenstack",
                   styleSheet="color:#2a2f3d; font-size:10px;",
                   parent=foot)
            fl.addWidget(
                QLabel("by DwarvenStack · github.com/dwarvenstack",
                       styleSheet="color:#2a2f3d; font-size:10px;")
            )
            root.addWidget(foot)

        # ── Slots (always called on GUI thread via Qt signal dispatch) ────

        def on_progress(self, sid: str, pct: int, msg: str):
            s = self._steps.get(sid)
            if not s:
                return
            # Mark as active on first progress tick
            if s["icon"].text() == "○":
                s["icon"].setText("◎")
                s["icon"].setStyleSheet("color:#00d9ff; font-size:16px; background:transparent;")
                s["status"].setText("Installing…")
                s["status"].setStyleSheet("color:#00d9ff; font-size:11px; background:transparent;")
            s["bar"].setValue(pct)
            s["detail"].setText(msg)
            self._overall.setText(msg)

        def on_step_done(self, sid: str, ok: bool, err: str):
            s = self._steps.get(sid)
            if not s:
                return
            if ok:
                s["icon"].setText("✓")
                s["icon"].setStyleSheet("color:#2dd4a0; font-size:16px; background:transparent;")
                s["status"].setText("Done ✓")
                s["status"].setStyleSheet("color:#2dd4a0; font-size:11px; background:transparent;")
                s["bar"].setValue(100)
                s["bar"].setStyleSheet("""
                    QProgressBar { background:#1e2430; border:none; border-radius:2px; }
                    QProgressBar::chunk {
                        background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                            stop:0 #2dd4a0,stop:1 #1a9b74); border-radius:2px;
                    }
                """)
            else:
                s["icon"].setText("✕")
                s["icon"].setStyleSheet("color:#ff6b6b; font-size:16px; background:transparent;")
                s["status"].setText("Failed")
                s["status"].setStyleSheet("color:#ff6b6b; font-size:11px; background:transparent;")
                s["detail"].setText(err[:80])

        def on_all_done(self):
            self._overall.setText("✓  Setup complete — launching RuneFetch…")
            self._overall.setStyleSheet("color:#2dd4a0; font-size:12px; font-weight:600;")
            self._skip_btn.hide()
            QTimer.singleShot(1400, self._finish)

        def _finish(self):
            self.finished.emit()
            self.accept()   # QDialog.accept() exits exec() and closes the dialog

        def _skip(self):
            mark_done()
            self.finished.emit()
            self.accept()

        # Drag to move
        def mousePressEvent(self, e):
            if e.button() == Qt.MouseButton.LeftButton:
                self._drag_pos = e.globalPosition().toPoint()

        def mouseMoveEvent(self, e):
            if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
                self.move(self.pos() + (e.globalPosition().toPoint() - self._drag_pos))
                self._drag_pos = e.globalPosition().toPoint()

        def mouseReleaseEvent(self, e):
            self._drag_pos = None

        def paintEvent(self, _e):
            p = QPainter(self)
            p.fillRect(self.rect(), QColor("#0d0f14"))
            p.end()

    # ── Wire up and run ───────────────────────────────────────────────────
    # Bug 3 fix: previously called app.exec() / app.quit() which terminates
    # the ENTIRE application event loop when the wizard closes. Any subsequent
    # call to run_wizard (e.g. from a re-download trigger) would kill the
    # running main window.
    #
    # Fix: Wizard now inherits QDialog. dialog.exec() runs a modal nested
    # event loop scoped only to this dialog. When the dialog closes, exec()
    # returns and the parent application continues normally. app.quit() is
    # never called.

    wizard = Wizard()
    worker = Worker()

    worker.progress.connect(wizard.on_progress)
    worker.step_done.connect(wizard.on_step_done)
    worker.all_done.connect(wizard.on_all_done)
    wizard._worker = worker   # prevent GC of QThread

    # Centre on screen
    screen = app.primaryScreen().geometry()
    wizard.move(
        (screen.width()  - wizard.width())  // 2,
        (screen.height() - wizard.height()) // 2,
    )

    worker.start()
    wizard.exec()   # modal nested loop — returns on close, never kills the app


# ── Public entry point ────────────────────────────────────────────────────────

def maybe_run_setup():
    if not check_needs_setup():
        # Always ensure our ffmpeg dir is on the process PATH after a reboot
        if FFMPEG_BIN.exists():
            ffmpeg_str = str(FFMPEG_BIN)
            if ffmpeg_str not in os.environ.get("PATH", ""):
                os.environ["PATH"] = ffmpeg_str + os.pathsep + os.environ.get("PATH", "")
        return

    if sys.platform != "win32":
        mark_done()
        return

    # Request elevation only if we can't write to our own app-data folder
    RF_DIR.mkdir(parents=True, exist_ok=True)
    test = RF_DIR / ".write_test"
    try:
        test.write_text("x")
        test.unlink()
    except PermissionError:
        if not is_admin():
            relaunch_as_admin()

    run_wizard()
