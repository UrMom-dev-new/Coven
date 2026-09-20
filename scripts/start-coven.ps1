param(
  [int]$Port = 8765,
  [switch]$Demo,
  [switch]$Open,
  [switch]$Desktop
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
  $Python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $Python) {
  Write-Error "Python 3.11 or newer is required. Install Python, then run this launcher again."
}

try {
  $Health = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 1
  if ($Health.StatusCode -eq 200) {
    Write-Host "Coven is already running at http://127.0.0.1:$Port/"
    if ($Open) { Start-Process "http://127.0.0.1:$Port/" }
    exit 0
  }
} catch {
  # No existing instance answered on this port.
}

if ($Demo) {
  $env:COVEN_DEMO_MODE = "1"
}

Set-Location $Repo
$Module = "coven.server"
if ($Desktop) {
  $Module = "coven.desktop"
}
$Args = @("-m", $Module, "--port", "$Port")
if (-not $Desktop) { $Args = @("-m", $Module, "--host", "127.0.0.1", "--port", "$Port") }
if ($Open -and -not $Desktop) { $Args += "--open" }
& $Python.Source $Args
