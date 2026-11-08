$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
# Do NOT pass -v: keep persistent PostgreSQL, Redis, Kafka volumes.
docker compose down
if ($LASTEXITCODE -ne 0) { throw 'Could not stop the lab containers.' }
