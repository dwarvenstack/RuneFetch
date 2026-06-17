"""
HistoryPanel — shows the completed / errored download log.

Backed by history.json in the same folder as settings.
Supports clear-all and re-download actions.
"""

import json
import os
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from gui.theme import (
    BG_SECONDARY, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_GREEN, ACCENT_RED, ACCENT_CYAN,
)
import utils.settings as cfg_mod


HISTORY_PATH = os.path.join(
    os.path.dirname(cfg_mod.CONFIG_PATH), "runefetch_history.json"
)


def load_history() -> list:
    if os.path.exists(HISTORY_PATH):
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def append_history(entry: dict):
    """Append one entry; keeps last 500 records."""
    records = load_history()
    records.append(entry)
    records = records[-500:]
    try:
        os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def clear_history():
    try:
        if os.path.exists(HISTORY_PATH):
            os.remove(HISTORY_PATH)
    except Exception:
        pass


class HistoryPanel(QWidget):
    """History panel widget."""

    redownload_requested = pyqtSignal(dict)  # emits {url, fmt, save_path, title}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self.reload()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ──────────────────────────────────────────────────────
        hdr = QWidget()
        hdr.setFixedHeight(56)
        hdr.setStyleSheet(f"background: {BG_SECONDARY}; border-bottom: 1px solid #1e2430;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 16, 0)

        title = QLabel("History")
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 16px; font-weight: 700;")
        hl.addWidget(title, stretch=1)

        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        hl.addWidget(self._count_lbl)

        clear_btn = QPushButton("Clear history")
        clear_btn.setObjectName("SecondaryBtn")
        clear_btn.clicked.connect(self._clear)
        hl.addWidget(clear_btn)

        layout.addWidget(hdr)

        # ── Table ────────────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["Title", "Platform", "Format", "Size", "Date"]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for col in (1, 2, 3, 4):
            self._table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(False)
        self._table.setShowGrid(False)
        layout.addWidget(self._table)

        # ── Bottom bar ───────────────────────────────────────────────────
        footer = QWidget()
        footer.setFixedHeight(36)
        footer.setStyleSheet(f"background: {BG_SECONDARY}; border-top: 1px solid #1e2430;")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(20, 0, 20, 0)
        hint = QLabel("Double-click a row to re-download that item.")
        hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        fl.addWidget(hint)
        layout.addWidget(footer)

        self._table.cellDoubleClicked.connect(self._on_double_click)

    # ── Slots ────────────────────────────────────────────────────────────────

    def reload(self):
        records = load_history()
        self._table.setRowCount(0)
        for rec in reversed(records):
            row = self._table.rowCount()
            self._table.insertRow(row)

            state  = rec.get("state", "")
            colour = QColor(ACCENT_GREEN) if state == "Complete" else QColor(ACCENT_RED)

            items = [
                (rec.get("title", "—"), TEXT_PRIMARY),
                (rec.get("source_label", "—"), TEXT_SECONDARY),
                (rec.get("fmt", "—"), TEXT_SECONDARY),
                (rec.get("size", "—"), TEXT_SECONDARY),
                (rec.get("date", "—"), TEXT_MUTED),
            ]
            # Store full record in col-0 UserRole so redownload has all metadata
            for col, (text, fg) in enumerate(items):
                cell = QTableWidgetItem(text)
                cell.setForeground(QColor(fg))
                if col == 0:
                    # Pack url + fmt + save_path as a dict for the redownload slot
                    cell.setData(Qt.ItemDataRole.UserRole, {
                        "url":        rec.get("url", ""),
                        "fmt":        rec.get("fmt", ""),
                        "save_path":  rec.get("save_path", ""),
                        "title":      rec.get("title", ""),
                    })
                else:
                    cell.setData(Qt.ItemDataRole.UserRole, rec.get("url", ""))
                self._table.setItem(row, col, cell)

        count = self._table.rowCount()
        self._count_lbl.setText(f"{count} item{'s' if count != 1 else ''}")

    def _clear(self):
        reply = QMessageBox.question(
            self, "Clear History",
            "Remove all history records?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            clear_history()
            self.reload()

    def _on_double_click(self, row: int, _col: int):
        """
        Bug 3 fix: emit full record dict (not just URL) so the redownload
        slot can check for existing files and restore the original fmt/quality.
        Previously emitted only a str URL; now emits a dict.
        """
        item = self._table.item(row, 0)
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("url"):
                self.redownload_requested.emit(data)
            elif isinstance(data, str) and data:
                # Backwards-compat: old history entries stored just a string
                self.redownload_requested.emit({"url": data, "fmt": "", "save_path": "", "title": ""})
