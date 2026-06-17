@echo off
:: RuneFetch — Windows setup script
:: Run once after cloning the repository.

echo ============================================
echo   RuneFetch setup  ^|  by DwarvenStack
echo ============================================
echo.

:: ── Check Python ─────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo   Install Python 3.10+ from https://python.org
    echo   Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% found.

:: ── Check pip ────────────────────────────────────────────────
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pip not available. Run:  python -m ensurepip
    pause
    exit /b 1
)

:: ── Upgrade pip ──────────────────────────────────────────────
echo.
echo [1/3] Upgrading pip...
python -m pip install --upgrade pip --quiet

:: ── Install Python dependencies ───────────────────────────────
echo [2/3] Installing Python dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Dependency installation failed. Check the output above.
    pause
    exit /b 1
)

:: ── Check ffmpeg ──────────────────────────────────────────────
echo.
echo [3/3] Checking ffmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] ffmpeg not found on PATH.
    echo   RuneFetch will prompt you to auto-download ffmpeg on first launch.
    echo   To install manually:
    echo     winget install Gyan.FFmpeg
    echo   or download from https://ffmpeg.org/download.html
) else (
    echo [OK] ffmpeg found.
)

echo.
echo ============================================
echo   Setup complete!
echo.
echo   Run the app:
echo     python main.py
echo.
echo   Browser Extension:
echo     1. Open chrome://extensions
echo     2. Enable Developer mode
echo     3. Click "Load unpacked"
echo     4. Select the browser_extension\ folder
echo     5. Open Settings in RuneFetch and copy
echo        the bridge token to pair the extension.
echo ============================================
pause
