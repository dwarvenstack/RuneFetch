#!/usr/bin/env python3
"""
RuneFetch — by DwarvenStack
Production-grade Internet Download Manager

Entry point:
  1. First-run setup wizard (installs ffmpeg, spotdl, sets PATH)
  2. Main application window
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

from setup_wizard import maybe_run_setup
from gui.main_window import RuneFetchWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("RuneFetch")
    app.setOrganizationName("DwarvenStack")
    app.setApplicationVersion("1.0.0")
    app.setFont(QFont("Segoe UI", 10))

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
