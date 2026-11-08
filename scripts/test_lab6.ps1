$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
docker compose build tests
if ($LASTEXITCODE -ne 0) { throw 'Could not rebuild tests.' }
docker compose run --rm tests python -m pytest --collect-only -q
if ($LASTEXITCODE -ne 0) { throw 'Could not collect tests.' }
docker compose run --rm tests
if ($LASTEXITCODE -ne 0) { throw 'Integration tests failed; do not commit yet.' }
