# Builds an unsigned MSIX from the PyInstaller output for Microsoft Store upload.
# Usage (from the project root):
#   powershell -ExecutionPolicy Bypass -File packaging\msix\build_msix.ps1
$ErrorActionPreference = "Stop"

$MsixDir  = $PSScriptRoot
$DistDir  = Join-Path $MsixDir "..\dist\EngPlayer"
$WorkDir  = Join-Path $MsixDir "build"
$Staging  = Join-Path $WorkDir "staging"
$PriWork  = Join-Path $WorkDir "pri"
$Version  = ([xml](Get-Content (Join-Path $MsixDir "AppxManifest.xml"))).Package.Identity.Version
$Output   = Join-Path $MsixDir "EngPlayer_${Version}_x64.msix"

if (-not (Test-Path (Join-Path $DistDir "EngPlayer.exe"))) {
    throw "PyInstaller output not found: $DistDir. Build with EngPlayer.spec first."
}

$Kit = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\makeappx.exe" -ErrorAction SilentlyContinue |
       Sort-Object FullName -Descending | Select-Object -First 1
if (-not $Kit) { throw "makeappx.exe not found. Install the Windows SDK." }
$MakeAppx = $Kit.FullName
$MakePri  = Join-Path $Kit.DirectoryName "makepri.exe"
Write-Host "Using $MakeAppx"

if (Test-Path $WorkDir) { Remove-Item $WorkDir -Recurse -Force }
New-Item -ItemType Directory -Path $Staging, $PriWork | Out-Null

Copy-Item (Join-Path $DistDir "*") $Staging -Recurse
Copy-Item (Join-Path $MsixDir "AppxManifest.xml") $Staging
Copy-Item (Join-Path $MsixDir "Assets") $Staging -Recurse

# Index only the manifest and logos, so locale folders in _internal are not treated as resources.
Copy-Item (Join-Path $MsixDir "AppxManifest.xml") $PriWork
Copy-Item (Join-Path $MsixDir "Assets") $PriWork -Recurse
$PriConfig = Join-Path $WorkDir "priconfig.xml"
& $MakePri createconfig /cf $PriConfig /dq en-US /o | Out-Host
if ($LASTEXITCODE -ne 0) { throw "makepri createconfig failed" }
& $MakePri new /pr $PriWork /cf $PriConfig /mn (Join-Path $PriWork "AppxManifest.xml") /of (Join-Path $Staging "resources.pri") /o | Out-Host
if ($LASTEXITCODE -ne 0) { throw "makepri new failed" }

& $MakeAppx pack /d $Staging /p $Output /o | Out-Host
if ($LASTEXITCODE -ne 0) { throw "makeappx pack failed" }

Write-Host ""
Write-Host "Package: $Output"
Write-Host "Local test: Add-AppxPackage -Register `"$Staging\AppxManifest.xml`""
