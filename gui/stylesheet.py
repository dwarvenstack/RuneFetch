"""
RuneFetch "Harbour" stylesheet (v3).

Palette:
  #1B3C53  BG_PRIMARY      deep ocean navy
  #234C6A  BG_CARD         harbour blue cards
  #456882  TEXT_DISABLED   steel blue (decorative)
  #D2C1B6  ACCENT_CYAN     driftwood beige (primary accent)
"""

from gui.theme import (
    BG_PRIMARY, BG_SECONDARY, BG_CARD, BG_CARD_HOVER, BG_INPUT,
    BG_SETTINGS, SURFACE_RAISED, SURFACE_OVERLAY,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_DISABLED,
    TEXT_ACCENT, TEXT_ON_ACCENT,
    BORDER, BORDER_CARD, BORDER_FOCUS,
    ACCENT_CYAN, ACCENT_BLUE, ACCENT_AMBER, ACCENT_GREEN, ACCENT_RED,
    ACCENT_PURPLE, ACCENT_ORANGE,
    FONT_FAMILY, FONT_DISPLAY, FONT_MONO,
    CARD_RADIUS, BUTTON_RADIUS, SIDEBAR_WIDTH,
)

QSS = f"""
/* ── Base ──────────────────────────────────────────────────────────────── */
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

/* ── Sidebar ────────────────────────────────────────────────────────────── */
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

/* ── Nav buttons ────────────────────────────────────────────────────────── */
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
    background: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
}}
QPushButton#NavBtn[active="true"] {{
    background: rgba(210,193,182,0.12);
    color: {ACCENT_CYAN};
    font-weight: 600;
    border-left: 3px solid {ACCENT_CYAN};
    border-radius: 0 8px 8px 0;
}}
QPushButton#NavBtn[active="true"]:hover {{
    background: rgba(210,193,182,0.18);
}}

/* ── Content panels ─────────────────────────────────────────────────────── */
#ContentPanel {{
    background: {BG_PRIMARY};
}}

#PanelHeader {{
    background: {BG_SECONDARY};
    border-bottom: 1px solid {BORDER};
    padding: 0 20px;
}}

/* ── URL input row ──────────────────────────────────────────────────────── */
QLineEdit#UrlInput {{
    background: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: {BUTTON_RADIUS}px;
    padding: 10px 14px;
    font-size: 13px;
    selection-background-color: rgba(210,193,182,0.25);
    min-height: 40px;
}}
QLineEdit#UrlInput:hover {{
    border-color: rgba(210,193,182,0.45);
}}
QLineEdit#UrlInput:focus {{
    border: 1px solid {BORDER_FOCUS};
    background: {BG_INPUT};
}}
QLineEdit#UrlInput::placeholder {{
    color: {TEXT_MUTED};
}}

/* ── General line edit ─────────────────────────────────────────────────── */
QLineEdit {{
    background: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: {BUTTON_RADIUS}px;
    padding: 6px 10px;
    font-size: 13px;
    selection-background-color: rgba(210,193,182,0.25);
}}
QLineEdit:hover {{
    border-color: rgba(210,193,182,0.35);
}}
QLineEdit:focus {{
    border: 1px solid {BORDER_FOCUS};
}}
QLineEdit[readOnly="true"] {{
    color: {TEXT_MUTED};
    background: {BG_PRIMARY};
}}

/* ── Primary action button ──────────────────────────────────────────────── */
QPushButton#PrimaryBtn,
QPushButton#PrimaryBtn:hover,
QPushButton#PrimaryBtn:pressed {{
    color: {TEXT_ON_ACCENT};
    font-weight: 700;
    font-size: 13px;
}}
QPushButton#PrimaryBtn {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT_CYAN}, stop:1 {ACCENT_BLUE}
    );
    border: none;
    border-radius: {BUTTON_RADIUS}px;
    padding: 10px 22px;
    min-height: 40px;
}}
QPushButton#PrimaryBtn:hover {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #ddd0c8, stop:1 #9ab0c0
    );
}}
QPushButton#PrimaryBtn:pressed {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #b8a99c, stop:1 #5c7f96
    );
}}
QPushButton#PrimaryBtn:disabled {{
    background: {BG_INPUT};
    color: {TEXT_DISABLED};
}}

/* ── Secondary button ───────────────────────────────────────────────────── */
QPushButton#SecondaryBtn {{
    background: transparent;
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER};
    border-radius: {BUTTON_RADIUS}px;
    padding: 7px 16px;
    font-size: 12px;
}}
QPushButton#SecondaryBtn:hover {{
    background: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
    border-color: rgba(210,193,182,0.40);
}}
QPushButton#SecondaryBtn:pressed {{
    background: {BG_CARD};
    border-color: {ACCENT_CYAN};
}}
QPushButton#SecondaryBtn:disabled {{
    color: {TEXT_DISABLED};
    border-color: {BORDER};
}}

/* ── Amber secondary button (warm CTA — resume, retry) ─────────────────── */
QPushButton#AmberBtn {{
    background: transparent;
    color: {ACCENT_AMBER};
    border: 1px solid rgba(201,168,130,0.55);
    border-radius: {BUTTON_RADIUS}px;
    padding: 7px 16px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#AmberBtn:hover {{
    background: rgba(201,168,130,0.12);
    border-color: {ACCENT_AMBER};
}}
QPushButton#AmberBtn:pressed {{
    background: rgba(201,168,130,0.22);
}}

/* ── Danger button (delete, clear all) ─────────────────────────────────── */
QPushButton#DangerBtn {{
    background: transparent;
    color: {TEXT_MUTED};
    border: 1px solid {BORDER};
    border-radius: {BUTTON_RADIUS}px;
    padding: 7px 16px;
    font-size: 12px;
}}
QPushButton#DangerBtn:hover {{
    background: rgba(224,107,107,0.12);
    color: {ACCENT_RED};
    border-color: rgba(224,107,107,0.55);
}}
QPushButton#DangerBtn:pressed {{
    background: rgba(224,107,107,0.22);
}}

/* ── Icon button (small card controls) ─────────────────────────────────── */
QPushButton#IconBtn {{
    background: {BG_INPUT};
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 4px 8px;
    font-size: 14px;
    min-width: 28px;
    min-height: 28px;
}}
QPushButton#IconBtn:hover {{
    background: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
    border-color: rgba(210,193,182,0.40);
}}
QPushButton#IconBtn:pressed {{
    background: {BG_CARD};
    border-color: {ACCENT_CYAN};
}}
QPushButton#IconBtn:disabled {{
    color: {TEXT_DISABLED};
    background: {BG_PRIMARY};
    border-color: {BORDER};
}}

/* ── Icon button delete variant ─────────────────────────────────────────── */
QPushButton#IconBtnDelete {{
    background: {BG_INPUT};
    color: {TEXT_MUTED};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 4px 8px;
    font-size: 14px;
    min-width: 28px;
    min-height: 28px;
}}
QPushButton#IconBtnDelete:hover {{
    background: rgba(224,107,107,0.12);
    color: {ACCENT_RED};
    border-color: rgba(224,107,107,0.55);
}}
QPushButton#IconBtnDelete:pressed {{
    background: rgba(224,107,107,0.22);
}}

/* ── Chip toggle buttons ────────────────────────────────────────────────── */
QPushButton#ChipBtn {{
    background: {BG_INPUT};
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 5px 14px;
    font-size: 12px;
}}
QPushButton#ChipBtn:hover {{
    background: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
    border-color: rgba(210,193,182,0.40);
}}
QPushButton#ChipBtn[active="true"] {{
    background: rgba(210,193,182,0.14);
    color: {ACCENT_CYAN};
    border: 1px solid rgba(210,193,182,0.55);
    font-weight: 600;
}}
QPushButton#ChipBtn[active="true"]:hover {{
    background: rgba(210,193,182,0.22);
}}

/* ── Scroll area ────────────────────────────────────────────────────────── */
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
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: rgba(210,193,182,0.50);
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: {BG_SECONDARY};
    height: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 3px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: rgba(210,193,182,0.50);
}}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Combobox ───────────────────────────────────────────────────────────── */
QComboBox {{
    background: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: {BUTTON_RADIUS}px;
    padding: 6px 12px;
    font-size: 13px;
    min-width: 100px;
}}
QComboBox:hover {{
    border-color: rgba(210,193,182,0.40);
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
    background: {SURFACE_OVERLAY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    selection-background-color: rgba(210,193,182,0.20);
    outline: none;
    padding: 4px;
}}
QComboBox QAbstractItemView::item:hover {{
    background: {SURFACE_RAISED};
}}

/* ── Spinbox ────────────────────────────────────────────────────────────── */
QSpinBox {{
    background: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: {BUTTON_RADIUS}px;
    padding: 6px 10px;
    font-size: 13px;
}}
QSpinBox:hover {{
    border-color: rgba(210,193,182,0.40);
}}
QSpinBox:focus {{
    border: 1px solid {BORDER_FOCUS};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: {BG_CARD};
    border: none;
    width: 18px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {SURFACE_RAISED};
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

/* ── Checkbox ───────────────────────────────────────────────────────────── */
QCheckBox {{
    color: {TEXT_SECONDARY};
    spacing: 8px;
    font-size: 12px;
}}
QCheckBox:hover {{
    color: {TEXT_PRIMARY};
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
}}
QCheckBox::indicator:hover {{
    border-color: rgba(210,193,182,0.60);
}}
QCheckBox::indicator:checked:hover {{
    background: #ddd0c8;
}}

/* ── Labels ─────────────────────────────────────────────────────────────── */
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
    font-family: "{FONT_MONO}", monospace;
}}
QLabel#CardSpeed {{
    color: {TEXT_SECONDARY};
    font-size: 11px;
    font-family: "{FONT_MONO}", monospace;
}}
QLabel#FooterLabel {{
    color: {TEXT_MUTED};
    font-size: 11px;
}}
QLabel#LinkLabel {{
    color: {ACCENT_CYAN};
    font-size: 11px;
}}
QLabel#LinkLabel:hover {{
    color: #ddd0c8;
}}
QLabel#BrandName {{
    color: {TEXT_PRIMARY};
    font-size: 15px;
    font-weight: 700;
    font-family: "{FONT_DISPLAY}", "{FONT_FAMILY}", sans-serif;
    letter-spacing: 0.5px;
}}
QLabel#BrandSub {{
    color: {TEXT_MUTED};
    font-size: 10px;
}}
QLabel#DisplayTitle {{
    color: {TEXT_PRIMARY};
    font-size: 20px;
    font-weight: 700;
    font-family: "{FONT_DISPLAY}", "{FONT_FAMILY}", sans-serif;
}}

/* ── Separator ──────────────────────────────────────────────────────────── */
QFrame[frameShape="4"],
QFrame[frameShape="5"] {{
    color: {BORDER};
    background: {BORDER};
    border: none;
}}

/* ── Tab bar ────────────────────────────────────────────────────────────── */
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
    border-bottom: 2px solid {BORDER};
}}

/* ── Message box ────────────────────────────────────────────────────────── */
QMessageBox {{
    background: {SURFACE_OVERLAY};
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
    background: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
    border-color: rgba(210,193,182,0.40);
}}
QMessageBox QPushButton:pressed {{
    background: {BG_CARD};
}}

/* ── Tooltip ────────────────────────────────────────────────────────────── */
QToolTip {{
    background: {SURFACE_OVERLAY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    padding: 5px 9px;
    border-radius: 5px;
    font-size: 11px;
}}

/* ── Settings ───────────────────────────────────────────────────────────── */
#SettingsGroup {{
    background: {BG_CARD};
    border: 1px solid {BORDER_CARD};
    border-top: 1px solid rgba(255,255,255,0.06);
    border-radius: {CARD_RADIUS}px;
}}
QLabel#SettingsGroupTitle {{
    color: {TEXT_SECONDARY};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    font-family: "{FONT_DISPLAY}", "{FONT_FAMILY}", sans-serif;
}}
QLabel#SettingsDesc {{
    color: {TEXT_MUTED};
    font-size: 11px;
}}

/* ── History table ──────────────────────────────────────────────────────── */
QTableWidget {{
    background: {BG_PRIMARY};
    color: {TEXT_PRIMARY};
    border: none;
    gridline-color: {BORDER};
    selection-background-color: rgba(210,193,182,0.14);
    selection-color: {TEXT_PRIMARY};
    font-size: 12px;
    alternate-background-color: {BG_SECONDARY};
}}
QTableWidget::item {{
    padding: 6px 10px;
    border-bottom: 1px solid {BORDER};
}}
QTableWidget::item:hover {{
    background: {SURFACE_RAISED};
}}
QTableWidget::item:selected {{
    background: rgba(210,193,182,0.14);
    color: {TEXT_PRIMARY};
}}
QHeaderView::section {{
    background: {BG_SECONDARY};
    color: {TEXT_MUTED};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.8px;
    padding: 7px 10px;
    border: none;
    border-bottom: 1px solid {BORDER};
}}
QHeaderView::section:hover {{
    background: {SURFACE_RAISED};
    color: {TEXT_SECONDARY};
}}

/* ── Log text area ──────────────────────────────────────────────────────── */
QTextEdit {{
    background: {BG_INPUT};
    color: {TEXT_SECONDARY};
    border: none;
    border-radius: 6px;
    font-family: "{FONT_MONO}", "Consolas", monospace;
    font-size: 11px;
    padding: 6px;
    selection-background-color: rgba(210,193,182,0.22);
}}

/* ── Menu ───────────────────────────────────────────────────────────────── */
QMenu {{
    background: {SURFACE_OVERLAY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 16px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
}}
QMenu::item:disabled {{
    color: {TEXT_DISABLED};
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 4px 8px;
}}

/* ── Progress bar (fallback for non-waveform areas) ─────────────────────── */
QProgressBar {{
    background: {BG_INPUT};
    border: none;
    border-radius: 3px;
    height: 4px;
    text-align: center;
    font-size: 0px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT_CYAN}, stop:1 {ACCENT_BLUE});
    border-radius: 3px;
}}
"""


def get_stylesheet() -> str:
    return QSS
