"""
SettingsPanel — RuneFetch preferences UI.

Bug 1 fix: Save Settings button was buried below the visible scroll area
because addStretch() was placed after the save button row, pushing it off
screen on shorter windows. Fixed by:
  - Moving addStretch() BEFORE the save button row so it pushes the button
    to the bottom of the content, not beyond it
  - Removing the double addStretch() that was compounding the problem
  - The scroll area's inner widget now sizes correctly to always show the button
"""

import os
import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QCheckBox, QFileDialog,
    QScrollArea, QFrame, QSizePolicy, QApplication,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices

from gui.theme import (
    BG_CARD, BG_SECONDARY, BORDER_CARD, TEXT_PRIMARY, TEXT_SECONDARY,
    TEXT_MUTED, ACCENT_CYAN, ACCENT_GREEN, CARD_RADIUS,
)
import utils.settings as cfg_mod

log = logging.getLogger(__name__)


class _Group(QFrame):
    """Titled settings card group."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsGroup")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(12)

        if title:
            hdr = QLabel(title.upper())
            hdr.setObjectName("SettingsGroupTitle")
            layout.addWidget(hdr)

        self._body = QVBoxLayout()
        self._body.setSpacing(10)
        layout.addLayout(self._body)

    def add(self, widget: QWidget):
        self._body.addWidget(widget)

    def add_layout(self, layout):
        self._body.addLayout(layout)


class SettingsPanel(QWidget):
    """Full settings panel embedded in the main window's stacked widget."""

    saved = pyqtSignal()  # emitted after successful save

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = dict(cfg)
        self._build()

    def reload(self, cfg: dict):
        """Reload panel with fresh config (e.g. after external change)."""
        self.cfg = dict(cfg)
        self._apply_cfg()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        hdr = QWidget()
        hdr.setFixedHeight(56)
        hdr.setObjectName("PanelHeader")
        hdr.setStyleSheet(f"background: {BG_SECONDARY}; border-bottom: 1px solid #1e2430;")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(20, 0, 20, 0)
        title_lbl = QLabel("Settings")
        title_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 16px; font-weight: 700;"
        )
        hdr_layout.addWidget(title_lbl)
        outer.addWidget(hdr)

        # ── Scrollable body ───────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 18, 20, 20)
        body_layout.setSpacing(14)

        # ── Downloads ─────────────────────────────────────────────────────────
        dl_grp = _Group("Downloads")

        path_row = QHBoxLayout()
        self._path_edit = QLineEdit(self.cfg.get("save_path", ""))
        self._path_edit.setObjectName("UrlInput")
        self._path_edit.setPlaceholderText("Default download folder…")
        path_row.addWidget(self._path_edit, stretch=1)
        browse_btn = QPushButton("Browse…")
        browse_btn.setObjectName("SecondaryBtn")
        browse_btn.clicked.connect(self._browse_path)
        path_row.addWidget(browse_btn)
        dl_grp.add(self._make_label("Default download path"))
        dl_grp.add_layout(path_row)

        self._prompt_cb = QCheckBox("Ask for a save location for each download")
        self._prompt_cb.setChecked(self.cfg.get("prompt_per_file", False))
        dl_grp.add(self._prompt_cb)

        conc_row = QWidget()
        conc_row.setStyleSheet("background:transparent")
        cl = QHBoxLayout(conc_row)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(10)
        cl.addWidget(self._make_label("Concurrent downloads"), stretch=1)
        self._conc_spin = QSpinBox()
        self._conc_spin.setRange(1, 10)
        self._conc_spin.setValue(self.cfg.get("max_concurrent", 2))
        self._conc_spin.setFixedWidth(64)
        cl.addWidget(self._conc_spin)
        dl_grp.add(conc_row)

        body_layout.addWidget(dl_grp)

        # ── Performance ───────────────────────────────────────────────────────
        perf_grp = _Group("Performance")

        throttle_row = QWidget()
        throttle_row.setStyleSheet("background:transparent")
        tl = QHBoxLayout(throttle_row)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(10)
        tl.addWidget(self._make_label("Max speed (0 = unlimited)"), stretch=1)
        self._throttle_spin = QSpinBox()
        self._throttle_spin.setRange(0, 100_000)
        self._throttle_spin.setSingleStep(100)
        self._throttle_spin.setSuffix(" KB/s")
        self._throttle_spin.setValue(self.cfg.get("throttle_kbps", 0))
        self._throttle_spin.setFixedWidth(110)
        tl.addWidget(self._throttle_spin)
        perf_grp.add(throttle_row)

        frag_row = QWidget()
        frag_row.setStyleSheet("background:transparent")
        fl = QHBoxLayout(frag_row)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(10)
        fl.addWidget(self._make_label("Fragment threads per download"), stretch=1)
        self._frag_spin = QSpinBox()
        self._frag_spin.setRange(1, 16)
        self._frag_spin.setValue(self.cfg.get("fragment_threads", 4))
        self._frag_spin.setFixedWidth(64)
        fl.addWidget(self._frag_spin)
        perf_grp.add(frag_row)

        body_layout.addWidget(perf_grp)

        # ── Network ───────────────────────────────────────────────────────────
        net_grp = _Group("Network")
        self._proxy_edit = QLineEdit(self.cfg.get("proxy", ""))
        self._proxy_edit.setObjectName("UrlInput")
        self._proxy_edit.setPlaceholderText("http://proxy:port  (blank = none)")
        net_grp.add(self._make_label("HTTP proxy"))
        net_grp.add(self._proxy_edit)
        body_layout.addWidget(net_grp)

        # ── Behaviour ─────────────────────────────────────────────────────────
        beh_grp = _Group("Behaviour")
        self._autostart_cb = QCheckBox("Auto-start queued downloads on launch")
        self._autostart_cb.setChecked(self.cfg.get("autostart", True))
        beh_grp.add(self._autostart_cb)
        self._history_cb = QCheckBox("Keep download history")
        self._history_cb.setChecked(self.cfg.get("keep_history", True))
        beh_grp.add(self._history_cb)
        self._tray_close_cb = QCheckBox("Minimise to system tray when window is closed")
        self._tray_close_cb.setChecked(self.cfg.get("close_to_tray", True))
        beh_grp.add(self._tray_close_cb)
        self._clip_cb = QCheckBox("Monitor clipboard for URLs (auto-fill URL bar)")
        self._clip_cb.setChecked(self.cfg.get("clipboard_monitor", False))
        beh_grp.add(self._clip_cb)
        body_layout.addWidget(beh_grp)

        # ── Browser Extension ─────────────────────────────────────────────────
        ext_grp = _Group("Browser Extension")

        ext_info = QLabel(
            "Install the RuneFetch extension in Chrome/Edge, then paste the token "
            "below into the extension popup to pair it."
        )
        ext_info.setWordWrap(True)
        ext_info.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
        ext_grp.add(ext_info)

        token_row = QHBoxLayout()
        self._token_edit = QLineEdit(self.cfg.get("bridge_token", ""))
        self._token_edit.setObjectName("UrlInput")
        self._token_edit.setReadOnly(True)
        self._token_edit.setPlaceholderText("Token not yet generated — save settings to generate")
        token_row.addWidget(self._token_edit, stretch=1)

        self._copy_token_btn = QPushButton("Copy")
        self._copy_token_btn.setObjectName("SecondaryBtn")
        self._copy_token_btn.setFixedWidth(64)
        self._copy_token_btn.setAccessibleName("Copy bridge token to clipboard")
        self._copy_token_btn.clicked.connect(self._copy_token)
        token_row.addWidget(self._copy_token_btn)
        ext_grp.add(self._make_label("Pairing token"))
        ext_grp.add_layout(token_row)

        port_row = QWidget()
        port_row.setStyleSheet("background:transparent")
        pr = QHBoxLayout(port_row)
        pr.setContentsMargins(0, 0, 0, 0)
        pr.setSpacing(10)
        pr.addWidget(self._make_label("Bridge port (default 8765)"), stretch=1)
        self._bridge_port_spin = QSpinBox()
        self._bridge_port_spin.setRange(1024, 65535)
        self._bridge_port_spin.setValue(self.cfg.get("bridge_port", 8765))
        self._bridge_port_spin.setFixedWidth(80)
        pr.addWidget(self._bridge_port_spin)
        ext_grp.add(port_row)

        body_layout.addWidget(ext_grp)

        # ── About ─────────────────────────────────────────────────────────────
        about_grp = _Group("About RuneFetch")
        ver = QLabel("RuneFetch v1.0.0  ·  by DwarvenStack")
        ver.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        about_grp.add(ver)
        link_btn = QPushButton("⛩  Visit DwarvenStack on GitHub")
        link_btn.setObjectName("SecondaryBtn")
        link_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/dwarvenstack"))
        )
        about_grp.add(link_btn)
        body_layout.addWidget(about_grp)

        # ── Save button ───────────────────────────────────────────────────────
        # BUG 1 FIX: addStretch() was placed AFTER the save row, pushing the
        # button beyond the scroll area's visible height on smaller windows.
        # Correct order: stretch fills space above, then save button sits at bottom.
        body_layout.addStretch()   # ← pushes save btn to bottom, NOT past it

        save_row = QHBoxLayout()
        save_row.addStretch()
        self._save_btn = QPushButton("Save Settings")
        self._save_btn.setObjectName("PrimaryBtn")
        self._save_btn.setFixedWidth(150)
        self._save_btn.setMinimumHeight(36)
        from gui.theme import TEXT_ON_ACCENT
        self._save_btn.setStyleSheet(
            f"QPushButton#PrimaryBtn {{ color: {TEXT_ON_ACCENT}; font-weight: 700; }}"
        )
        # Explicit connection — verified separately from layout fix
        self._save_btn.clicked.connect(self._save)
        save_row.addWidget(self._save_btn)
        body_layout.addLayout(save_row)
        # No second addStretch() here — that was the original bug

        scroll.setWidget(body)
        outer.addWidget(scroll)

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;"
        )
        return lbl

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _copy_token(self):
        token = self._token_edit.text().strip()
        if token:
            QApplication.clipboard().setText(token)
            self._copy_token_btn.setText("Copied!")
            QTimer.singleShot(1500, lambda: self._copy_token_btn.setText("Copy"))

    def _browse_path(self):
        current = self._path_edit.text() or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(
            self, "Choose download folder", current
        )
        if folder:
            self._path_edit.setText(folder)

    def _save(self):
        """
        Persist all settings to disk.
        Shows a brief visual confirmation on the button itself.
        Emits saved() so the main window can reload its queue settings.
        """
        try:
            path = self._path_edit.text().strip()
            if path and not os.path.exists(path):
                try:
                    os.makedirs(path, exist_ok=True)
                except OSError as e:
                    log.warning(f"Could not create save path '{path}': {e}")

            self.cfg["save_path"]        = path or self.cfg.get("save_path", "")
            self.cfg["prompt_per_file"]  = self._prompt_cb.isChecked()
            self.cfg["max_concurrent"]   = self._conc_spin.value()
            self.cfg["throttle_kbps"]    = self._throttle_spin.value()
            self.cfg["fragment_threads"] = self._frag_spin.value()
            self.cfg["proxy"]              = self._proxy_edit.text().strip()
            self.cfg["autostart"]          = self._autostart_cb.isChecked()
            self.cfg["keep_history"]       = self._history_cb.isChecked()
            self.cfg["close_to_tray"]      = self._tray_close_cb.isChecked()
            self.cfg["clipboard_monitor"]  = self._clip_cb.isChecked()
            self.cfg["bridge_port"]        = self._bridge_port_spin.value()
            # Generate token on first save if absent
            from utils.settings import get_or_create_bridge_token
            get_or_create_bridge_token(self.cfg)
            self._token_edit.setText(self.cfg.get("bridge_token", ""))

            cfg_mod.save(self.cfg)
            log.info("Settings saved successfully.")

            # Visual feedback — button briefly turns green
            self._save_btn.setText("✓  Saved")
            self._save_btn.setStyleSheet(
                "QPushButton { background: #2dd4a022; color: #2dd4a0; "
                "border: 1px solid #2dd4a055; border-radius: 6px; "
                "font-size: 13px; font-weight: 600; }"
            )
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(1800, self._reset_save_btn)

            self.saved.emit()

        except Exception as e:
            log.error(f"Failed to save settings: {e}")
            self._save_btn.setText("⚠  Save failed")
            self._save_btn.setStyleSheet(
                "QPushButton { background: #ff6b6b22; color: #ff6b6b; "
                "border: 1px solid #ff6b6b55; border-radius: 6px; "
                "font-size: 13px; font-weight: 600; }"
            )
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(2500, self._reset_save_btn)

    def _reset_save_btn(self):
        """Restore save button to its normal PrimaryBtn style."""
        from gui.theme import TEXT_ON_ACCENT
        self._save_btn.setText("Save Settings")
        self._save_btn.setObjectName("PrimaryBtn")
        self._save_btn.setStyleSheet(
            f"QPushButton#PrimaryBtn {{ color: {TEXT_ON_ACCENT}; font-weight: 700; }}"
        )
        self._save_btn.style().unpolish(self._save_btn)
        self._save_btn.style().polish(self._save_btn)

    def _apply_cfg(self):
        self._path_edit.setText(self.cfg.get("save_path", ""))
        self._prompt_cb.setChecked(self.cfg.get("prompt_per_file", False))
        self._conc_spin.setValue(self.cfg.get("max_concurrent", 2))
        self._throttle_spin.setValue(self.cfg.get("throttle_kbps", 0))
        self._frag_spin.setValue(self.cfg.get("fragment_threads", 4))
        self._proxy_edit.setText(self.cfg.get("proxy", ""))
        self._autostart_cb.setChecked(self.cfg.get("autostart", True))
        self._history_cb.setChecked(self.cfg.get("keep_history", True))
        self._tray_close_cb.setChecked(self.cfg.get("close_to_tray", True))
        self._clip_cb.setChecked(self.cfg.get("clipboard_monitor", False))
        self._bridge_port_spin.setValue(self.cfg.get("bridge_port", 8765))
        self._token_edit.setText(self.cfg.get("bridge_token", ""))

    def get_cfg(self) -> dict:
        return dict(self.cfg)
