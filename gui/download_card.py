"""
DownloadCard — PyQt6 widget for one download item.

Fixes in this version
─────────────────────
• delete properly calls setParent(None) + deleteLater() so widget is
  fully removed from layout with no layout-shift ghost
• clear_all path emits deleted signal so cards self-clean correctly
• Per-item log panel (collapsible) shows each track / event line in
  real time — colour-coded: grey normal, green ✓ done, red ✗ error
• Button disabled states are visually unambiguous (near-black + dim text)
"""

import logging
import os
import sys
import subprocess

from PyQt6.QtWidgets import (
    QFrame, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QSizePolicy, QTextEdit, QScrollArea,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QPainter, QLinearGradient, QColor, QBrush, QTextCursor

from gui.theme import (
    BG_CARD, BG_CARD_HOVER, BORDER_CARD,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_CYAN, ACCENT_AMBER, ACCENT_GREEN, ACCENT_RED,
    CARD_RADIUS, BADGE_DOWNLOADING, BADGE_QUEUED, BADGE_COMPLETE,
    BADGE_ERROR, BADGE_PAUSED, BADGE_CANCELLED,
)
from gui.waveform import WaveformProgress, GRADIENT_PRESETS
from core.queue_manager import (
    STATE_QUEUED, STATE_DOWNLOADING, STATE_COMPLETE,
    STATE_ERROR, STATE_PAUSED, STATE_CANCELLED,
)

# ── Badge map ────────────────────────────────────────────────────────────────

_log = logging.getLogger(__name__)

_BADGE_MAP = {
    STATE_DOWNLOADING: BADGE_DOWNLOADING,
    STATE_QUEUED:      BADGE_QUEUED,
    STATE_COMPLETE:    BADGE_COMPLETE,
    STATE_ERROR:       BADGE_ERROR,
    STATE_PAUSED:      BADGE_PAUSED,
    STATE_CANCELLED:   BADGE_CANCELLED,
}

_GRADIENT_MAP = {
    STATE_DOWNLOADING: "cyan_blue",
    STATE_QUEUED:      "purple_cyan",
    STATE_COMPLETE:    "green",
    STATE_ERROR:       "red",
    STATE_PAUSED:      "muted",
    STATE_CANCELLED:   "muted",
}

# ── Button stylesheets ───────────────────────────────────────────────────────

_STYLE_ACTIVE = """
QPushButton {
    background: #181c26;
    color: #8b92a8;
    border: 1px solid #1e2430;
    border-radius: 5px;
    font-size: 14px;
}
QPushButton:hover {
    background: #1e2330;
    color: #eef2ff;
    border-color: #00d9ff55;
}
QPushButton:pressed {
    background: #13161e;
}
"""

_STYLE_DISABLED = """
QPushButton {
    background: #111418;
    color: #232830;
    border: 1px solid #161a22;
    border-radius: 5px;
    font-size: 14px;
}
"""

_STYLE_DELETE = """
QPushButton {
    background: #181c26;
    color: #8b92a8;
    border: 1px solid #1e2430;
    border-radius: 5px;
    font-size: 14px;
}
QPushButton:hover {
    background: #2a1010;
    color: #ff6b6b;
    border-color: #ff6b6b55;
}
QPushButton:pressed {
    background: #1a0a0a;
}
"""

# ── Gradient badge ────────────────────────────────────────────────────────────

class GradientBadge(QLabel):
    def __init__(self, text: str, color_pair: tuple, parent=None):
        super().__init__(text, parent)
        self._c1 = QColor(color_pair[0])
        self._c2 = QColor(color_pair[1])
        self.setFixedHeight(22)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "color: #ffffff; font-size: 11px; font-weight: 700;"
            "padding: 0 10px; background: transparent; border: none;"
        )
        self._resize_to(text)

    def _resize_to(self, text: str):
        self.setFixedWidth(self.fontMetrics().horizontalAdvance(text) + 24)

    def set_colors(self, color_pair: tuple):
        self._c1 = QColor(color_pair[0])
        self._c2 = QColor(color_pair[1])
        self.update()

    def setText(self, text: str):
        super().setText(text)
        self._resize_to(text)

    def paintEvent(self, event):
        try:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            grad = QLinearGradient(0, 0, self.width(), 0)
            c1 = QColor(self._c1); c1.setAlpha(210)
            c2 = QColor(self._c2); c2.setAlpha(210)
            grad.setColorAt(0.0, c1)
            grad.setColorAt(1.0, c2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(self.rect(), 11, 11)
            p.end()
        except Exception as exc:
            _log.error("GradientBadge paintEvent error: %s", exc)
        super().paintEvent(event)


# ── Log panel ─────────────────────────────────────────────────────────────────

class LogPanel(QWidget):
    """
    Collapsible per-card activity log.
    Shows track-by-track events: downloading, done, error.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._visible = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(0)

        self._toggle_btn = QPushButton("▶  Show log")
        self._toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: #4a5070;
                border: none;
                font-size: 11px;
                text-align: left;
                padding: 0;
            }}
            QPushButton:hover {{ color: #8b92a8; }}
        """)
        self._toggle_btn.setFixedHeight(18)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._toggle)
        layout.addWidget(self._toggle_btn)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(100)
        self._log.setStyleSheet("""
            QTextEdit {
                background: #0d0f14;
                color: #6b7280;
                border: 1px solid #1e2430;
                border-radius: 4px;
                font-family: Consolas, monospace;
                font-size: 11px;
                padding: 4px 6px;
            }
            QScrollBar:vertical {
                background: #13161e; width: 4px; border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background: #2a2f3d; border-radius: 2px;
            }
        """)
        self._log.setVisible(False)
        layout.addWidget(self._log)

    def _toggle(self):
        self._visible = not self._visible
        self._log.setVisible(self._visible)
        self._toggle_btn.setText(
            "▼  Hide log" if self._visible else "▶  Show log"
        )

    def append(self, text: str, colour: str = "#6b7280"):
        """Append a coloured HTML line and auto-scroll to bottom."""
        html = f'<span style="color:{colour};">{text}</span>'
        self._log.append(html)
        self._log.moveCursor(QTextCursor.MoveOperation.End)

    def has_entries(self) -> bool:
        return self._log.toPlainText().strip() != ""


