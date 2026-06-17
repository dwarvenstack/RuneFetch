"""
RuneFetch Theme — design tokens for the DwarvenStack IDM.

Palette is built around a deep navy/slate dark background with four
signature gradient pairs used throughout the UI for badges, progress
fills, and accent elements.
"""

# ── Core background palette ────────────────────────────────────────────────
BG_PRIMARY      = "#0d0f14"   # near-black base canvas
BG_SECONDARY    = "#13161e"   # sidebar / header panels
BG_CARD         = "#181c26"   # download cards
BG_CARD_HOVER   = "#1e2330"   # card hover state
BG_INPUT        = "#1e2330"   # text input fields
BG_OVERLAY      = "#0d0f14cc" # semi-transparent overlay (modal bg)
BG_SETTINGS     = "#13161e"   # settings panel

# ── Text colours ──────────────────────────────────────────────────────────
TEXT_PRIMARY    = "#eef2ff"   # near-white main text
TEXT_SECONDARY  = "#8b92a8"   # secondary / meta info
TEXT_MUTED      = "#4a5070"   # disabled / placeholder
TEXT_ACCENT     = "#00d9ff"   # cyan accent text
TEXT_ON_ACCENT  = "#ffffff"

# ── Borders ────────────────────────────────────────────────────────────────
BORDER          = "#1e2430"
BORDER_FOCUS    = "#00d9ff"
BORDER_CARD     = "#222838"

# ── Gradient definitions (CSS-style for reference; used in QPainter logic) ─
# Cyan → Blue
GRAD_CYAN_BLUE   = ("#00d9ff", "#0099ff")
# Orange → Red
GRAD_ORANGE_RED  = ("#ff9f43", "#ff6b6b")
# Pink → Orange
GRAD_PINK_ORANGE = ("#ff6b9d", "#ff9f43")
# Purple → Cyan
GRAD_PURPLE_CYAN = ("#9d4edd", "#00d9ff")

# Solid accents (start colours of each gradient)
ACCENT_CYAN     = "#00d9ff"
ACCENT_BLUE     = "#0099ff"
ACCENT_ORANGE   = "#ff9f43"
ACCENT_RED      = "#ff6b6b"
ACCENT_PINK     = "#ff6b9d"
ACCENT_PURPLE   = "#9d4edd"
ACCENT_GREEN    = "#2dd4a0"

# ── Badge colours (state → gradient pair) ─────────────────────────────────
BADGE_DOWNLOADING = GRAD_CYAN_BLUE
BADGE_QUEUED      = GRAD_PURPLE_CYAN
BADGE_COMPLETE    = (ACCENT_GREEN, "#1a9b74")
BADGE_ERROR       = GRAD_ORANGE_RED
BADGE_PAUSED      = ("#8b92a8", "#4a5070")
BADGE_CANCELLED   = ("#4a5070", "#2a2f3d")

# ── Typography ─────────────────────────────────────────────────────────────
FONT_FAMILY     = "Segoe UI"        # Windows; falls back gracefully
FONT_MONO       = "Consolas"

# ── Sizes ──────────────────────────────────────────────────────────────────
SIDEBAR_WIDTH   = 188
TITLEBAR_HEIGHT = 42
STATUSBAR_HEIGHT= 28
CARD_RADIUS     = 10
BUTTON_RADIUS   = 6

# ── QSS fragments ──────────────────────────────────────────────────────────
# Full stylesheet is built in gui/stylesheet.py to keep this file as pure tokens.
