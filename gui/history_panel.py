"""
HistoryPanel — shows the completed / errored download log.

Backed by history.json in the same folder as settings.
Supports clear-all and re-download actions.
"""

import json
import logging
import os
from datetime import datetime

_log = logging.getLogger(__name__)

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QMenu,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QAction

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
        except Exception as e:
            _log.warning("Could not load history file %s: %s", HISTORY_PATH, e)
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
    except Exception as e:
        _log.warning("Could not save history to %s: %s", HISTORY_PATH, e)


def delete_history_entry(index: int):
    """Remove the entry at the given index (0 = oldest). No-op if out of range."""
    records = load_history()
    if 0 <= index < len(records):
        records.pop(index)
        try:
            os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
            with open(HISTORY_PATH, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2, ensure_ascii=False)
        except Exception as e:
            _log.warning("Could not save history after delete: %s", e)


def clear_history():
    try:
        if os.path.exists(HISTORY_PATH):
            os.remove(HISTORY_PATH)
    except Exception as e:
        _log.warning("Could not clear history file: %s", e)


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
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._table)

        # ── Bottom bar ───────────────────────────────────────────────────
        footer = QWidget()
        footer.setFixedHeight(36)
        footer.setStyleSheet(f"background: {BG_SECONDARY}; border-top: 1px solid #1e2430;")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(20, 0, 20, 0)
        hint = QLabel("Double-click to re-download · Right-click to delete.")
        hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        fl.addWidget(hint, stretch=1)

        del_btn = QPushButton("Delete selected")
        del_btn.setObjectName("SecondaryBtn")
        del_btn.setAccessibleName("Delete selected history entry")
        del_btn.clicked.connect(self._delete_selected)
        fl.addWidget(del_btn)

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

    def _show_context_menu(self, pos):
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        menu = QMenu(self)
        redownload_act = QAction("Re-download", self)
        redownload_act.triggered.connect(lambda: self._on_double_click(row, 0))
        delete_act = QAction("Delete entry", self)
        delete_act.triggered.connect(lambda: self._delete_row(row))
        menu.addAction(redownload_act)
        menu.addSeparator()
        menu.addAction(delete_act)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _delete_selected(self):
        rows = sorted(
            {idx.row() for idx in self._table.selectedIndexes()},
            reverse=True,
        )
        if not rows:
            return
        for row in rows:
            self._delete_row(row)

    def _delete_row(self, row: int):
        """Delete the row from the table and from the history file.

        The table is displayed newest-first (reversed), so we must map the
        visual row back to its original index in the JSON file.
        """
        records = load_history()
        original_idx = len(records) - 1 - row
        delete_history_entry(original_idx)
        self._table.removeRow(row)
        count = self._table.rowCount()
        self._count_lbl.setText(f"{count} item{'s' if count != 1 else ''}")

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
