"""
RuneFetch icon generator.

Place your source icon as:
    assets/runefetch_icon.png   (recommend 512x512 or larger)

Then run:
    python tools/generate_icons.py

This will:
  • Copy assets/runefetch_icon.png (kept as-is for the app tray / window icon)
  • Generate browser_extension/icons/icon16.png
  • Generate browser_extension/icons/icon48.png
  • Generate browser_extension/icons/icon128.png

Requires:  pip install Pillow  (already in requirements.txt via Pillow>=10.3.0)
"""

import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required: pip install Pillow")

ROOT   = Path(__file__).parent.parent
SRC    = ROOT / "assets" / "runefetch_icon.png"
EXT_ICONS = ROOT / "browser_extension" / "icons"

if not SRC.exists():
    sys.exit(
        f"Source icon not found at: {SRC}\n"
        "Save your icon there (PNG, 512×512 or larger recommended) and re-run."
    )

img = Image.open(SRC).convert("RGBA")
print(f"Source icon loaded: {img.size[0]}×{img.size[1]} px")

EXT_ICONS.mkdir(parents=True, exist_ok=True)

for size in (16, 48, 128):
    out_path = EXT_ICONS / f"icon{size}.png"
    resized = img.resize((size, size), Image.LANCZOS)
    resized.save(out_path, "PNG")
    print(f"  Wrote {out_path}")

print("\nDone. Extension icons updated.")
print(f"App icon:  {SRC}  (used automatically by RuneFetch)")
