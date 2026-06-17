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

import os
import sys
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QLineEdit, QStackedWidget,
    QScrollArea, QFrame, QSizePolicy, QFileDialog,
    QMessageBox, QComboBox,
)
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSlot
from PyQt6.QtGui import (
    QPainter, QLinearGradient, QColor, QFont,
    QDesktopServices, QMouseEvent,
)
from PyQt6.QtCore import QUrl

from gui.stylesheet import get_stylesheet
from gui.theme import (
    BG_PRIMARY, BG_SECONDARY, BORDER, BORDER_CARD,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_CYAN, ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED,
    GRAD_CYAN_BLUE, GRAD_ORANGE_RED, GRAD_PURPLE_CYAN,
    SIDEBAR_WIDTH, TITLEBAR_HEIGHT, STATUSBAR_HEIGHT,
)
from gui.download_card import DownloadCard
from gui.settings_panel import SettingsPanel
from gui.history_panel import HistoryPanel, append_history

from core.detector import detect, TYPE_DRM
from core.queue_manager import (
    QueueManager, STATE_QUEUED, STATE_DOWNLOADING,
    STATE_COMPLETE, STATE_ERROR, STATE_PAUSED, STATE_CANCELLED,
)
import utils.settings as cfg_mod


POLL_MS = 120

NAV_ITEMS = [
    ("Downloads", "↓"),
    ("History",   "◷"),
    ("Settings",  "⚙"),
]

