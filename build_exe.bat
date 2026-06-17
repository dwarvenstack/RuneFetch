@echo off
:: ============================================================
::  RuneFetch — build single-file Windows EXE
::  Run this from inside the RuneFetch project folder.
:: ============================================================
setlocal

echo.
echo  ====================================================
echo    RuneFetch EXE Builder  ^|  by DwarvenStack
echo  ====================================================
echo.

:: ── Check Python ────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ from https://python.org
    pause & exit /b 1
)

:: ── Install / upgrade dependencies ──────────────────────────
echo [1/4] Installing dependencies...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet
python -m pip install pyinstaller --quiet
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause & exit /b 1
)

:: ── Clean previous build ────────────────────────────────────
echo [2/4] Cleaning previous build...
if exist build   rmdir /s /q build
if exist dist    rmdir /s /q dist

:: ── Run PyInstaller ─────────────────────────────────────────
echo [3/4] Building EXE (this takes 1-3 minutes)...
python -m PyInstaller RuneFetch.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller build failed. Check output above.
    pause & exit /b 1
)

:: ── Done ────────────────────────────────────────────────────
echo [4/4] Done!
echo.
echo  Output: dist\RuneFetch.exe
echo.
echo  NOTE: ffmpeg is NOT bundled. Users need ffmpeg on PATH
echo  for video merging and audio extraction to work.
echo  Install: winget install Gyan.FFmpeg
echo.
if exist dist\RuneFetch.exe (
    for %%F in (dist\RuneFetch.exe) do echo  File size: %%~zF bytes
)

pause
