param(
  [Parameter(Mandatory = $true)]
  [string]$Exe,
  [string]$Token = "windows-build-smoke-token",
  [int]$TimeoutSeconds = 45
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Exe)) {
  throw "Coven.exe missing at $Exe"
}

Write-Host "Running Coven.exe self-test with a $TimeoutSeconds second timeout..."
$Smoke = Start-Process -FilePath $Exe -ArgumentList @(
  "--self-test",
  "--auth-token",
  $Token,
  "--self-test-timeout",
  "12"
) -PassThru

$Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while (-not $Smoke.HasExited -and (Get-Date) -lt $Deadline) {
  Start-Sleep -Milliseconds 250
  $Smoke.Refresh()
}

if (-not $Smoke.HasExited) {
  Stop-Process -Id $Smoke.Id -Force -ErrorAction SilentlyContinue
  throw "Coven.exe self-test timed out after $TimeoutSeconds seconds"
}

if ($Smoke.ExitCode -ne 0) {
  throw "Coven.exe self-test failed with exit code $($Smoke.ExitCode)"
}

Write-Host "Coven.exe self-test completed successfully."
