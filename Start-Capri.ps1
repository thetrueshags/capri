$ErrorActionPreference = 'Stop'
$capriPython = Join-Path $PSScriptRoot '.venv/Scripts/pythonw.exe'
if (-not (Test-Path -LiteralPath $capriPython)) {
    throw 'Run Setup-Capri.cmd once to install the desktop dependencies.'
}
$capriTemp = Join-Path $PSScriptRoot 'data/tmp'
New-Item -ItemType Directory -Force -Path $capriTemp | Out-Null
$env:TEMP = $capriTemp
$env:TMP = $capriTemp
$env:PYTHONDONTWRITEBYTECODE = '1'
Start-Process -FilePath $capriPython -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -ArgumentList @('-m', 'capri.companion.app')
