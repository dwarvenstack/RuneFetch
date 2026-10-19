#!/usr/bin/env python3
"""
Verify every runtime dependency imports on a clean interpreter.

This is the check that would have caught the August 2026 breakage, where the
interpreter RuneFetch ran under lost its site-packages and every import in
app.py failed at startup while the source stayed perfectly valid.

Import name != distribution name for several deps, so both are listed.
"""

import importlib
import sys

# (import name, pip distribution name, required?)
DEPENDENCIES = [
    ("webview",     "pywebview",      True),
    ("yt_dlp",      "yt-dlp",         True),
    ("websockets",  "websockets",     True),
    ("requests",    "requests",       True),
    ("PIL",         "Pillow",         True),
    ("bs4",         "beautifulsoup4", True),
    ("mutagen",     "mutagen",        True),
    ("tldextract",  "tldextract",     True),
    ("spotdl",      "spotdl",         True),
    # Optional: the app degrades gracefully without these (tray icon /
    # clipboard monitor are disabled, downloads still work).
    ("pystray",     "pystray",        False),
    ("pyperclip",   "pyperclip",      False),
]


def main() -> int:
    failures = []

    for import_name, dist_name, required in DEPENDENCIES:
        try:
            mod = importlib.import_module(import_name)
        except Exception as exc:
            tag = "FAIL" if required else "WARN"
            print(f"{tag}  {import_name:<12} ({dist_name}) -> {type(exc).__name__}: {exc}")
            if required:
                failures.append(dist_name)
            continue

        version = getattr(mod, "__version__", None)
        if version is None and import_name == "yt_dlp":
            version = getattr(mod.version, "__version__", "?")
        print(f"OK    {import_name:<12} {version or ''}")

    if failures:
        print(f"\nMissing required dependencies: {', '.join(failures)}")
        print("Fix with:  pip install -r requirements.txt")
        return 1

    print("\nAll required dependencies import cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
