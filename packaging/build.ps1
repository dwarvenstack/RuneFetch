param([switch]$SkipBundle)

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$python = Join-Path $PWD '.venv\Scripts\python.exe'
$version = (Get-Content VERSION -Raw).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw 'VERSION must be X.Y.Z' }
$compiler = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
if (-not (Test-Path $compiler)) { throw 'Install Inno Setup 6 first.' }

foreach ($check in @('check_imports', 'check_modules', 'smoke_update', 'smoke_ws', 'test_update_download')) {
    & $python "ci/$check.py"
    if ($LASTEXITCODE -ne 0) { throw "$check failed" }
}

if (-not $SkipBundle) {
    & $python -m PyInstaller --noconfirm --clean --windowed --onedir `
        --name RuneFetch --icon assets/runefetch_icon.png `
        --add-data 'webui;webui' --add-data 'assets;assets' --add-data 'VERSION;.' `
        --collect-all webview --collect-all spotdl --collect-data pykakasi `
        --hidden-import pystray._win32 app.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
}

$bundledVersion = (Get-Content dist/RuneFetch/_internal/VERSION -Raw).Trim()
if ($bundledVersion -ne $version) { throw 'Bundle version differs from VERSION; rebuild.' }
& $python ci/check_bundle.py
if ($LASTEXITCODE -ne 0) { throw 'Packaged Spotify worker check failed' }
Copy-Item README.md,LICENSE dist/RuneFetch/
Copy-Item browser_extension dist/RuneFetch/ -Recurse -Force
& $python -m pip freeze | Set-Content dist/RuneFetch/requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Cannot record dependencies' }
& $python -c "from PIL import Image; Image.open('assets/runefetch_icon.png').save('assets/runefetch_icon.ico', sizes=[(16,16),(32,32),(48,48),(256,256)])"
if ($LASTEXITCODE -ne 0) { throw 'Icon conversion failed' }
& $compiler "/DMyAppVersion=$version" packaging/RuneFetch.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
$installer = "dist_installer/RuneFetch-Setup-$version.exe"
$hash = (Get-FileHash $installer -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  RuneFetch-Setup-$version.exe" | Set-Content "$installer.sha256" -Encoding ascii
Write-Host "Installer ready: $installer"