# ── Download card ─────────────────────────────────────────────────────────────

class DownloadCard(QFrame):
    """One card in the download queue list."""

    deleted = pyqtSignal(str)

    def __init__(self, item, queue, cfg: dict, parent=None):
        super().__init__(parent)
        self.item  = item
        self.queue = queue
        self.cfg   = cfg
        self._being_deleted = False   # guard against double-delete

        self.setObjectName("DownloadCard")
        self.setStyleSheet(f"""
            QFrame#DownloadCard {{
                background: {BG_CARD};
                border: 1px solid {BORDER_CARD};
                border-top: 1px solid rgba(255,255,255,0.07);
                border-radius: {CARD_RADIUS}px;
            }}
            QFrame#DownloadCard:hover {{
                border-color: rgba(245,185,69,0.30);
                border-top-color: rgba(255,255,255,0.10);
            }}
        """)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Resting drop-shadow (Forge §5.4)
        from gui.motion import apply_shadow
        self._shadow = apply_shadow(self, blur=10, offset_y=3,
                                    colour="#000000", alpha=90)
        self._build()

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build(self):
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(14, 10, 14, 10)
        self._root.setSpacing(6)

        # Row 1: icon · title/meta · badge
        top = QHBoxLayout()
        top.setSpacing(8)

        self._icon_lbl = QLabel(self.item.source_icon)
        self._icon_lbl.setFixedWidth(22)
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._icon_lbl.setStyleSheet("font-size: 16px; background: transparent;")
        top.addWidget(self._icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)

        self._title_lbl = QLabel(self._truncate(self.item.title, 70))
        self._title_lbl.setObjectName("CardTitle")
        self._title_lbl.setToolTip(self.item.title)
        title_col.addWidget(self._title_lbl)

        self._meta_lbl = QLabel(self._meta_text())
        self._meta_lbl.setObjectName("CardMeta")
        title_col.addWidget(self._meta_lbl)

        top.addLayout(title_col, stretch=1)

        badge_pair = _BADGE_MAP.get(self.item.state, BADGE_QUEUED)
        self._badge = GradientBadge(self.item.state, badge_pair)
        top.addWidget(self._badge, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._root.addLayout(top)

        # Row 2: waveform
        grad_key = _GRADIENT_MAP.get(self.item.state, "cyan_blue")
        self._wave = WaveformProgress(self, gradient_key=grad_key, height=26)
        self._wave.set_progress(self.item.progress)
        self._root.addWidget(self._wave)

        # Row 3: speed/ETA + buttons
        bottom = QHBoxLayout()
        bottom.setSpacing(6)

        self._speed_lbl = QLabel(self._speed_text())
        self._speed_lbl.setObjectName("CardSpeed")
        bottom.addWidget(self._speed_lbl, stretch=1)

        self._eta_lbl = QLabel(self.item.eta or "")
        self._eta_lbl.setObjectName("CardSpeed")
        self._eta_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        bottom.addWidget(self._eta_lbl)

        self._btn_pause  = self._make_btn("⏸", "Pause / Resume", self._on_pause)
        self._btn_cancel = self._make_btn("✕",  "Cancel",          self._on_cancel)
        self._btn_folder = self._make_btn("📂", "Open folder",      self._on_folder)
        self._btn_delete = self._make_btn("🗑",  "Remove",          self._on_delete)
        self._btn_delete.setStyleSheet(_STYLE_DELETE)

        for btn in (self._btn_pause, self._btn_cancel,
                    self._btn_folder, self._btn_delete):
            bottom.addWidget(btn)

        self._root.addLayout(bottom)

        # Row 4: collapsible log panel
        self._log_panel = LogPanel(self)
        self._root.addWidget(self._log_panel)

        self._refresh_buttons()

    def _make_btn(self, icon: str, tooltip: str, slot) -> QPushButton:
        btn = QPushButton(icon)
        btn.setToolTip(tooltip)
        btn.setAccessibleName(tooltip)  # screen-reader label for icon-only buttons
        btn.setFixedSize(QSize(30, 26))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(_STYLE_ACTIVE)
        btn.clicked.connect(slot)
        return btn

    # ── Log API ────────────────────────────────────────────────────────────────

    def log(self, text: str, colour: str = "#6b7280"):
        """Append a line to this card's log panel."""
        self._log_panel.append(text, colour)

    # ── Actions ────────────────────────────────────────────────────────────────

    def _on_pause(self):
        if self.item.state == STATE_PAUSED:
            self.queue.resume(self.item.id)
        elif self.item.state == STATE_DOWNLOADING:
            self.queue.pause(self.item.id)

    def _on_cancel(self):
        self.queue.cancel(self.item.id)

    def _on_folder(self):
        path = self.item.save_path
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", path])
            elif sys.platform == "win32":
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

    def _on_delete(self):
        """
        Remove this card cleanly.

        Must:
        1. Guard against re-entry (double-click or poll-loop calling refresh
           on an item that's already being removed).
        2. Cancel the download if still active.
        3. Remove from parent layout, hide, then schedule deleteLater()
           so Qt fully frees the widget after the current event loop tick.
        4. Emit deleted so the main window updates its bookkeeping.
        """
        if self._being_deleted:
            return
        self._being_deleted = True

        # Stop any active download
        self.queue.remove(self.item.id)

        # Detach from layout immediately so the gap closes right away
        self.hide()
        self.setParent(None)   # removes from layout

        # Schedule full Qt object deletion after event loop processes hide
        self.deleteLater()

        # Notify parent window to clean up its _cards dict
        self.deleted.emit(self.item.id)

    # ── Refresh ────────────────────────────────────────────────────────────────

    def refresh(self, item):
        """Called by the main window poll loop. Skipped if being deleted."""
        if self._being_deleted:
            return

        self.item = item

        self._title_lbl.setText(self._truncate(item.title, 70))
        self._title_lbl.setToolTip(item.title)
        self._meta_lbl.setText(self._meta_text())
        self._speed_lbl.setText(self._speed_text())
        self._eta_lbl.setText(item.eta or "")

        if item.state == STATE_ERROR:
            self._meta_lbl.setText(self._truncate(item.error_msg, 80))
            self._meta_lbl.setStyleSheet(f"color: {ACCENT_RED}; font-size: 11px;")
        else:
            self._meta_lbl.setStyleSheet("")

        badge_pair = _BADGE_MAP.get(item.state, BADGE_QUEUED)
        self._badge.setText(item.state)
        self._badge.set_colors(badge_pair)

        grad_key = _GRADIENT_MAP.get(item.state, "cyan_blue")
        self._wave.set_gradient(grad_key)
        self._wave.set_progress(item.progress)

        self._refresh_buttons()

    def _refresh_buttons(self):
        state  = self.item.state
        active = state in (STATE_QUEUED, STATE_DOWNLOADING)
        paused = state == STATE_PAUSED
        done   = state in (STATE_COMPLETE, STATE_ERROR, STATE_CANCELLED)

        # Pause
        can_pause = active or paused
        self._btn_pause.setText("▶" if paused else "⏸")
        self._btn_pause.setToolTip("Resume" if paused else "Pause")
        self._btn_pause.setEnabled(can_pause)
        self._btn_pause.setStyleSheet(_STYLE_ACTIVE if can_pause else _STYLE_DISABLED)
        self._btn_pause.setCursor(
            Qt.CursorShape.PointingHandCursor if can_pause
            else Qt.CursorShape.ForbiddenCursor
        )

        # Cancel
        can_cancel = active or paused
        self._btn_cancel.setEnabled(can_cancel)
        self._btn_cancel.setStyleSheet(_STYLE_ACTIVE if can_cancel else _STYLE_DISABLED)
        self._btn_cancel.setCursor(
            Qt.CursorShape.PointingHandCursor if can_cancel
            else Qt.CursorShape.ForbiddenCursor
        )

        # Folder — always available; dimmer when queued only
        folder_ready = state != STATE_QUEUED
        self._btn_folder.setEnabled(True)
        self._btn_folder.setStyleSheet(_STYLE_ACTIVE if folder_ready else _STYLE_DISABLED)

        # Delete — always red-hover active
        self._btn_delete.setEnabled(True)
        self._btn_delete.setStyleSheet(_STYLE_DELETE)
        self._btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _meta_text(self) -> str:
        parts = [f"⊙ {self.item.source_label}"]
        qual = getattr(self.item, "quality", "") or ""
        fmt  = self.item.fmt or ""
        if qual:
            # Use the human-readable quality label stored at add() time
            parts.append(qual)
        elif "mp3" in fmt.lower() or (
            "bestvideo" not in fmt.lower() and "audio" in fmt.lower()
        ):
            parts.append("MP3")
        elif fmt:
            parts.append(fmt)
        if self.item.size:
            parts.append(self.item.size)
        return "  ·  ".join(parts)

    def _speed_text(self) -> str:
        if self.item.speed:
            return f"{self.item.progress:.0f}%  ·  {self.item.speed}"
        if self.item.progress > 0:
            return f"{self.item.progress:.0f}%"
        return ""

    @staticmethod
    def _truncate(text: str, n: int) -> str:
        return text[:n] + "…" if len(text) > n else text
