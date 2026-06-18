"""
Quality selection dialog — shown before every yt-dlp / YouTube download.

Flow:
  1. Dialog opens immediately; background thread fetches available formats.
  2. On success: shows actual available resolutions for this specific video.
  3. On timeout (15 s) or error: shows a standard quality list and lets yt-dlp
     pick the closest available match.
  4. Playlists skip fetching and go straight to the standard list.
"""

import logging

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QButtonGroup, QRadioButton, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont

_log = logging.getLogger(__name__)

from gui.theme import (
    BG_PRIMARY, BG_SECONDARY, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_CYAN, ACCENT_BLUE, BORDER,
)

# Standard fallback list — yt-dlp will find the closest available match
FALLBACK_QUALITIES = [
    ("Best quality (auto)",   "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best", False),
    ("1080p HD",              "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best", False),
    ("720p HD",               "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best",  False),
    ("480p",                  "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]/best",  False),
    ("360p",                  "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best[height<=360]/best",  False),
    ("Audio only (MP3 320k)", "bestaudio/best", True),
]


# ── Background format fetcher ─────────────────────────────────────────────────

class _FormatFetcher(QThread):
    ready  = pyqtSignal(list, str)   # formats, video title
    failed = pyqtSignal(str)

    def __init__(self, url: str, proxy: str = ""):
        super().__init__()
        self.url   = url
        self.proxy = proxy

    def run(self):
        try:
            import yt_dlp
            opts = {"quiet": True, "no_warnings": True, "skip_download": True}
            if self.proxy:
                opts["proxy"] = self.proxy
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                formats = info.get("formats") or []
                title   = info.get("title", "")
                self.ready.emit(formats, title)
        except Exception as exc:
            _log.warning("Format fetch failed for %s: %s", self.url[:60], exc)
            self.failed.emit(str(exc))


# ── Dialog ────────────────────────────────────────────────────────────────────

_DIALOG_STYLE = """
QDialog  {{ background: {bg}; }}
QLabel   {{ color: {fg}; background: transparent; }}
QFrame[frameShape="4"] {{ color: {border}; }}
QPushButton {{
    background: {bg2}; color: {fg};
    border: 1px solid {border}; border-radius: 6px;
    padding: 7px 18px; font-size: 13px;
}}
QPushButton:hover {{ background: #1e2330; }}
QPushButton#DlBtn {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {cyan}, stop:1 {blue});
    border: none; color: #fff; font-weight: 700;
    padding: 7px 22px;
}}
QPushButton#DlBtn:hover {{ opacity: 0.9; }}
QPushButton#DlBtn:disabled {{ background: #2a2f3d; color: #4a5070; }}
QRadioButton {{
    color: {fg}; background: transparent;
    spacing: 10px; font-size: 13px; padding: 4px 0;
}}
QRadioButton::indicator {{
    width: 16px; height: 16px; border-radius: 8px;
    border: 2px solid #3a4060;
}}
QRadioButton::indicator:checked {{
    background: {cyan}; border: 2px solid {cyan};
}}
QRadioButton:hover {{ color: {cyan}; }}
""".format(
    bg=BG_PRIMARY, bg2=BG_SECONDARY, fg=TEXT_PRIMARY,
    border=BORDER, cyan=ACCENT_CYAN, blue=ACCENT_BLUE,
)


