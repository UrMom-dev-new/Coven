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

$TempRoot = $env:RUNNER_TEMP
if (-not $TempRoot) {
  $TempRoot = [System.IO.Path]::GetTempPath()
}
$SelfTestLog = Join-Path $TempRoot "coven-self-test-$PID.log"
Remove-Item $SelfTestLog -Force -ErrorAction SilentlyContinue

function Show-SelfTestLog {
  if (Test-Path $SelfTestLog) {
    Write-Host "Coven.exe self-test log:"
    Get-Content $SelfTestLog
  } else {
    Write-Host "Coven.exe self-test log was not created at $SelfTestLog"
  }
}

Write-Host "Running Coven.exe self-test with a $TimeoutSeconds second timeout..."
$Smoke = Start-Process -FilePath $Exe -ArgumentList @(
  "--self-test",
  "--auth-token",
  $Token,
  "--self-test-timeout",
  "12",
  "--self-test-log",
  $SelfTestLog
) -PassThru

$Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while (-not $Smoke.HasExited -and (Get-Date) -lt $Deadline) {
  Start-Sleep -Milliseconds 250
  $Smoke.Refresh()
}

if (-not $Smoke.HasExited) {
  Stop-Process -Id $Smoke.Id -Force -ErrorAction SilentlyContinue
  Show-SelfTestLog
  throw "Coven.exe self-test timed out after $TimeoutSeconds seconds"
}

if ($Smoke.ExitCode -ne 0) {
  Show-SelfTestLog
  throw "Coven.exe self-test failed with exit code $($Smoke.ExitCode)"
}

Show-SelfTestLog
Write-Host "Coven.exe self-test completed successfully."
