@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Capri.ps1"
if errorlevel 1 (
  echo Capri could not start. Run Setup-Capri.cmd first.
  pause
  exit /b 1
)