class QualityDialog(QDialog):
    """
    Show available download qualities and return the user's choice.

    After exec():
        fmt_str, is_audio = dlg.selected_format()
        # fmt_str is a yt-dlp format selector string
        # is_audio is True if audio-only was chosen
    """

    def __init__(self, url: str, suggested_title: str = "",
                 is_playlist: bool = False, proxy: str = "", parent=None):
        super().__init__(parent)
        self._url         = url
        self._proxy       = proxy
        self._is_playlist = is_playlist
        self._fmt_str     = FALLBACK_QUALITIES[0][1]
        self._is_audio    = False
        self._qual_label  = FALLBACK_QUALITIES[0][0]
        self._fetcher     = None
        self._dot_n       = 0

        self.setWindowTitle("Choose Download Quality")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setStyleSheet(_DIALOG_STYLE)

        self._build(suggested_title)

        if is_playlist:
            self._show_options(
                "Playlist — quality applies to all videos:",
                FALLBACK_QUALITIES,
            )
        else:
            self._start_fetch()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self, suggested_title: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 16)
        root.setSpacing(10)

        # Header
        hdr = QLabel("Select Quality")
        hdr.setStyleSheet("font-size: 15px; font-weight: 700;")
        root.addWidget(hdr)

        if suggested_title:
            sub = QLabel(suggested_title[:72] + ("…" if len(suggested_title) > 72 else ""))
            sub.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
            sub.setWordWrap(True)
            root.addWidget(sub)

        # Status line (loading / fallback message)
        self._status_lbl = QLabel("Fetching available qualities…")
        self._status_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        root.addWidget(self._status_lbl)

        # Options area
        self._options_widget = QFrame()
        self._options_layout = QVBoxLayout(self._options_widget)
        self._options_layout.setContentsMargins(0, 2, 0, 2)
        self._options_layout.setSpacing(2)
        self._options_widget.hide()
        root.addWidget(self._options_widget)

        self._btn_group = None   # created fresh in each _show_options call

        # Divider + button row
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {BORDER};")
        root.addWidget(sep)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)

        self._ok_btn = QPushButton("Download")
        self._ok_btn.setObjectName("DlBtn")
        self._ok_btn.setEnabled(False)
        self._ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._ok_btn)

        root.addLayout(btn_row)

    # ── Fetching ──────────────────────────────────────────────────────────────

    def _start_fetch(self):
        self._dot_timer = QTimer(self)
        self._dot_timer.timeout.connect(self._tick_dot)
        self._dot_timer.start(350)

        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(
            lambda: self._show_options(
                "Couldn't fetch formats — choose a target quality:",
                FALLBACK_QUALITIES,
            )
        )
        self._timeout.start(15_000)

        self._fetcher = _FormatFetcher(self._url, self._proxy)
        self._fetcher.ready.connect(self._on_formats_ready)
        self._fetcher.failed.connect(
            lambda _: self._show_options(
                "Couldn't fetch formats — choose a target quality:",
                FALLBACK_QUALITIES,
            )
        )
        self._fetcher.start()

    def _tick_dot(self):
        dots = "." * (self._dot_n % 4)
        self._dot_n += 1
        self._status_lbl.setText(f"Fetching available qualities{dots}")

    def _stop_timers(self):
        if hasattr(self, "_dot_timer"):
            self._dot_timer.stop()
        if hasattr(self, "_timeout"):
            self._timeout.stop()

    def _on_formats_ready(self, formats: list, title: str):
        self._stop_timers()
        try:
            seen   = set()
            v_opts = []
            for f in reversed(formats):
                h = f.get("height")
                if not h:
                    continue
                vcodec = f.get("vcodec") or ""
                if vcodec.lower() in ("none", ""):
                    continue
                if h in seen:
                    continue
                seen.add(h)
                size    = f.get("filesize") or f.get("filesize_approx")
                sz_str  = _fmt_bytes(size) if size else ""
                res_lbl = {2160: "4K · 2160p", 1440: "2K · 1440p"}.get(h, f"{h}p")
                fmt_sel = (
                    f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/"
                    f"bestvideo[height<={h}]+bestaudio/"
                    f"best[height<={h}]/best"
                )
                v_opts.append((res_lbl, fmt_sel, False, sz_str))

            v_opts.sort(key=lambda x: _height_key(x[0]), reverse=True)
            audio_opt = [("Audio only  (MP3 · 320 kbps)", "bestaudio/best", True, "")]

            if not v_opts:
                _log.info("No video streams found in format list — falling back")
                self._show_options(
                    "No video streams found — choose target quality:",
                    FALLBACK_QUALITIES,
                )
                return

            self._show_options(
                "Available qualities for this video:",
                v_opts + audio_opt,
                with_size=True,
            )
        except Exception as exc:
            _log.error("Error processing format list: %s", exc, exc_info=True)
            self._show_options(
                "Error reading formats — choose target quality:",
                FALLBACK_QUALITIES,
            )

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _show_options(self, header: str, options, with_size: bool = False):
        self._stop_timers()
        self._status_lbl.setText(header)

        # Clear previous widgets
        while self._options_layout.count():
            child = self._options_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Discard old group entirely — prevents stale ID mappings and
        # double-connected idClicked signals from prior _show_options calls.
        if self._btn_group is not None:
            self._btn_group.setParent(None)
        self._btn_group = QButtonGroup(self)

        first = True
        for i, row_data in enumerate(options):
            label    = row_data[0]
            fmt_str  = row_data[1]
            is_audio = row_data[2]
            sz_str   = row_data[3] if len(row_data) > 3 else ""

            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)

            rb = QRadioButton(label)
            rb.setProperty("fmt_str",  fmt_str)
            rb.setProperty("is_audio", bool(is_audio))

            if first:
                rb.setChecked(True)
                self._fmt_str   = fmt_str
                self._is_audio  = bool(is_audio)
                self._qual_label = label
                first = False

            self._btn_group.addButton(rb, i)
            row.addWidget(rb, stretch=1)

            if with_size and sz_str:
                sz_lbl = QLabel(f"~{sz_str}")
                sz_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; min-width: 52px;")
                sz_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                row.addWidget(sz_lbl)

            container = QFrame()
            container.setLayout(row)
            self._options_layout.addWidget(container)

        self._btn_group.idClicked.connect(self._on_radio_clicked)
        self._options_widget.show()
        self._ok_btn.setEnabled(True)
        self.adjustSize()

    def _on_radio_clicked(self, btn_id: int):
        btn = self._btn_group.button(btn_id)
        if btn:
            self._fmt_str   = btn.property("fmt_str") or ""
            self._is_audio  = bool(btn.property("is_audio"))
            self._qual_label = btn.text()

    # ── Result ────────────────────────────────────────────────────────────────

    def selected_format(self):
        """Returns (yt_dlp_format_string, is_audio_only: bool, quality_label: str)."""
        return self._fmt_str, self._is_audio, self._qual_label


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_bytes(b):
    if not b:
        return ""
    if b >= 1_073_741_824:
        return f"{b/1_073_741_824:.1f} GB"
    if b >= 1_048_576:
        return f"{b/1_048_576:.1f} MB"
    if b >= 1024:
        return f"{b/1024:.0f} KB"
    return f"{b} B"


def _height_key(label: str) -> int:
    """Extract numeric height for sorting."""
    for part in label.replace("·", " ").split():
        if part.endswith("p"):
            try:
                return int(part[:-1])
            except ValueError:
                pass
        if part.endswith("K"):
            try:
                return int(part[:-1]) * 1000
            except ValueError:
                pass
    return 0
