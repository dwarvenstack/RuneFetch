"""
RuneFetch stylesheet.

Generates the full QSS string used by QApplication.setStyleSheet().
Keeps all visual polish in one place while theme.py holds raw tokens.
"""

from gui.theme import (
    BG_PRIMARY, BG_SECONDARY, BG_CARD, BG_CARD_HOVER,
    BG_INPUT, BG_SETTINGS,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_ACCENT,
    BORDER, BORDER_FOCUS, BORDER_CARD,
    ACCENT_CYAN, ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, ACCENT_ORANGE,
    FONT_FAMILY, CARD_RADIUS, BUTTON_RADIUS, SIDEBAR_WIDTH,
)

QSS = f"""
/* ── Base ──────────────────────────────────────────────────────── */
QWidget {{
    font-family: "{FONT_FAMILY}", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    color: {TEXT_PRIMARY};
    background: {BG_PRIMARY};
    border: none;
    outline: none;
}}

QMainWindow, QDialog {{
    background: {BG_PRIMARY};
}}

/* ── Sidebar ───────────────────────────────────────────────────── */
#Sidebar {{
    background: {BG_SECONDARY};
    border-right: 1px solid {BORDER};
    min-width: {SIDEBAR_WIDTH}px;
    max-width: {SIDEBAR_WIDTH}px;
}}

#SidebarBrand {{
    background: {BG_SECONDARY};
    padding: 0;
}}

/* ── Nav buttons ───────────────────────────────────────────────── */
QPushButton#NavBtn {{
    background: transparent;
    color: {TEXT_SECONDARY};
    border: none;
    border-radius: 8px;
    padding: 9px 14px;
    text-align: left;
    font-size: 13px;
}}
QPushButton#NavBtn:hover {{
    background: {BG_INPUT};
    color: {TEXT_PRIMARY};
}}
QPushButton#NavBtn[active="true"] {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #00d9ff22, stop:1 #0099ff18
    );
    color: {ACCENT_CYAN};
    font-weight: 600;
    border-left: 2px solid {ACCENT_CYAN};
    border-radius: 0 8px 8px 0;
}}

/* ── Content panels ────────────────────────────────────────────── */
#ContentPanel {{
    background: {BG_PRIMARY};
}}

#PanelHeader {{
    background: {BG_SECONDARY};
    border-bottom: 1px solid {BORDER};
    padding: 0 20px;
}}

/* ── URL input row ─────────────────────────────────────────────── */
QLineEdit#UrlInput {{
    background: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: {BUTTON_RADIUS}px;
    padding: 9px 14px;
    font-size: 13px;
    selection-background-color: {ACCENT_CYAN}44;
}}
QLineEdit#UrlInput:focus {{
    border: 1px solid {BORDER_FOCUS};
}}
QLineEdit#UrlInput::placeholder {{
    color: {TEXT_MUTED};
}}

/* ── Primary action button ─────────────────────────────────────── */
QPushButton#PrimaryBtn {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT_CYAN}, stop:1 {ACCENT_BLUE}
    );
    color: #ffffff;
    border: none;
    border-radius: {BUTTON_RADIUS}px;
    padding: 9px 22px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#PrimaryBtn:hover {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #33e5ff, stop:1 #33aaff
    );
}}
QPushButton#PrimaryBtn:pressed {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #00aacb, stop:1 #007acc
    );
}}
QPushButton#PrimaryBtn:disabled {{
    background: {BG_INPUT};
    color: {TEXT_MUTED};
}}

/* ── Secondary button ──────────────────────────────────────────── */
QPushButton#SecondaryBtn {{
    background: {BG_INPUT};
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER};
    border-radius: {BUTTON_RADIUS}px;
    padding: 7px 16px;
    font-size: 12px;
}}
QPushButton#SecondaryBtn:hover {{
    background: {BG_CARD_HOVER};
    color: {TEXT_PRIMARY};
    border: 1px solid {ACCENT_CYAN}55;
}}
QPushButton#SecondaryBtn:pressed {{
    background: {BG_CARD};
}}

/* ── Icon button (small) ───────────────────────────────────────── */
QPushButton#IconBtn {{
    background: {BG_INPUT};
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 4px 8px;
    font-size: 14px;
    min-width: 28px;
    min-height: 26px;
}}
QPushButton#IconBtn:hover {{
    background: {BG_CARD_HOVER};
    color: {TEXT_PRIMARY};
    border-color: {ACCENT_CYAN}55;
}}
QPushButton#IconBtn:pressed {{
    background: {BG_CARD};
}}
QPushButton#IconBtn:disabled {{
    color: {TEXT_MUTED};
    background: {BG_CARD};
    border-color: {BORDER};
    opacity: 0.4;
}}

/* ── Chip toggle buttons ───────────────────────────────────────── */
QPushButton#ChipBtn {{
    background: {BG_INPUT};
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 5px 14px;
    font-size: 12px;
}}
QPushButton#ChipBtn:hover {{
    background: {BG_CARD_HOVER};
    color: {TEXT_PRIMARY};
}}
QPushButton#ChipBtn[active="true"] {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT_CYAN}33, stop:1 {ACCENT_BLUE}22
    );
    color: {ACCENT_CYAN};
    border: 1px solid {ACCENT_CYAN}66;
    font-weight: 600;
}}

/* ── Scroll area ───────────────────────────────────────────────── */
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QScrollBar:vertical {{
    background: {BG_SECONDARY};
    width: 6px;
    margin: 0;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 3px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT_CYAN}55;
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{ height: 0; }}

/* ── Combobox ──────────────────────────────────────────────────── */
QComboBox {{
    background: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: {BUTTON_RADIUS}px;
    padding: 6px 12px;
    font-size: 12px;
    min-width: 100px;
}}
QComboBox:focus {{
    border: 1px solid {BORDER_FOCUS};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_SECONDARY};
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT_CYAN}33;
    outline: none;
}}

/* ── Spinbox ───────────────────────────────────────────────────── */
QSpinBox {{
    background: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: {BUTTON_RADIUS}px;
    padding: 6px 10px;
    font-size: 12px;
}}
QSpinBox:focus {{
    border: 1px solid {BORDER_FOCUS};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: {BG_CARD};
    border: none;
    width: 18px;
}}
QSpinBox::up-arrow {{
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {TEXT_SECONDARY};
}}
QSpinBox::down-arrow {{
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_SECONDARY};
}}

/* ── Checkbox ──────────────────────────────────────────────────── */
QCheckBox {{
    color: {TEXT_SECONDARY};
    spacing: 8px;
    font-size: 12px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {BG_INPUT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT_CYAN};
    border-color: {ACCENT_CYAN};
    image: none;
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT_CYAN}88;
}}

/* ── Labels ────────────────────────────────────────────────────── */
QLabel#SectionLabel {{
    color: {TEXT_MUTED};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
}}
QLabel#CardTitle {{
    color: {TEXT_PRIMARY};
    font-size: 13px;
    font-weight: 600;
}}
QLabel#CardMeta {{
    color: {TEXT_SECONDARY};
    font-size: 11px;
}}
QLabel#CardSpeed {{
    color: {TEXT_SECONDARY};
    font-size: 11px;
}}
QLabel#FooterLabel {{
    color: {TEXT_MUTED};
    font-size: 11px;
}}
QLabel#LinkLabel {{
    color: {ACCENT_CYAN};
    font-size: 11px;
}}
QLabel#BrandName {{
    color: {TEXT_PRIMARY};
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QLabel#BrandSub {{
    color: {TEXT_MUTED};
    font-size: 10px;
}}

/* ── Separator ─────────────────────────────────────────────────── */
QFrame[frameShape="4"],   /* HLine */
QFrame[frameShape="5"] {{ /* VLine */
    color: {BORDER};
    background: {BORDER};
    border: none;
}}

/* ── Tab bar (history / queue panels) ─────────────────────────── */
QTabWidget::pane {{
    border: none;
    background: {BG_PRIMARY};
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    padding: 8px 18px;
    font-size: 12px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {ACCENT_CYAN};
    border-bottom: 2px solid {ACCENT_CYAN};
}}
QTabBar::tab:hover {{
    color: {TEXT_SECONDARY};
}}

/* ── Message box ───────────────────────────────────────────────── */
QMessageBox {{
    background: {BG_CARD};
}}
QMessageBox QLabel {{
    color: {TEXT_PRIMARY};
}}
QMessageBox QPushButton {{
    background: {BG_INPUT};
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 18px;
    min-width: 80px;
}}
QMessageBox QPushButton:hover {{
    background: {BG_CARD_HOVER};
    color: {TEXT_PRIMARY};
}}

/* ── Tooltip ───────────────────────────────────────────────────── */
QToolTip {{
    background: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 11px;
}}

/* ── Settings ──────────────────────────────────────────────────── */
#SettingsGroup {{
    background: {BG_CARD};
    border: 1px solid {BORDER_CARD};
    border-radius: {CARD_RADIUS}px;
}}
QLabel#SettingsGroupTitle {{
    color: {TEXT_SECONDARY};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.8px;
    text-transform: uppercase;
}}
QLabel#SettingsDesc {{
    color: {TEXT_MUTED};
    font-size: 11px;
}}

/* ── History table ─────────────────────────────────────────────── */
QTableWidget {{
    background: {BG_PRIMARY};
    color: {TEXT_PRIMARY};
    border: none;
    gridline-color: {BORDER};
    selection-background-color: {ACCENT_CYAN}22;
    selection-color: {TEXT_PRIMARY};
    font-size: 12px;
}}
QTableWidget::item {{
    padding: 6px 10px;
    border-bottom: 1px solid {BORDER};
}}
QHeaderView::section {{
    background: {BG_SECONDARY};
    color: {TEXT_MUTED};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.8px;
    padding: 6px 10px;
    border: none;
    border-bottom: 1px solid {BORDER};
}}
"""


def get_stylesheet() -> str:
    return QSS
