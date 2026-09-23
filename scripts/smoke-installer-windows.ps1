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

$InstallLog = Join-Path $env:TEMP "coven-installer-smoke.log"
Remove-Item -Force $InstallLog -ErrorAction SilentlyContinue

Write-Host "Installing Coven to $InstallDir"
$InstallArgs = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /LOG=""$InstallLog"" /DIR=""$InstallDir"""
$Process = Start-Process -FilePath (Resolve-Path $Installer) -ArgumentList $InstallArgs -Wait -PassThru
if ($Process.ExitCode -ne 0) {
  if (Test-Path $InstallLog) {
    Get-Content $InstallLog | Select-Object -Last 80
  }
  throw "Installer exited with code $($Process.ExitCode)"
}

$Exe = Join-Path $InstallDir "Coven.exe"
for ($Attempt = 0; $Attempt -lt 20 -and -not (Test-Path $Exe); $Attempt++) {
  Start-Sleep -Milliseconds 500
}
if (-not (Test-Path $Exe)) {
  if (Test-Path $InstallLog) {
    Write-Host "Installer log tail:"
    Get-Content $InstallLog | Select-Object -Last 120
  }
  if (Test-Path $InstallDir) {
    Write-Host "Installed directory contents:"
    Get-ChildItem -Recurse -Force $InstallDir | Select-Object -First 80 | Format-Table FullName
  }
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
