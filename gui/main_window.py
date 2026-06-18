"""
RuneFetch Main Window — production IDM UI.

Layout
──────
  ┌─────────────────────────────────────────────────────┐
  │  Custom titlebar (gradient wordmark + window controls)│
  ├────────┬────────────────────────────────────────────┤
  │        │  URL bar + format/quality chips             │
  │ Side-  │  ─────────────────────────────────────────  │
  │  bar   │  Stacked panels:                            │
  │        │    • Downloads (queue list)                 │
  │        │    • History                                │
  │        │    • Settings                               │
  ├────────┴────────────────────────────────────────────┤
  │  Status bar (active · speed · save path · DwarvenStack│
  └─────────────────────────────────────────────────────┘
"""

import logging
import os
import sys
from datetime import datetime

_log = logging.getLogger(__name__)

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QLineEdit, QStackedWidget,
    QScrollArea, QFrame, QSizePolicy, QFileDialog,
    QMessageBox, QComboBox, QSystemTrayIcon, QMenu, QApplication, QDialog,
)
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSlot
from PyQt6.QtGui import (
    QPainter, QLinearGradient, QColor, QFont,
    QDesktopServices, QMouseEvent, QPixmap, QIcon,
)
from PyQt6.QtCore import QUrl

from gui.stylesheet import get_stylesheet
from gui.theme import (
    BG_PRIMARY, BG_SECONDARY, BORDER, BORDER_CARD,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_CYAN, ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED,
    GRAD_BEIGE_STEEL, GRAD_ORANGE_RED, GRAD_STEEL_BLUE,
    SIDEBAR_WIDTH, TITLEBAR_HEIGHT, STATUSBAR_HEIGHT,
)
from gui.download_card import DownloadCard
from gui.settings_panel import SettingsPanel
from gui.history_panel import HistoryPanel, append_history
from gui.quality_dialog import QualityDialog
from gui.download_confirm_dialog import (
    DownloadConfirmDialog, ACTION_START, ACTION_LATER,
)

from core.detector import detect, TYPE_DRM
from core.queue_manager import (
    QueueManager, STATE_QUEUED, STATE_DOWNLOADING,
    STATE_COMPLETE, STATE_ERROR, STATE_PAUSED, STATE_CANCELLED,
)
from core.bridge import LocalBridge
from core.queue_persistence import save_queue, load_queue
import utils.settings as cfg_mod


POLL_MS = 120

NAV_ITEMS = [
    ("Downloads", "↓"),
    ("History",   "◷"),
    ("Settings",  "⚙"),
]

# Quality is selected per-download via QualityDialog — no static chip list needed.


# ── Custom title bar ────────────────────────────────────────────────────────

