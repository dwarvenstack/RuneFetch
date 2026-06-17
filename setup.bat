@echo off
:: RuneFetch — Windows setup script
:: Run once after cloning the repository.

echo ============================================
echo   RuneFetch setup  ^|  by DwarvenStack
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

:: Check ffmpeg
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] ffmpeg not found on PATH.
    echo   Video merging and audio extraction require ffmpeg.
    echo   Install via: winget install Gyan.FFmpeg
    echo   Or download from: https://ffmpeg.org/download.html
    echo.
)

:: Install Python dependencies
echo Installing Python dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if errorlevel 1 (
    echo [ERROR] Dependency installation failed. Check the error above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Setup complete!  Run:  python main.py
echo ============================================
pause
