$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$ver = (Select-String -Path ui\server.py -Pattern '^VERSION = "([^"]+)"').Matches[0].Groups[1].Value
python -m PyInstaller --noconfirm --clean thevassal.spec
if ($LASTEXITCODE -ne 0) { Write-Host "BUILD FAILED"; exit 1 }
$dir = Join-Path $PSScriptRoot "dist\LegalityEngine"
if (-not (Test-Path (Join-Path $dir "Legality Engine for VASSAL.exe"))) { Write-Host "BUILD FAILED"; exit 1 }
Copy-Item RELEASE_README.md $dir
$art = Get-ChildItem $dir -Recurse -File -Include *.png,*.jpg,*.jpeg,*.bmp,*.gif,*.vsav,*.vmod,*.pdf
if ($art) { $art | ForEach-Object { Write-Host "ART IN BUILD: $($_.FullName)" }; exit 1 }
$zip = Join-Path $PSScriptRoot "dist\LegalityEngine-$ver-win64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path (Join-Path $dir "*") -DestinationPath $zip
Write-Host ("OK  ->  {0}  ({1:N1} MB)" -f $zip, ((Get-Item $zip).Length / 1MB))
