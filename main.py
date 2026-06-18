#!/usr/bin/env python3
"""
RuneFetch — by DwarvenStack
Production-grade Internet Download Manager

Entry point:
  1. Logging setup (file + console)
  2. First-run setup wizard (installs ffmpeg, spotdl, sets PATH)
  3. Main application window
"""
import sys
import os
import logging
import logging.handlers
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QFontDatabase

from setup_wizard import maybe_run_setup
from gui.main_window import RuneFetchWindow


def _load_fonts():
    """Register bundled fonts from assets/fonts/ before QApplication.setFont().

    Font files are not shipped in the repo — place them here manually:
      assets/fonts/Inter-Regular.ttf
      assets/fonts/Inter-Medium.ttf
      assets/fonts/Inter-SemiBold.ttf
      assets/fonts/SpaceGrotesk-SemiBold.ttf
      assets/fonts/SpaceGrotesk-Bold.ttf
      assets/fonts/JetBrainsMono-Regular.ttf

    If the files are absent the app silently falls back to system fonts.
    """
    fonts_dir = Path(__file__).parent / "assets" / "fonts"
    if not fonts_dir.is_dir():
        return
    loaded = 0
    for ttf in fonts_dir.glob("*.ttf"):
        fid = QFontDatabase.addApplicationFont(str(ttf))
        if fid != -1:
            loaded += 1
    for otf in fonts_dir.glob("*.otf"):
        fid = QFontDatabase.addApplicationFont(str(otf))
        if fid != -1:
            loaded += 1
    if loaded:
        logging.getLogger(__name__).info("Loaded %d bundled font(s) from %s", loaded, fonts_dir)


def _setup_logging():
    log_dir = Path.home() / ".runefetch"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "runefetch.log"

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    # Rotating file — keeps last 2 MB, 3 backups
    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # Console (terminal) — INFO and above
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(fh)
    root.addHandler(ch)

    logging.info("RuneFetch starting — log: %s", log_file)


def main():
    _setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("RuneFetch")
    app.setOrganizationName("DwarvenStack")
    app.setApplicationVersion("2.0.0")

    # Register bundled fonts BEFORE setFont so they are available
    _load_fonts()
    app.setFont(QFont("Candara", 10))

    # Keep the event loop alive when the main window is closed (tray mode)
    app.setQuitOnLastWindowClosed(False)

    # ── First-run setup (no-op after first successful run) ────────────────
    maybe_run_setup()

    # ── Main window ───────────────────────────────────────────────────────
    window = RuneFetchWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
