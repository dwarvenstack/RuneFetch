"""
RuneFetch "Harbour" Theme — design tokens (v3).

Palette source (user-supplied):
  #1B3C53  deep ocean navy   — canvas / darkest surface
  #234C6A  harbour blue      — panels / sidebar / cards
  #456882  steel blue        — raised surfaces / borders
  #D2C1B6  driftwood beige   — primary accent (warm against cool navy)
"""

# ── Surface elevation ladder ──────────────────────────────────────────────
BG_PRIMARY      = "#1B3C53"   # canvas — deep ocean navy
BG_SECONDARY    = "#1E4460"   # surface.1 — sidebar / panels (between P and card)
BG_CARD         = "#234C6A"   # surface.1 — download cards
BG_CARD_HOVER   = "#2A5878"   # surface.2 — hover state
BG_INPUT        = "#152F42"   # surface.sunken — inset wells / inputs
BG_OVERLAY      = "#1B3C53cc" # modal overlay
BG_SETTINGS     = "#1E4460"   # settings panel
SURFACE_RAISED  = "#2E607A"   # surface.2 — chips / secondary buttons
SURFACE_OVERLAY = "#344F66"   # surface.3 — menus / toasts / tooltips
HIGHLIGHT_TOP   = "rgba(255,255,255,0.06)"  # 1px lit edge on raised surfaces

# ── Text colours ──────────────────────────────────────────────────────────
TEXT_PRIMARY    = "#F0EDE8"   # warm off-white — headings, titles, key values
TEXT_SECONDARY  = "#A8BAC8"   # mid blue-grey — meta, labels, descriptions
TEXT_MUTED      = "#7899AE"   # steel hint — hints, timestamps, placeholders
TEXT_DISABLED   = "#456882"   # steel blue itself — decor / disabled glyphs ONLY
TEXT_ACCENT     = "#D2C1B6"   # driftwood — links, focus, active labels
TEXT_ON_ACCENT  = "#1B3C53"   # dark navy on filled accent surfaces

# ── Borders ────────────────────────────────────────────────────────────────
BORDER          = "#2E5068"   # single hairline token
BORDER_CARD     = "#2E5068"
BORDER_FOCUS    = "#D2C1B6"   # driftwood focus ring

# ── Gradient definitions ───────────────────────────────────────────────────
GRAD_BEIGE_STEEL = ("#D2C1B6", "#7899AE")   # downloading (warm → steel)
GRAD_ORANGE_RED  = ("#ff9f43", "#FF6B6B")   # error
GRAD_PINK_ORANGE = ("#ff6b9d", "#ff9f43")
GRAD_STEEL_BLUE  = ("#456882", "#234C6A")   # queued (steel → harbour)

# ── Accents ────────────────────────────────────────────────────────────────
ACCENT_CYAN     = "#D2C1B6"   # primary accent: driftwood beige (was cyan)
ACCENT_BLUE     = "#7899AE"   # secondary: steel blue (was blue)
ACCENT_AMBER    = "#C9A882"   # warm amber variant of driftwood — paused / waiting
ACCENT_PURPLE   = "#9D6BFF"   # queued (kept for contrast)
ACCENT_GREEN    = "#6EC99A"   # complete (softened green — ocean-sage)
ACCENT_RED      = "#E06B6B"   # error (softened, less neon)
ACCENT_ORANGE   = "#D4956A"   # warning

# ── Badge colours (state → gradient pair) ─────────────────────────────────
BADGE_DOWNLOADING = GRAD_BEIGE_STEEL
BADGE_QUEUED      = GRAD_STEEL_BLUE
BADGE_COMPLETE    = (ACCENT_GREEN, "#4aaa7a")
BADGE_ERROR       = GRAD_ORANGE_RED
BADGE_PAUSED      = (ACCENT_AMBER, "#a07840")
BADGE_CANCELLED   = ("#456882", "#234C6A")

# ── Typography (warm system fonts — no bundling needed) ───────────────────
FONT_FAMILY     = "Candara"
FONT_DISPLAY    = "Bahnschrift"
FONT_MONO       = "Cascadia Code"

# ── Sizes ──────────────────────────────────────────────────────────────────
SIDEBAR_WIDTH   = 200
SIDEBAR_COMPACT = 56
TITLEBAR_HEIGHT = 42
STATUSBAR_HEIGHT= 28
CARD_RADIUS     = 10
BUTTON_RADIUS   = 6