# Bug 2 fix: Video removed from format group; Audio is now a standalone toggle.
# Quality chips form their own independent group (Best quality is the default).
# Audio toggle ON  → extract audio only (MP3) regardless of source type.
# Audio toggle OFF → extract full content (video+audio for video sources).
AUDIO_TOGGLE_LABEL = "Audio only (MP3)"
QUALITY_CHIPS = ["Best quality", "1080p", "720p", "480p", "360p"]


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
        brand = _GradientLabel("⛩ RuneFetch", GRAD_CYAN_BLUE)
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
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e: QMouseEvent):
        if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
            delta = e.globalPosition().toPoint() - self._drag_pos
            self._win.move(self._win.pos() + delta)
            self._drag_pos = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e: QMouseEvent):
        self._drag_pos = None

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.0, QColor(BG_SECONDARY))
        grad.setColorAt(1.0, QColor(BG_PRIMARY))
        p.fillRect(self.rect(), grad)
        # Bottom border
        p.setPen(QColor(BORDER))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.end()


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
        self._audio_on      = False         # True = extract audio only
        self._selected_qual = "Best quality"

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.resize(860, 640)
        self.setMinimumSize(720, 520)
        self.setWindowTitle("RuneFetch")

        self.setStyleSheet(get_stylesheet())
        self._build_ui()
        self._start_poll()

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
        url_container.setFixedHeight(120)
        uc_layout = QVBoxLayout(url_container)
        uc_layout.setContentsMargins(20, 12, 20, 12)
        uc_layout.setSpacing(8)

        # URL row
        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        self._url_edit = QLineEdit()
        self._url_edit.setObjectName("UrlInput")
        self._url_edit.setPlaceholderText(
            "Paste a link — YouTube, Spotify, direct file, or any of 1000+ sites…"
        )
        self._url_edit.returnPressed.connect(self._on_analyse)
        url_row.addWidget(self._url_edit, stretch=1)

        analyse_btn = QPushButton("  ↓  Add")
        analyse_btn.setObjectName("PrimaryBtn")
        analyse_btn.setFixedWidth(96)
        analyse_btn.clicked.connect(self._on_analyse)
        url_row.addWidget(analyse_btn)
        uc_layout.addLayout(url_row)

        # Chip row — Bug 2 fix
        # Layout: [QUALITY label] [Best quality] [1080p] … [360p]  |  [🎵 Audio toggle]
        # Audio toggle is visually separated at the right — it is independent of
        # the quality group and does not contaminate it.
        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)
        self._chip_btns: dict[str, QPushButton] = {}

        quality_lbl = QLabel("QUALITY")
        quality_lbl.setObjectName("SectionLabel")
        chips_row.addWidget(quality_lbl)

        for chip in QUALITY_CHIPS:
            btn = QPushButton(chip)
            btn.setObjectName("ChipBtn")
            btn.setProperty("active", chip == self._selected_qual)
            btn.clicked.connect(lambda _c, t=chip: self._on_quality_chip(t))
            chips_row.addWidget(btn)
            self._chip_btns[chip] = btn

        chips_row.addStretch()

        # Audio toggle — standalone, visually separated by a small spacer
        sep_lbl = QLabel("|")
        sep_lbl.setStyleSheet("color: #2a2f3d; font-size: 13px; padding: 0 4px;")
        chips_row.addWidget(sep_lbl)

        self._audio_btn = QPushButton("🎵  Audio only")
        self._audio_btn.setObjectName("ChipBtn")
        self._audio_btn.setProperty("active", self._audio_on)
        self._audio_btn.setToolTip(
            "Toggle ON: extract audio only (MP3).\n"
            "Toggle OFF: download full video (or audio if source is audio-only)."
        )
        self._audio_btn.clicked.connect(self._on_audio_toggle)
        chips_row.addWidget(self._audio_btn)

        uc_layout.addLayout(chips_row)

        dl_layout.addWidget(url_container)

        # Queue list section header
        queue_hdr = QWidget()
        queue_hdr.setFixedHeight(32)
        qhl = QHBoxLayout(queue_hdr)
        qhl.setContentsMargins(20, 0, 16, 0)
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

    # ── Chips — Bug 2 fix ────────────────────────────────────────────────────
    # Quality chips and the Audio toggle are completely independent.
    # _on_quality_chip only ever changes _selected_qual.
    # _on_audio_toggle only ever flips _audio_on.
    # They never share state or contaminate each other.

    def _on_quality_chip(self, text: str):
        """Select a quality tier. Audio toggle is unaffected."""
        self._selected_qual = text
        self._refresh_quality_chips()

    def _on_audio_toggle(self):
        """
        Toggle audio-only mode on/off.

        ON:  item.fmt will be set to "Audio only (MP3)" → yt-dlp extracts
             bestaudio and postprocesses to MP3 regardless of source type.
        OFF: item.fmt reflects the content type (video+audio for video sources,
             audio-only for audio-only sources like SoundCloud/Spotify).
        """
        self._audio_on = not self._audio_on
        self._audio_btn.setProperty("active", self._audio_on)
        self._audio_btn.style().unpolish(self._audio_btn)
        self._audio_btn.style().polish(self._audio_btn)
        # Update tooltip to reflect current state
        if self._audio_on:
            self._audio_btn.setToolTip("Audio only ON — will extract MP3. Click to turn off.")
        else:
            self._audio_btn.setToolTip(
                "Audio only OFF — will download full content. Click to turn on."
            )

    def _refresh_quality_chips(self):
        """Refresh only quality chip active states — never touches audio toggle."""
        for text, btn in self._chip_btns.items():
            is_active = (text == self._selected_qual)
            btn.setProperty("active", is_active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ── Analyse & add ────────────────────────────────────────────────────────

    def _on_analyse(self):
        url = self._url_edit.text().strip()
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

        # Determine save path
        save_path = self.cfg.get("save_path", "")
        if self.cfg.get("prompt_per_file", False):
            chosen = QFileDialog.getExistingDirectory(
                self, "Choose save folder for this download", save_path
            )
            if chosen:
                save_path = chosen

        # Bug 2 fix: fmt is derived from the audio toggle, not a format chip group.
        # If audio toggle is ON, always use "Audio only (MP3)".
        # If audio toggle is OFF, use the source's natural type
        # (video sources get video+audio; audio-only sources get audio).
        fmt  = "Audio only (MP3)" if self._audio_on else "Video (MP4)"
        qual = self._selected_qual

        item_id = self.queue.add(
            url          = url,
            title        = info["label"] + " — " + url[:40],
            source_label = info["label"],
            source_icon  = info["icon"],
            fmt          = fmt,
            quality      = qual,
            save_path    = save_path,
            dl_type      = info["type"],
            fragment_threads = self.cfg.get("fragment_threads", 4),
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
        self._cards_layout.addWidget(card)
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

        # Aggregate speed
        total_speed = 0.0
        for i in active:
            spd = i.speed
            if spd:
                try:
                    val, unit = spd.split()
                    v = float(val)
                    if "MB" in unit:   v *= 1024
                    total_speed += v
                except Exception:
                    pass
        spd_str = f"{total_speed/1024:.1f} MB/s" if total_speed >= 1024 else \
                  (f"{total_speed:.0f} KB/s" if total_speed > 0 else "")

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
        import logging, os
        log = logging.getLogger(__name__)

        url   = record.get("url", "").strip()
        fmt   = record.get("fmt", "")
        title = record.get("title", "")

        if not url:
            log.warning("_redownload called with empty URL, ignoring.")
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
