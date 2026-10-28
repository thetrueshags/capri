@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup-Capri.ps1" %*
if errorlevel 1 (
  echo Setup failed. Read the error above.
  pause
  exit /b 1
)
echo Setup complete. You can close this window.
pause
