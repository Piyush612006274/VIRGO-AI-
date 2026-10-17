$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot "..\..\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Virgo development environment is not available."
}

& $python -m maturin build --release --locked
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Output "Virgo production wheel is available under target/wheels/."
