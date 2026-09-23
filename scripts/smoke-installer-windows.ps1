param(
  [string]$Installer = ".\dist\installer\Coven-Setup-x64.exe",
  [string]$InstallDir = "",
  [string]$Token = "installer-smoke-token",
  [int]$TimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"
if ($PSVersionTable.PSVersion.Major -ge 7) {
  $PSNativeCommandUseErrorActionPreference = $true
}

$Repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Repo

if (-not (Test-Path $Installer)) {
  throw "Installer not found: $Installer"
}
if (-not $InstallDir) {
  $InstallDir = Join-Path $env:TEMP "Coven Install β"
}

if (Test-Path $InstallDir) {
  Remove-Item -Recurse -Force $InstallDir
}

Write-Host "Installing Coven to $InstallDir"
& $Installer /VERYSILENT /SUPPRESSMSGBOXES /NORESTART "/DIR=$InstallDir"

$Exe = Join-Path $InstallDir "Coven.exe"
if (-not (Test-Path $Exe)) {
  throw "Installed executable was not found at $Exe"
}

Write-Host "Running installed executable self-test"
& (Join-Path $Repo "scripts\smoke-windows.ps1") -Exe $Exe -Token $Token -TimeoutSeconds $TimeoutSeconds

$Uninstall = Join-Path $InstallDir "unins000.exe"
if (Test-Path $Uninstall) {
  Write-Host "Uninstalling Coven from disposable smoke directory"
  & $Uninstall /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
} else {
  throw "Uninstaller was not found at $Uninstall"
}

Write-Host "Installer smoke passed."
