$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Failed to start lab3.' }
docker compose ps
Write-Host 'GraphQL: http://localhost:8000/graphql/'
Write-Host 'Health: http://localhost:8000/ready'
Write-Host 'Tokens: demo-student-token / demo-teacher-token / demo-admin-token'
