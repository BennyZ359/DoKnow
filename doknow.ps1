# Run from any directory. Does not install dependencies or alter execution policy.
$ErrorActionPreference = 'Stop'
$doknowPython = Join-Path $PSScriptRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $doknowPython)) {
    $doknowPython = (Get-Command python -ErrorAction Stop).Source
}
& $doknowPython (Join-Path $PSScriptRoot 'scripts\local.py') @args
exit $LASTEXITCODE
