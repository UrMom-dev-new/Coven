param(
  [switch]$Clean,
  [switch]$SkipSmoke
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
  $Smoke = Start-Process -FilePath $Exe -ArgumentList @("--self-test", "--auth-token", "windows-build-smoke-token") -Wait -PassThru
  if ($Smoke.ExitCode -ne 0) {
    throw "Portable executable self-test failed with exit code $($Smoke.ExitCode)"
  }
}

Write-Host "Portable bundle: $Bundle"
