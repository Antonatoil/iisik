$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose could not start the project.' }
docker compose exec -T gateway pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed. Check Docker logs.' }
