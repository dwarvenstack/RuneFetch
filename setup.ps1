# RuneFetch — development environment setup.
#
# Creates a project-local .venv and installs everything into it. Using a venv
# rather than the system Python matters: RuneFetch broke in Aug 2026 when a
# Python upgrade replaced the interpreter's site-packages and every dependency
# vanished. A .venv inside the project is unaffected by that.
#
# Usage:   .\setup.ps1          install / repair the environment
#          .\setup.ps1 -Check   verify only, change nothing

param([switch]$Check)

$ErrorActionPreference = "Stop"
$root   = $PSScriptRoot
$venv   = Join-Path $root ".venv"
$python = Join-Path $venv "Scripts\python.exe"

function Section($text) { Write-Host "`n== $text" -ForegroundColor Cyan }

if ($Check) {
    Section "Checking environment"
    if (-not (Test-Path $python)) {
        Write-Host "No .venv found. Run .\setup.ps1 to create it." -ForegroundColor Yellow
        exit 1
    }
    & $python ci\check_imports.py
    exit $LASTEXITCODE
}

Section "Python"
$sys = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $sys) { throw "Python not found on PATH. Install Python 3.11+ first." }
& python --version

Section "Virtual environment"
if (Test-Path $python) {
    Write-Host ".venv already exists — reusing it."
} else {
    & python -m venv $venv
    Write-Host "Created $venv"
}

Section "Dependencies"
& $python -m pip install --upgrade pip --quiet
& $python -m pip install -r (Join-Path $root "requirements.txt")

Section "ffmpeg"
# Required to merge separate video/audio streams into one MP4. RuneFetch also
# offers to fetch it on first run, but flagging it here is clearer.
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-Host "ffmpeg found: $((Get-Command ffmpeg).Source)"
} else {
    Write-Host "ffmpeg NOT found — merged-quality downloads will fail." -ForegroundColor Yellow
    Write-Host "Install it with:  scoop install ffmpeg   (or winget install ffmpeg)"
}

Section "Verifying"
& $python ci\check_imports.py
if ($LASTEXITCODE -ne 0) { throw "Dependency check failed." }
& $python ci\check_modules.py
if ($LASTEXITCODE -ne 0) { throw "Module check failed." }

Write-Host "`nReady. Start RuneFetch with:" -ForegroundColor Green
Write-Host "    .\.venv\Scripts\python.exe app.py"
