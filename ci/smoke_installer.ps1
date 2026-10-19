param([string]$Version = (Get-Content (Join-Path $PSScriptRoot '../VERSION') -Raw).Trim(), [switch]$SkipLiveDownload)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location $root
$installer = Join-Path $root "dist_installer/RuneFetch-Setup-$Version.exe"
$target = [IO.Path]::GetFullPath((Join-Path $root ("build/installer-test-$Version-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))))
if (-not $target.StartsWith($root + [IO.Path]::DirectorySeparatorChar)) { throw 'Test target escapes workspace' }

function RegistrationSnapshot {
    $records = foreach ($registryRoot in @('HKCU:', 'HKLM:')) {
        foreach ($prefix in @('Software', 'Software/WOW6432Node')) {
            $key = "$registryRoot/$prefix/Microsoft/Windows/CurrentVersion/Uninstall/{8F3A6E52-1C4D-4B7A-9E23-6D5F8C1A0B94}_is1"
            if (Test-Path $key) {
                $entry = Get-ItemProperty $key
                [pscustomobject]@{ Key=$key; Version=$entry.DisplayVersion; Location=$entry.InstallLocation; Uninstall=$entry.UninstallString }
            }
        }
    }
    return ($records | ConvertTo-Json -Compress)
}

$before = RegistrationSnapshot
function InstallTestPayload {
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOCLOSEAPPLICATIONS', '/NORESTARTAPPLICATIONS', '/NOICONS', '/TESTINSTALL=1', ('/DIR="{0}"' -f $target), ('/LOG="{0}"' -f (Join-Path $root 'build/installer-smoke.log')))
    $process = Start-Process -FilePath $installer -ArgumentList $arguments -WindowStyle Hidden -PassThru -Wait
    if ($process.ExitCode -ne 0) { throw "Installer failed: $($process.ExitCode)" }
}
InstallTestPayload
$files = @(Get-ChildItem (Join-Path $root 'dist/RuneFetch') -Recurse -File)
foreach ($source in $files) {
    $relative = [IO.Path]::GetRelativePath((Join-Path $root 'dist/RuneFetch'), $source.FullName)
    $installed = Join-Path $target $relative
    if (-not (Test-Path -LiteralPath $installed)) { throw "Missing installed file: $relative" }
    if ((Get-FileHash -LiteralPath $source.FullName).Hash -ne (Get-FileHash -LiteralPath $installed).Hash) { throw "Installed bytes differ: $relative" }
}
Write-Output "PASS: installer extracted all $($files.Count) payload files with matching hashes"
$exe = Join-Path $target 'RuneFetch.exe'
[IO.File]::WriteAllText($exe, 'stale test payload')
InstallTestPayload
if ((Get-FileHash $exe).Hash -ne (Get-FileHash 'dist/RuneFetch/RuneFetch.exe').Hash) { throw 'Installer did not replace stale executable' }
Write-Output 'PASS: installer replaced a stale executable on reinstall'
if ((RegistrationSnapshot) -ne $before) { throw 'Test install changed normal app registration' }
Write-Output 'PASS: personal installation registration preserved'
$python = Join-Path $root '.venv/Scripts/python.exe'
if ($SkipLiveDownload) {
    & $python ci/smoke_bundle.py --exe $exe
} else {
    & $python ci/smoke_bundle.py --exe $exe --download-url 'https://www.youtube.com/shorts/HysJ32YP0x0' --download-dir (Join-Path $root ('build/installed-download-' + (Get-Date -Format 'yyyyMMdd-HHmmss')))
}
if ($LASTEXITCODE -ne 0) { throw 'Installed application verification failed' }
@{version=$Version; installedPath=$target; verifiedFiles=$files.Count; registrationPreserved=$true; reinstallPassed=$true; installedDownloadPassed=(-not $SkipLiveDownload)} | ConvertTo-Json | Set-Content build/installer-test-result.json
if ($SkipLiveDownload) { Write-Output 'PASS: installed application starts; live download skipped explicitly' }
else { Write-Output 'PASS: installed application starts and completes a real download' }
