param([switch] $Development)
$ErrorActionPreference = 'Stop'
$capriTemp = Join-Path $PSScriptRoot 'data/tmp'
New-Item -ItemType Directory -Force -Path $capriTemp | Out-Null
$env:TEMP = $capriTemp
$env:TMP = $capriTemp
if (-not $env:PIP_CACHE_DIR) { $env:PIP_CACHE_DIR = Join-Path $PSScriptRoot '.cache/pip' }
$env:PYTHONDONTWRITEBYTECODE = '1'
$capriPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $capriPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv (Join-Path $PSScriptRoot '.venv')
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -c "import sys; assert sys.version_info[:2] == (3,12), 'Install Python 3.12 (64-bit) first.'"
        if ($LASTEXITCODE) { throw 'Python 3.12 (64-bit) is required.' }
        & python -m venv (Join-Path $PSScriptRoot '.venv')
    } else { throw 'Install Python 3.12 (64-bit), then run setup again.' }
    if ($LASTEXITCODE) { throw 'Could not create the Python 3.12 environment.' }
}
& $capriPython -c "import struct,sys; assert sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8, 'Python 3.12 (64-bit) is required.'"
if ($LASTEXITCODE) { throw 'The environment must use Python 3.12 (64-bit).' }
$capriRequirements = if ($Development) { 'requirements-dev.txt' } else { 'requirements.txt' }
& $capriPython -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot $capriRequirements)
if ($LASTEXITCODE) { throw 'Could not install the desktop dependencies.' }
Push-Location $PSScriptRoot
try {
    & $capriPython -c "from capri.companion.config import Config; c=Config(); print('Private seed prompt:', c.directory / 'persona.txt')"
    if ($LASTEXITCODE) { throw 'Could not initialize the private profile.' }
} finally { Pop-Location }
Write-Output 'Ready. Double-click Start-Capri.cmd, or run Start-Capri.ps1.'
Write-Output 'Chat is optional: install/run Ollama and pull qwen2.5:3b, or choose another installed local model in Settings.'
