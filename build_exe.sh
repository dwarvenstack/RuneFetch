#!/bin/bash
# RuneFetch — build single-file EXE on macOS / Linux
# For Linux: produces a Linux binary (not .exe)
# For macOS: produces a macOS app bundle
# Cross-compiling to Windows .exe from Linux is NOT supported by PyInstaller.
# Use build_exe.bat on a Windows machine for the Windows EXE.

set -e

echo ""
echo " ===================================================="
echo "   RuneFetch EXE Builder  |  by DwarvenStack"
echo " ===================================================="
echo ""

# Install deps
echo "[1/4] Installing dependencies..."
pip install -r requirements.txt -q
pip install pyinstaller -q

# Clean
echo "[2/4] Cleaning previous build..."
rm -rf build dist

# Build
echo "[3/4] Building binary (this takes 1-3 minutes)..."
python -m PyInstaller RuneFetch.spec --clean --noconfirm

# Done
echo "[4/4] Done!"
echo ""
echo " Output: dist/RuneFetch"
echo ""
echo " NOTE: ffmpeg is NOT bundled. Install separately:"
echo "   macOS:  brew install ffmpeg"
echo "   Linux:  sudo apt install ffmpeg"
echo ""
