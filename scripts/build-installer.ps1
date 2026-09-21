param(
  [string]$IsccPath = ""
)

$ErrorActionPreference = "Stop"
if ($PSVersionTable.PSVersion.Major -ge 7) {
  $PSNativeCommandUseErrorActionPreference = $true
}

$Repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Repo

$Bundle = Join-Path $Repo "dist\Coven"
$Exe = Join-Path $Bundle "Coven.exe"
$Script = Join-Path $Repo "packaging\installer\Coven.iss"
$OutputDir = Join-Path $Repo "dist\installer"

if (-not (Test-Path $Exe)) {
  throw "Portable bundle must be built before the installer. Missing $Exe"
}
if (-not (Test-Path $Script)) {
  throw "Installer script was not found at $Script"
}

if (-not $IsccPath) {
  $Command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
  if ($Command) {
    $IsccPath = $Command.Source
  }
}

if (-not $IsccPath) {
  $Candidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
  )
  foreach ($Candidate in $Candidates) {
    if ($Candidate -and (Test-Path $Candidate)) {
      $IsccPath = $Candidate
      break
    }
  }
}

if (-not $IsccPath -or -not (Test-Path $IsccPath)) {
  throw "Inno Setup compiler ISCC.exe was not found. Install Inno Setup 6 or pass -IsccPath."
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

Write-Host "Compiling Coven installer with Inno Setup..."
& $IsccPath "/O$OutputDir" $Script

$Installer = Get-ChildItem -Path $OutputDir -Filter "CovenSetup-*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $Installer) {
  throw "Installer executable was not produced in $OutputDir"
}

Write-Host "Unsigned installer artifact: $($Installer.FullName)"