class _TitleBar(QWidget):
    """
    Frameless title bar with a gradient RuneFetch wordmark and window controls.
    Supports click-drag to move the window.
    """

    def __init__(self, parent: QMainWindow):
        super().__init__(parent)
        self._win = parent
        self._drag_pos = None
        self.setFixedHeight(TITLEBAR_HEIGHT)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(8)

        # Wordmark — painted as a gradient label
        brand = _GradientLabel("⛩ RuneFetch", GRAD_BEIGE_STEEL)
        brand.setStyleSheet(
            "font-size: 15px; font-weight: 800; letter-spacing: 1px; background: transparent;"
        )
        layout.addWidget(brand)

        by = QLabel("by DwarvenStack")
        by.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
        layout.addWidget(by)

        layout.addStretch()

        # Window control buttons
        for icon, slot, tip in [
            ("─", self._win.showMinimized, "Minimise"),
            ("□", self._toggle_max, "Maximise"),
            ("✕", self._win.close, "Close"),
        ]:
            btn = QPushButton(icon)
            btn.setToolTip(tip)
            btn.setFixedSize(QSize(32, 26))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {TEXT_MUTED};
                    border: none; font-size: 13px;
                    border-radius: 5px;
                }}
                QPushButton:hover {{
                    background: {'#ff453a22' if icon == '✕' else '#ffffff18'};
                    color: {'#ff453a' if icon == '✕' else '{TEXT_PRIMARY}'};
                }}
            """)
            btn.clicked.connect(slot)
            layout.addWidget(btn)

    def _toggle_max(self):
        if self._win.isMaximized():
            self._win.showNormal()
        else:
            self._win.showMaximized()

    # Drag to move
    def mousePressEvent(self, e: QMouseEvent):
        try:
            if e.button() == Qt.MouseButton.LeftButton:
                self._drag_pos = e.globalPosition().toPoint()
        except Exception as exc:
            _log.error("TitleBar mousePressEvent: %s", exc)

    def mouseMoveEvent(self, e: QMouseEvent):
        try:
            if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
                delta = e.globalPosition().toPoint() - self._drag_pos
                self._win.move(self._win.pos() + delta)
                self._drag_pos = e.globalPosition().toPoint()
        except Exception as exc:
            _log.error("TitleBar mouseMoveEvent: %s", exc)

    def mouseReleaseEvent(self, e: QMouseEvent):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, e: QMouseEvent):
        try:
            if e.button() == Qt.MouseButton.LeftButton:
                self._toggle_max()
        except Exception as exc:
            _log.error("TitleBar mouseDoubleClickEvent: %s", exc)

    def paintEvent(self, _event):
        try:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            grad = QLinearGradient(0, 0, self.width(), 0)
            grad.setColorAt(0.0, QColor(BG_SECONDARY))
            grad.setColorAt(1.0, QColor(BG_PRIMARY))
            p.fillRect(self.rect(), grad)
            p.setPen(QColor(BORDER))
            p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
            p.end()
        except Exception as exc:
            _log.error("TitleBar paintEvent: %s", exc)


class _GradientLabel(QLabel):
    """A QLabel whose text is painted with a horizontal gradient."""

    def __init__(self, text: str, gradient: tuple, parent=None):
        super().__init__(text, parent)
        self._g = gradient

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.0, QColor(self._g[0]))
        grad.setColorAt(1.0, QColor(self._g[1]))
        p.setPen(QColor(self._g[0]))   # fallback
        # Use clipPath for text — paint gradient rect then mask with text
        from PyQt6.QtGui import QPainterPath
        path = QPainterPath()
        path.addText(0, self.fontMetrics().ascent(), self.font(), self.text())
        p.setBrush(grad)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(path)
        p.end()


# ── Main window ─────────────────────────────────────────────────────────────

class RuneFetchWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.cfg   = cfg_mod.load()
        self.queue = QueueManager(
            max_concurrent=self.cfg.get("max_concurrent", 2),
            throttle_kbps =self.cfg.get("throttle_kbps", 0),
        )
        self._cards: dict[str, DownloadCard] = {}
        self._active_nav = "Downloads"
        # Bug 2 fix: Audio is a toggle (bool), quality is the only chip group

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.resize(860, 640)
        self.setMinimumSize(720, 520)
        self.setWindowTitle("RuneFetch")

        # Set window + taskbar icon from assets if available
        import pathlib
        _icon_path = pathlib.Path(__file__).parent.parent / "assets" / "runefetch_icon.png"
        if _icon_path.exists():
            self.setWindowIcon(QIcon(str(_icon_path)))

        self.setStyleSheet(get_stylesheet())
        self._build_ui()
        self._start_poll()
        self._setup_tray()
        self._setup_bridge()
        self._setup_clipboard_monitor()
        self._restore_queue()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Title bar
        self._titlebar = _TitleBar(self)
        root.addWidget(self._titlebar)

        # Body (sidebar + content)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._build_sidebar(body)
        self._build_content_area(body)

        root.addLayout(body, stretch=1)
        self._build_statusbar(root)

    def _build_sidebar(self, parent_layout):
        sb = QWidget()
        sb.setObjectName("Sidebar")
        sb.setFixedWidth(SIDEBAR_WIDTH)
        sb_layout = QVBoxLayout(sb)
        sb_layout.setContentsMargins(8, 14, 8, 14)
        sb_layout.setSpacing(2)

        self._nav_buttons: dict[str, QPushButton] = {}
        for label, icon in NAV_ITEMS:
            btn = QPushButton(f"  {icon}  {label}")
            btn.setObjectName("NavBtn")
            btn.setProperty("active", label == self._active_nav)
            btn.setCheckable(False)
            btn.clicked.connect(lambda checked, lbl=label: self._on_nav(lbl))
            sb_layout.addWidget(btn)
            self._nav_buttons[label] = btn

        sb_layout.addStretch()

        # Footer link
        foot = QLabel('<a href="https://github.com/dwarvenstack" '
                      'style="color: #4a5070; text-decoration: none; font-size: 10px;">'
                      '⛩ DwarvenStack</a>')
        foot.setOpenExternalLinks(True)
        foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        foot.setWordWrap(True)
        sb_layout.addWidget(foot)

        parent_layout.addWidget(sb)

    def _build_content_area(self, parent_layout):
        self._stack = QStackedWidget()
        self._stack.setObjectName("ContentPanel")

        # ── Page 0: Downloads ────────────────────────────────────────────
        dl_page = QWidget()
        dl_page.setObjectName("ContentPanel")
        dl_layout = QVBoxLayout(dl_page)
        dl_layout.setContentsMargins(0, 0, 0, 0)
        dl_layout.setSpacing(0)

        # URL section
        url_container = QWidget()
        url_container.setObjectName("PanelHeader")
        uc_layout = QVBoxLayout(url_container)
        uc_layout.setContentsMargins(20, 14, 20, 10)
        uc_layout.setSpacing(6)

        # URL row
        url_row = QHBoxLayout()
        url_row.setSpacing(10)
        self._url_edit = QLineEdit()
        self._url_edit.setObjectName("UrlInput")
        self._url_edit.setPlaceholderText(
            "Drop a link here — YouTube, Spotify, or any of 1000+ sites…"
        )
        self._url_edit.returnPressed.connect(self._on_analyse)
        url_row.addWidget(self._url_edit, stretch=1)

        analyse_btn = QPushButton("↓  Add")
        analyse_btn.setObjectName("PrimaryBtn")
        analyse_btn.setFixedWidth(100)
        from gui.theme import TEXT_ON_ACCENT
        analyse_btn.setStyleSheet(
            f"QPushButton#PrimaryBtn {{ color: {TEXT_ON_ACCENT}; font-weight: 700; }}"
        )
        analyse_btn.clicked.connect(self._on_analyse)
        url_row.addWidget(analyse_btn)
        uc_layout.addLayout(url_row)

        hint_lbl = QLabel("Format & quality are chosen for each download — just paste and go.")
        hint_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; padding-left: 2px;")
        uc_layout.addWidget(hint_lbl)

        dl_layout.addWidget(url_container)

        # Queue list section header
        queue_hdr = QWidget()
        queue_hdr.setFixedHeight(36)
        qhl = QHBoxLayout(queue_hdr)
        qhl.setContentsMargins(20, 0, 20, 0)
        ql_lbl = QLabel("DOWNLOAD QUEUE")
        ql_lbl.setObjectName("SectionLabel")
        qhl.addWidget(ql_lbl, stretch=1)

        self._queue_count_lbl = QLabel("")
        self._queue_count_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        qhl.addWidget(self._queue_count_lbl)

        clear_all_btn = QPushButton("Clear all")
        clear_all_btn.setObjectName("SecondaryBtn")
        clear_all_btn.clicked.connect(self._clear_all)
        qhl.addWidget(clear_all_btn)
        dl_layout.addWidget(queue_hdr)

        # Scrollable card list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._cards_container = QWidget()
        self._cards_container.setStyleSheet("background: transparent;")
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(16, 8, 16, 16)
        self._cards_layout.setSpacing(8)
        self._cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Empty-state label
        self._empty_lbl = QLabel(
            "Paste a URL above and press Enter to start downloading"
        )
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; padding: 60px;")
        self._cards_layout.addWidget(self._empty_lbl)

        scroll.setWidget(self._cards_container)
        dl_layout.addWidget(scroll, stretch=1)

        self._stack.addWidget(dl_page)   # index 0

        # ── Page 1: History ──────────────────────────────────────────────
        self._history_panel = HistoryPanel()
        self._history_panel.redownload_requested.connect(self._redownload)  # receives dict
        self._stack.addWidget(self._history_panel)   # index 1

        # ── Page 2: Settings ─────────────────────────────────────────────
        self._settings_panel = SettingsPanel(self.cfg)
        self._settings_panel.saved.connect(self._on_settings_saved)
        self._stack.addWidget(self._settings_panel)  # index 2

        parent_layout.addWidget(self._stack, stretch=1)

    def _build_statusbar(self, parent_layout):
        bar = QWidget()
        bar.setFixedHeight(STATUSBAR_HEIGHT)
        bar.setStyleSheet(
            f"background: {BG_SECONDARY}; border-top: 1px solid {BORDER};"
        )
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 0, 16, 0)

        self._status_lbl = QLabel("● Ready")
        self._status_lbl.setObjectName("FooterLabel")
        bl.addWidget(self._status_lbl)

        bl.addStretch()

        self._speed_total_lbl = QLabel("")
        self._speed_total_lbl.setObjectName("FooterLabel")
        bl.addWidget(self._speed_total_lbl)

        sep = QLabel("·")
        sep.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        bl.addWidget(sep)

        self._path_lbl = QLabel(self.cfg.get("save_path", ""))
        self._path_lbl.setObjectName("FooterLabel")
        bl.addWidget(self._path_lbl)

        sep2 = QLabel("·")
        sep2.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        bl.addWidget(sep2)

        dw_link = QLabel(
            '<a href="https://github.com/dwarvenstack" '
            'style="color: #4a5070; text-decoration: none;">'
            'More free apps → DwarvenStack</a>'
        )
        dw_link.setOpenExternalLinks(True)
        dw_link.setObjectName("FooterLabel")
        bl.addWidget(dw_link)

        parent_layout.addWidget(bar)

    # ── Nav ──────────────────────────────────────────────────────────────────

    def _on_nav(self, label: str):
        self._active_nav = label
        page_map = {"Downloads": 0, "History": 1, "Settings": 2}
        self._stack.setCurrentIndex(page_map.get(label, 0))

        if label == "History":
            self._history_panel.reload()

        # Update button styles
        for lbl, btn in self._nav_buttons.items():
            btn.setProperty("active", lbl == label)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # Quality is now handled per-download via QualityDialog — no chip state needed.

    # ── Analyse & add ────────────────────────────────────────────────────────

    def _on_analyse(self):
        url = self._url_edit.text().strip()
        if url:
            self._on_analyse_url(url)

    def _show_download_confirm(self, url: str, suggested_title: str = ""):
        """Show IDM-style confirmation dialog when a URL arrives from the extension."""
        _log.info("Extension URL received: %s", url[:80])

        # Bring window to front so the dialog is visible
        self.show()
        self.raise_()
        self.activateWindow()

        dlg = DownloadConfirmDialog(
            url              = url,
            suggested_title  = suggested_title,
            default_save_path= self.cfg.get("save_path", ""),
            proxy            = self.cfg.get("proxy", ""),
            parent           = self,
        )
        result = dlg.exec()
        if result != QDialog.DialogCode.Accepted or dlg.action == "cancel":
            _log.debug("Extension download cancelled by user")
            return

        # Override save path with user's choice from the dialog
        save_path = dlg.save_path or self.cfg.get("save_path", "")

        # Add to queue — with pause pre-cleared if "Download Later"
        self._on_analyse_url(
            url,
            suggested_title = suggested_title,
            _save_path      = save_path,
            _start_paused   = (dlg.action == ACTION_LATER),
        )

    def _on_analyse_url(self, url: str, suggested_title: str = "",
                        _save_path: str = "", _start_paused: bool = False):
        """Core add-to-queue logic shared by URL bar, bridge, and clipboard."""
        if not url:
            return

        info = detect(url)

        if info["type"] == TYPE_DRM:
            QMessageBox.warning(
                self, "DRM-Protected Content",
                f"<b>{info['label']}</b> uses Widevine DRM encryption.<br><br>"
                "This content cannot be downloaded by any third-party tool.<br>"
                "Please use the official app's built-in download/offline feature.",
            )
            return

        # Determine save path — _save_path pre-set by confirm dialog takes priority
        save_path = _save_path or self.cfg.get("save_path", "")
        if not _save_path and self.cfg.get("prompt_per_file", False):
            chosen = QFileDialog.getExistingDirectory(
                self, "Choose save folder for this download", save_path
            )
            if chosen:
                save_path = chosen

        from core.detector import TYPE_YOUTUBE, TYPE_YTDLP, TYPE_DIRECT, TYPE_SPOTIFY
        dl_type = info["type"]

        # For video/yt-dlp sources: show quality selection dialog
        # For direct files and Spotify: no quality choice needed
        fmt  = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
        qual = "Best quality"

        if dl_type in (TYPE_YOUTUBE, TYPE_YTDLP):
            default_title = suggested_title or info["label"]
            dlg = QualityDialog(
                url            = url,
                suggested_title= default_title,
                is_playlist    = info.get("is_playlist", False),
                proxy          = self.cfg.get("proxy", ""),
                parent         = self,
            )
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return   # user cancelled
            fmt, is_audio, qual = dlg.selected_format()
        elif dl_type == TYPE_SPOTIFY:
            fmt  = "Audio only (MP3)"
            qual = "Best quality"
        else:
            # Direct file — no quality selection
            fmt  = "Video (MP4)"
            qual = "Best quality"

        default_title = suggested_title or (info["label"] + " — " + url[:40])
        item_id = self.queue.add(
            url          = url,
            title        = default_title,
            source_label = info["label"],
            source_icon  = info["icon"],
            fmt          = fmt,
            quality      = qual,
            save_path    = save_path,
            dl_type      = info["type"],
            fragment_threads = self.cfg.get("fragment_threads", 4),
            proxy        = self.cfg.get("proxy", ""),
            start_paused = _start_paused,
        )

        self._url_edit.clear()
        self._ensure_card(item_id)

        # Switch to Downloads tab
        if self._active_nav != "Downloads":
            self._on_nav("Downloads")

    # ── Card management ──────────────────────────────────────────────────────

    def _ensure_card(self, item_id: str):
        if item_id in self._cards:
            return
        item = next((i for i in self.queue.get_items() if i.id == item_id), None)
        if not item:
            return
        if self._empty_lbl.isVisible():
            self._empty_lbl.hide()
        card = DownloadCard(item, self.queue, self.cfg, self._cards_container)
        card.deleted.connect(self._on_card_deleted)
        self._cards_layout.insertWidget(0, card)   # newest/active always on top
        self._cards[item_id] = card

    def _on_card_deleted(self, item_id: str):
        # Card widget already called queue.remove() and setParent(None)/deleteLater()
        # We just need to clean our bookkeeping dict and update empty state
        self._cards.pop(item_id, None)
        self._update_empty_state()

    def _clear_all(self):
        for item_id in list(self._cards.keys()):
            card = self._cards.pop(item_id, None)
            if card and not card._being_deleted:
                card._being_deleted = True
                self.queue.remove(item_id)
                card.hide()
                card.setParent(None)
                card.deleteLater()
        self._update_empty_state()

    def _update_empty_state(self):
        has_cards = bool(self._cards)
        self._empty_lbl.setVisible(not has_cards)

    # ── Poll loop ────────────────────────────────────────────────────────────

    def _start_poll(self):
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(POLL_MS)

    def _poll(self):
        # Drain URLs arriving from the browser extension bridge
        if hasattr(self, "_bridge") and self._bridge:
            while not self._bridge.incoming.empty():
                try:
                    url, title = self._bridge.incoming.get_nowait()
                    self._show_download_confirm(url, title)
                except Exception:
                    pass

        events = self.queue.poll_events()
        all_items = {i.id: i for i in self.queue.get_items()}
        for item_id in events:
            if item_id is None:
                continue
            # Only create/refresh cards for items still in the queue
            if item_id not in all_items:
                # Item was removed — clean up any lingering card reference
                card = self._cards.pop(item_id, None)
                if card and not card._being_deleted:
                    card._being_deleted = True
                    card.hide()
                    card.setParent(None)
                    card.deleteLater()
                continue
            self._ensure_card(item_id)
            card = self._cards.get(item_id)
            if card:
                item = all_items[item_id]
                card.refresh(item)
                # Append log events from item's log_lines queue
                while item._log_lines:
                    line, colour = item._log_lines.pop(0)
                    card.log(line, colour)
                # Record completion in history
                if item.state == STATE_COMPLETE:
                    self._record_history(item)

        # Status bar
        items  = self.queue.get_items()
        active = [i for i in items if i.state == STATE_DOWNLOADING]
        queued = [i for i in items if i.state == STATE_QUEUED]
        total  = len(items)

        # Aggregate speed using numeric field (avoids re-parsing formatted strings)
        total_bps = sum(i.speed_bps for i in active)
        if total_bps >= 1_048_576:
            spd_str = f"{total_bps/1_048_576:.1f} MB/s"
        elif total_bps >= 1024:
            spd_str = f"{total_bps/1024:.0f} KB/s"
        else:
            spd_str = f"{total_bps:.0f} B/s" if total_bps > 0 else ""

        if active:
            self._status_lbl.setText(
                f"● Downloading  {len(active)} active · {len(queued)} queued"
            )
            self._status_lbl.setStyleSheet(f"color: {ACCENT_CYAN}; font-size: 11px;")
        elif queued:
            self._status_lbl.setText(f"● {len(queued)} queued")
            self._status_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        else:
            self._status_lbl.setText("● Ready")
            self._status_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")

        self._speed_total_lbl.setText(spd_str)
        self._path_lbl.setText(self.cfg.get("save_path", ""))
        self._queue_count_lbl.setText(
            f"{total} item{'s' if total != 1 else ''}" if total else ""
        )

        # Update tray tooltip with live status
        if hasattr(self, "_tray"):
            if active:
                tip = f"RuneFetch — {len(active)} downloading"
                if spd_str:
                    tip += f"  {spd_str}"
            elif queued:
                tip = f"RuneFetch — {len(queued)} queued"
            else:
                tip = "RuneFetch — idle"
            self._tray.setToolTip(tip)

    # ── History recording ────────────────────────────────────────────────────

    def _record_history(self, item):
        """Write a completed item to history (idempotent via _recorded set)."""
        if not hasattr(self, "_recorded"):
            self._recorded: set = set()
        if item.id in self._recorded:
            return
        if not self.cfg.get("keep_history", True):
            return
        self._recorded.add(item.id)
        # Normalise format label
        fmt = item.fmt or ""
        if "audio" in fmt.lower() or "mp3" in fmt.lower():
            fmt_display = "MP3"
        elif "mp4" in fmt.lower() or "video" in fmt.lower():
            fmt_display = "MP4"
        else:
            fmt_display = fmt or "—"
        append_history({
            "title":        item.title,
            "url":          item.url,
            "source_label": item.source_label,
            "fmt":          fmt_display,
            "size":         item.size if item.size else "—",
            "state":        item.state,
            "date":         datetime.now().strftime("%Y-%m-%d %H:%M"),
            # Bug 3 fix: store save_path so redownload can check for existing files
            "save_path":    item.save_path,
        })

    # ── Redownload from history ──────────────────────────────────────────────

    @pyqtSlot(dict)
    def _redownload(self, record: dict):
        """
        Bug 3 fix: previously accepted a bare str URL and called _on_analyse(),
        which triggered maybe_run_setup() → run_wizard() → app.exec(), opening
        a new setup wizard that blocked the main window (visible as 3% stall).

        Fixes applied:
        1. Accepts a dict (url, fmt, save_path, title) from history panel.
        2. Checks whether the file already exists in the save folder before
           queueing — if found, informs the user and offers to open the folder
           instead of re-downloading.
        3. Restores the original fmt/quality from the history record so the
           redownload uses the same settings as the original download.
        4. Does NOT call _on_analyse() — constructs the queue.add() call
           directly to avoid any side-effects from the URL analysis path.
        """
        url   = record.get("url", "").strip()
        fmt   = record.get("fmt", "")
        title = record.get("title", "")

        if not url:
            _log.warning("_redownload called with empty URL, ignoring.")
            return

        save_path = record.get("save_path", "") or self.cfg.get("save_path", "")

        # ── Existing-file detection ─────────────────────────────────────────
        # Check if any file matching the title already exists in save_path.
        # This prevents pointless re-downloads and handles the "already exists"
        # edge case that yt-dlp would silently skip, showing 3% forever.
        if save_path and title and os.path.isdir(save_path):
            # Normalise title to match likely filename patterns
            safe_title = title[:60].replace("/", "_").replace("\\", "_")
            existing = [
                f for f in os.listdir(save_path)
                if safe_title.lower()[:20] in f.lower()
            ]
            if existing:
                reply = QMessageBox.question(
                    self,
                    "File Already Exists",
                    f"<b>{existing[0]}</b><br><br>"
                    f"This file already exists in your downloads folder.<br>"
                    f"Do you want to download it again?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.No:
                    # Open the folder so the user can find the file
                    import subprocess, sys as _sys
                    try:
                        if _sys.platform == "win32":
                            os.startfile(save_path)
                        elif _sys.platform == "darwin":
                            subprocess.Popen(["open", save_path])
                        else:
                            subprocess.Popen(["xdg-open", save_path])
                    except Exception as e:
                        log.warning(f"Could not open folder: {e}")
                    return

        # ── Restore fmt/quality from history ────────────────────────────────
        # Map stored display label back to internal fmt string
        fmt_lower = fmt.lower()
        if "mp3" in fmt_lower or "audio" in fmt_lower:
            resolved_fmt  = "Audio only (MP3)"
            resolved_qual = "Best quality"
        else:
            resolved_fmt  = "Video (MP4)"
            resolved_qual = "Best quality"

        # ── Detect source type ───────────────────────────────────────────────
        info = detect(url)
        if info["type"] == TYPE_DRM:
            QMessageBox.warning(
                self, "DRM-Protected Content",
                f"<b>{info['label']}</b> uses DRM encryption and cannot be downloaded.",
            )
            return

        # ── Queue directly — no _on_analyse() call ───────────────────────────
        item_id = self.queue.add(
            url              = url,
            title            = title or (info["label"] + " — " + url[:40]),
            source_label     = info["label"],
            source_icon      = info["icon"],
            fmt              = resolved_fmt,
            quality          = resolved_qual,
            save_path        = save_path,
            dl_type          = info["type"],
            fragment_threads = self.cfg.get("fragment_threads", 4),
            proxy            = self.cfg.get("proxy", ""),
        )
        log.info(f"Re-queued from history: {url} (fmt={resolved_fmt})")

        self._on_nav("Downloads")
        self._ensure_card(item_id)

    # ── Settings saved ───────────────────────────────────────────────────────

    def _on_settings_saved(self):
        self.cfg = cfg_mod.load()
        self.queue.set_concurrency(self.cfg.get("max_concurrent", 2))
        self.queue.set_throttle(self.cfg.get("throttle_kbps", 0))
        self._path_lbl.setText(self.cfg.get("save_path", ""))

    # ── Bridge (Phase 2) ─────────────────────────────────────────────────────

    def _setup_bridge(self):
        from utils.settings import get_or_create_bridge_token
        token = get_or_create_bridge_token(self.cfg)
        port  = self.cfg.get("bridge_port", 8765)
        self._bridge = LocalBridge(token=token, port=port)
        self._bridge.start()

    # ── Clipboard monitor (Phase 4) ───────────────────────────────────────────

    def _setup_clipboard_monitor(self):
        self._last_clip_url = ""
        clip = QApplication.clipboard()
        clip.dataChanged.connect(self._on_clipboard_changed)

    def _on_clipboard_changed(self):
        if not self.cfg.get("clipboard_monitor", False):
            return
        text = QApplication.clipboard().text().strip()
        if not text.startswith(("http://", "https://")):
            return
        if text == self._last_clip_url:
            return
        self._last_clip_url = text
        # Auto-fill URL bar when on Downloads tab; tray notification otherwise
        if self._active_nav == "Downloads" and self.isVisible():
            self._url_edit.setText(text)
        elif hasattr(self, "_tray") and self._tray.isVisible():
            self._tray.showMessage(
                "RuneFetch — URL detected",
                text[:80] + ("…" if len(text) > 80 else ""),
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
            self._tray.messageClicked.connect(
                lambda: (self._tray_restore(), self._url_edit.setText(text))
            )

    # ── Queue persistence (Phase 4) ───────────────────────────────────────────

    def _restore_queue(self):
        """Re-queue items that were pending/active when the app last closed."""
        if not self.cfg.get("autostart", True):
            return
        from core.detector import detect
        for rec in load_queue():
            url = rec.get("url", "")
            if not url:
                continue
            try:
                info = detect(url)
                item_id = self.queue.add(
                    url          = url,
                    title        = rec.get("title", url[:40]),
                    source_label = rec.get("source_label", info["label"]),
                    source_icon  = rec.get("source_icon", info["icon"]),
                    fmt          = rec.get("fmt", "Video (MP4)"),
                    quality      = rec.get("quality", "Best quality"),
                    save_path    = rec.get("save_path", self.cfg.get("save_path", "")),
                    dl_type      = rec.get("dl_type", info["type"]),
                    fragment_threads = rec.get("fragment_threads", 4),
                    proxy        = rec.get("proxy", self.cfg.get("proxy", "")),
                )
                self._ensure_card(item_id)
            except Exception:
                pass

    # ── System tray ──────────────────────────────────────────────────────────

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(self._make_tray_icon())
        self._tray.setToolTip("RuneFetch")

        menu = QMenu()
        self._tray_open_action   = menu.addAction("Open RuneFetch")
        menu.addSeparator()
        self._tray_pause_action  = menu.addAction("Pause all")
        self._tray_resume_action = menu.addAction("Resume all")
        menu.addSeparator()
        quit_action = menu.addAction("Quit RuneFetch")

        self._tray_open_action.triggered.connect(self._tray_restore)
        self._tray_pause_action.triggered.connect(self._pause_all)
        self._tray_resume_action.triggered.connect(self._resume_all)
        quit_action.triggered.connect(self._tray_quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

        self._tray_first_hide = True

    def _make_tray_icon(self) -> QIcon:
        """Load icon from assets/runefetch_icon.png; fall back to a cyan circle."""
        import pathlib
        icon_path = pathlib.Path(__file__).parent.parent / "assets" / "runefetch_icon.png"
        if icon_path.exists():
            return QIcon(str(icon_path))
        # Fallback: programmatic cyan circle
        px = QPixmap(16, 16)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(ACCENT_CYAN))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(1, 1, 14, 14)
        p.end()
        return QIcon(px)

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self._tray_restore()

    def _tray_restore(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        # Resume animations/poll (poll timer is always running; waveforms resume on show)

    def _tray_quit(self):
        self._shutdown()
        QApplication.instance().quit()

    def _pause_all(self):
        for item in self.queue.get_items():
            self.queue.pause(item.id)

    def _resume_all(self):
        for item in self.queue.get_items():
            self.queue.resume(item.id)

    # ── Mouse-based edge resize ───────────────────────────────────────────────

    _RESIZE_MARGIN = 7   # px detection border
    _resize_dir    = None
    _resize_origin = None
    _resize_geom   = None

    def _edge_at(self, pos):
        """Return a string like 'left', 'bottom-right', etc., or None."""
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        m    = self._RESIZE_MARGIN
        on_l = x <= m;  on_r = x >= w - m
        on_t = y <= m;  on_b = y >= h - m
        if on_t and on_l:  return "top-left"
        if on_t and on_r:  return "top-right"
        if on_b and on_l:  return "bottom-left"
        if on_b and on_r:  return "bottom-right"
        if on_l:           return "left"
        if on_r:           return "right"
        if on_t:           return "top"
        if on_b:           return "bottom"
        return None

    _CURSOR_MAP = {
        "left":         Qt.CursorShape.SizeHorCursor,
        "right":        Qt.CursorShape.SizeHorCursor,
        "top":          Qt.CursorShape.SizeVerCursor,
        "bottom":       Qt.CursorShape.SizeVerCursor,
        "top-left":     Qt.CursorShape.SizeFDiagCursor,
        "bottom-right": Qt.CursorShape.SizeFDiagCursor,
        "top-right":    Qt.CursorShape.SizeBDiagCursor,
        "bottom-left":  Qt.CursorShape.SizeBDiagCursor,
    }

    def mousePressEvent(self, e):
        try:
            if e.button() == Qt.MouseButton.LeftButton:
                edge = self._edge_at(e.position().toPoint())
                if edge:
                    self._resize_dir    = edge
                    self._resize_origin = e.globalPosition().toPoint()
                    self._resize_geom   = self.geometry()
                    e.accept()
                    return
        except Exception as exc:
            _log.error("Window mousePressEvent: %s", exc)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        try:
            if self._resize_dir and e.buttons() == Qt.MouseButton.LeftButton:
                gpos  = e.globalPosition().toPoint()
                dx    = gpos.x() - self._resize_origin.x()
                dy    = gpos.y() - self._resize_origin.y()
                geo   = self._resize_geom
                x, y, w, h = geo.x(), geo.y(), geo.width(), geo.height()
                minw, minh = self.minimumWidth(), self.minimumHeight()
                d = self._resize_dir

                if "right"  in d: w = max(minw, geo.width()  + dx)
                if "bottom" in d: h = max(minh, geo.height() + dy)
                if "left"   in d:
                    nw = max(minw, geo.width() - dx)
                    x  = geo.right() - nw + 1
                    w  = nw
                if "top"    in d:
                    nh = max(minh, geo.height() - dy)
                    y  = geo.bottom() - nh + 1
                    h  = nh

                self.setGeometry(x, y, w, h)
                e.accept()
                return

            edge = self._edge_at(e.position().toPoint())
            cursor = self._CURSOR_MAP.get(edge, Qt.CursorShape.ArrowCursor)
            self.setCursor(cursor)
        except Exception as exc:
            _log.error("Window mouseMoveEvent: %s", exc)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        try:
            if self._resize_dir:
                self._resize_dir    = None
                self._resize_origin = None
                self._resize_geom   = None
                self.setCursor(Qt.CursorShape.ArrowCursor)
                e.accept()
                return
        except Exception as exc:
            _log.error("Window mouseReleaseEvent: %s", exc)
        super().mouseReleaseEvent(e)

    def closeEvent(self, event):
        """Close button behaviour: minimise to tray (default) or quit."""
        use_tray = (
            self.cfg.get("close_to_tray", True)
            and hasattr(self, "_tray")
            and self._tray.isVisible()
        )
        if use_tray:
            event.ignore()
            self.hide()
            if getattr(self, "_tray_first_hide", True):
                self._tray_first_hide = False
                self._tray.showMessage(
                    "RuneFetch",
                    "RuneFetch is still running in the system tray.\n"
                    "Right-click the tray icon to quit.",
                    QSystemTrayIcon.MessageIcon.Information,
                    4000,
                )
        else:
            self._shutdown()
            event.accept()

    def _shutdown(self):
        """Save queue state and stop background services before exit."""
        save_queue(self.queue.get_items())
        if hasattr(self, "_bridge") and self._bridge:
            self._bridge.stop()
