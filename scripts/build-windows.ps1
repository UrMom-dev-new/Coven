param(
  [switch]$Clean
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Repo

if ($Clean) {
  Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
}

python -m pip install --upgrade pip
python -m pip install -e ".[desktop]"
python -m PyInstaller packaging\Coven.spec --noconfirm --clean

Write-Host "Portable bundle: $Repo\dist\Coven"
