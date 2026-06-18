"""
Download confirmation dialog — shown when the browser extension sends a URL.

Mirrors the IDM "Download File Info" popup:
  • URL (read-only)
  • Category (auto-detected, editable)
  • Save As path + Browse
  • File size (fetched async via HEAD request)
  • Description / notes field
  • Buttons: Start Download | Download Later | Cancel

"Start Download"  → accepted, item starts immediately
"Download Later"  → accepted, item starts paused (queued but not running)
"Cancel"          → rejected, nothing added
"""

import logging
import os
import threading
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QCheckBox, QFrame, QFileDialog, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QFont

from gui.theme import (
    BG_PRIMARY, BG_SECONDARY, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_CYAN, ACCENT_BLUE, ACCENT_GREEN, BORDER,
)

_log = logging.getLogger(__name__)

# ── Async file-info fetcher ───────────────────────────────────────────────────

class _InfoFetcher(QObject):
    done = pyqtSignal(str, str)   # (size_str, filename)

    def __init__(self, url: str, proxy: str = ""):
        super().__init__()
        self._url   = url
        self._proxy = proxy

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self):
        try:
            import requests
            from urllib.parse import urlparse, unquote
            import re

            proxies = {"http": self._proxy, "https": self._proxy} if self._proxy else None
            head = requests.head(
                self._url,
                headers={"User-Agent": "Mozilla/5.0"},
                allow_redirects=True,
                timeout=8,
                proxies=proxies,
            )

            # Size
            size_str = ""
            cl = head.headers.get("Content-Length")
            if cl:
                b = int(cl)
                if b >= 1_073_741_824:
                    size_str = f"{b/1_073_741_824:.2f} GB"
                elif b >= 1_048_576:
                    size_str = f"{b/1_048_576:.2f} MB"
                elif b >= 1024:
                    size_str = f"{b/1024:.0f} KB"
                else:
                    size_str = f"{b} B"

            # Filename from Content-Disposition
            filename = ""
            cd = head.headers.get("Content-Disposition", "")
            m = re.search(r"filename\*=UTF-8''([^;\r\n]+)", cd, re.I)
            if m:
                filename = unquote(m.group(1).strip().strip('"'))
            else:
                m = re.search(r'filename=["\']?([^"\';\r\n]+)', cd, re.I)
                if m:
                    filename = unquote(m.group(1).strip().strip('"'))
            if not filename:
                filename = unquote(urlparse(self._url).path.split("/")[-1])

            self.done.emit(size_str, filename)
        except Exception as exc:
            _log.debug("Info fetch failed: %s", exc)
            self.done.emit("", "")


# ── Dialog ────────────────────────────────────────────────────────────────────

_CATEGORIES = ["Video", "Audio", "Document", "Archive", "Image", "Other"]

_STYLE = """
QDialog   {{ background: {bg}; }}
QLabel    {{ color: {fg}; background: transparent; }}
QLineEdit, QComboBox {{
    background: {bg2}; color: {fg};
    border: 1px solid {border}; border-radius: 5px;
    padding: 5px 8px; font-size: 13px;
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {cyan}; }}
QLineEdit[readOnly="true"] {{ color: {muted}; }}
QComboBox::drop-down {{ border: none; }}
QCheckBox {{ color: {muted}; font-size: 11px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border-radius: 3px;
                        border: 1px solid {border}; background: {bg2}; }}
QCheckBox::indicator:checked {{ background: {cyan}; border-color: {cyan}; }}
QFrame[frameShape="4"] {{ color: {border}; }}
QPushButton {{
    background: {bg2}; color: {fg};
    border: 1px solid {border}; border-radius: 6px;
    padding: 7px 16px; font-size: 13px;
}}
QPushButton:hover  {{ background: #1e2330; }}
QPushButton#Start  {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {cyan}, stop:1 {blue});
    border: none; color: #0A0C11; font-weight: 700; padding: 7px 22px;
}}
QPushButton#Start:hover {{ filter: brightness(1.1); }}
QPushButton#Later  {{ border-color: {green}; color: {green}; }}
QPushButton#Later:hover {{ background: rgba(45,212,160,.1); }}
""".format(
    bg=BG_PRIMARY, bg2=BG_SECONDARY, fg=TEXT_PRIMARY, muted=TEXT_MUTED,
    border=BORDER, cyan=ACCENT_CYAN, blue=ACCENT_BLUE, green=ACCENT_GREEN,
)

ACTION_START = "start"
ACTION_LATER = "later"
ACTION_CANCEL = "cancel"


