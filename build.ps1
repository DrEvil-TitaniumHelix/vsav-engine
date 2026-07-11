# build.ps1 — one-command Windows build for The Vassal.
# Produces dist\The Vassal.exe (single file, double-click to run).
#
# Prereqs (one time):  pip install pywebview pyinstaller
# Usage:               powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "Building Legality Engine for VASSAL (Windows, one-file)..." -ForegroundColor Cyan
Write-Host "Staging game assets..." -ForegroundColor Cyan
python build_stage.py
pyinstaller --noconfirm --clean thevassal.spec
$exe = Join-Path $PSScriptRoot "dist\Legality Engine for VASSAL.exe"
if (Test-Path $exe) {
    $mb = "{0:N1}" -f ((Get-Item $exe).Length / 1MB)
    Write-Host "OK  ->  $exe  ($mb MB)" -ForegroundColor Green
    Write-Host "Double-click it to run. Testers: see RELEASE_README.md about the antivirus warning." -ForegroundColor Yellow
} else {
    Write-Host "BUILD FAILED — no exe produced." -ForegroundColor Red
    exit 1
}
