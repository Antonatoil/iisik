$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $repo
docker compose config -q
if ($LASTEXITCODE -ne 0) { throw 'Invalid Docker Compose configuration.' }
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Lab 6 containers failed to start. Check docker compose logs.' }
docker compose ps
Invoke-RestMethod http://localhost:8000/ready
