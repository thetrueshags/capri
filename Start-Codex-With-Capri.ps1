# This adds observational hooks to this new Codex invocation only.
param([Parameter(ValueFromRemainingArguments = $true)][string[]] $CodexArguments)
$ErrorActionPreference = 'Stop'
$capriTemp = Join-Path $PSScriptRoot 'data/tmp'
New-Item -ItemType Directory -Force -Path $capriTemp | Out-Null
$env:TEMP = $capriTemp
$env:TMP = $capriTemp
$env:PYTHONDONTWRITEBYTECODE = '1'
& (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'tools/codex_with_capri.py') @CodexArguments
exit $LASTEXITCODE