class DownloadConfirmDialog(QDialog):
    """
    Show download info and let the user confirm before adding to queue.

    After exec():
        if dlg.action == ACTION_START:  add and start immediately
        if dlg.action == ACTION_LATER:  add paused (queued but not running)
        if dlg.action == ACTION_CANCEL: do nothing

    Properties:
        dlg.save_path   — chosen folder
        dlg.category    — chosen category string
        dlg.filename    — suggested filename (may be empty)
    """

    def __init__(self, url: str, suggested_title: str = "",
                 default_save_path: str = "", proxy: str = "", parent=None):
        super().__init__(parent)
        self._url       = url
        self._proxy     = proxy
        self.action     = ACTION_CANCEL
        self.save_path  = default_save_path or str(Path.home() / "Downloads" / "RuneFetch")
        self.category   = "Video"
        self.filename   = ""
        self._fetcher   = None

        self.setWindowTitle("Download File Info")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setStyleSheet(_STYLE)

        self._build(url, suggested_title)
        self._fetch_info()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self, url: str, suggested_title: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(10)

        def row(label_text, widget, extra=None):
            hl = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setFixedWidth(78)
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            hl.addWidget(lbl)
            hl.addWidget(widget, stretch=1)
            if extra:
                hl.addWidget(extra)
            return hl

        # URL
        self._url_edit = QLineEdit(url)
        self._url_edit.setReadOnly(True)
        self._url_edit.setToolTip(url)
        root.addLayout(row("URL", self._url_edit))

        # Category
        self._cat_combo = QComboBox()
        self._cat_combo.addItems(_CATEGORIES)
        self._cat_combo.setCurrentText(_guess_category(url))
        self._cat_combo.currentTextChanged.connect(lambda t: setattr(self, "category", t))
        self.category = self._cat_combo.currentText()
        root.addLayout(row("Category", self._cat_combo))

        # Save As
        self._path_edit = QLineEdit(self.save_path)
        self._path_edit.textChanged.connect(lambda t: setattr(self, "save_path", t))
        browse_btn = QPushButton("…")
        browse_btn.setFixedWidth(34)
        browse_btn.setToolTip("Choose folder")
        browse_btn.clicked.connect(self._browse)
        root.addLayout(row("Save As", self._path_edit, browse_btn))

        # Remember checkbox
        self._remember_cb = QCheckBox(f'Remember this path for "{self._cat_combo.currentText()}"')
        self._cat_combo.currentTextChanged.connect(
            lambda t: self._remember_cb.setText(f'Remember this path for "{t}"')
        )
        self._remember_cb.setContentsMargins(82, 0, 0, 0)
        root.addWidget(self._remember_cb)

        # File info row (size + filename — filled async)
        info_hl = QHBoxLayout()
        info_hl.setContentsMargins(82, 0, 0, 0)
        self._size_lbl = QLabel("Fetching file info…")
        self._size_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        info_hl.addWidget(self._size_lbl)
        info_hl.addStretch()
        root.addLayout(info_hl)

        # Filename (editable)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Filename (auto-detected)")
        self._name_edit.textChanged.connect(lambda t: setattr(self, "filename", t))
        root.addLayout(row("Filename", self._name_edit))

        # Divider
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {BORDER};")
        root.addWidget(sep)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)

        self._later_btn = QPushButton("Download Later")
        self._later_btn.setObjectName("Later")
        self._later_btn.setToolTip("Add to queue but don't start yet")
        self._later_btn.clicked.connect(self._on_later)

        self._start_btn = QPushButton("Start Download")
        self._start_btn.setObjectName("Start")
        self._start_btn.clicked.connect(self._on_start)
        self._start_btn.setDefault(True)

        btn_row.addWidget(self._cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._later_btn)
        btn_row.addWidget(self._start_btn)
        root.addLayout(btn_row)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_start(self):
        self.action    = ACTION_START
        self.save_path = self._path_edit.text().strip() or self.save_path
        self.category  = self._cat_combo.currentText()
        self.filename  = self._name_edit.text().strip()
        self.accept()

    def _on_later(self):
        self.action    = ACTION_LATER
        self.save_path = self._path_edit.text().strip() or self.save_path
        self.category  = self._cat_combo.currentText()
        self.filename  = self._name_edit.text().strip()
        self.accept()

    def _browse(self):
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose download folder", self._path_edit.text()
        )
        if chosen:
            self._path_edit.setText(chosen)

    # ── Async info fetch ──────────────────────────────────────────────────────

    def _fetch_info(self):
        self._fetcher = _InfoFetcher(self._url, self._proxy)
        self._fetcher.done.connect(self._on_info)
        self._fetcher.start()

    def _on_info(self, size_str: str, filename: str):
        if size_str:
            self._size_lbl.setText(f"Size: {size_str}")
        else:
            self._size_lbl.setText("")

        if filename and not self._name_edit.text():
            self._name_edit.setText(filename)
            self.filename = filename


# ── Helpers ───────────────────────────────────────────────────────────────────

def _guess_category(url: str) -> str:
    url_l = url.lower()
    if any(x in url_l for x in ("youtube", "vimeo", "twitch", "tiktok",
                                  "instagram", "reddit", ".mp4", ".mkv",
                                  ".avi", ".mov", ".webm")):
        return "Video"
    if any(x in url_l for x in ("spotify", "soundcloud", "bandcamp",
                                  ".mp3", ".flac", ".wav", ".m4a")):
        return "Audio"
    if any(x in url_l for x in (".pdf", ".docx", ".doc", ".xlsx", ".pptx")):
        return "Document"
    if any(x in url_l for x in (".zip", ".rar", ".7z", ".tar", ".gz")):
        return "Archive"
    if any(x in url_l for x in (".jpg", ".jpeg", ".png", ".gif", ".webp")):
        return "Image"
    return "Video"
