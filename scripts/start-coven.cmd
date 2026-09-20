@echo off
setlocal
set REPO=%~dp0..
set PORT=8765

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 or newer is required.
  exit /b 1
)

cd /d "%REPO%"
python -m coven.server --host 127.0.0.1 --port %PORT% --open
