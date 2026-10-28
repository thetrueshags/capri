param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('idle','working','waiting','ready','blocked')]
    [string] $State,
    [string] $Source = 'software',
    [string] $Session = 'default',
    [string] $Project = ''
)
& (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'capri/companion/bridge.py') --state $State --source $Source --session $Session --project $Project
