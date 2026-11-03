$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose could not start the services.' }
# Isolated, temporary test process; Gateway has NO direct DB connection.
docker compose run --rm tests
if ($LASTEXITCODE -ne 0) { throw 'Tests failed. Check service logs.' }
