$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Lab 6 startup failed.' }
docker compose ps
Write-Host 'GraphQL: http://localhost:8000/graphql/'
Write-Host 'Ready:   http://localhost:8000/ready'
