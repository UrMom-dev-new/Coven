param(
  [switch]$Clean,
  [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"
if ($PSVersionTable.PSVersion.Major -ge 7) {
  $PSNativeCommandUseErrorActionPreference = $true
}
$Repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Repo

if ($Clean) {
  Write-Host "Removing previous Windows build output..."
  Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
}

Write-Host "Installing Windows desktop dependencies..."
python -m pip install --upgrade pip
python -m pip install -e ".[desktop]"

Write-Host "Generating Windows version metadata..."
python scripts\generate-version-info.py

Write-Host "Building Coven portable bundle with PyInstaller..."
python -m PyInstaller packaging\Coven.spec --noconfirm --clean

$Bundle = Join-Path $Repo "dist\Coven"
$Exe = Join-Path $Bundle "Coven.exe"
$InternalPublic = Join-Path $Bundle "_internal\public\index.html"
$RootPublic = Join-Path $Bundle "public\index.html"
$InternalReference = Join-Path $Bundle "_internal\public\assets\reference\coven-approved-reference.png"
$RootReference = Join-Path $Bundle "public\assets\reference\coven-approved-reference.png"

if (-not (Test-Path $Exe)) {
  throw "Portable executable was not produced at $Exe"
}
if (-not ((Test-Path $InternalPublic) -or (Test-Path $RootPublic))) {
  throw "Bundled public web assets were not found in $Bundle"
}
if (-not ((Test-Path $InternalReference) -or (Test-Path $RootReference))) {
  throw "Approved reference image was not included in the portable bundle"
}

if (-not $SkipSmoke) {
  & (Join-Path $Repo "scripts\smoke-windows.ps1") -Exe $Exe -Token "windows-build-smoke-token"
}

Write-Host "Portable bundle: $Bundle"
