$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
Push-Location -LiteralPath $repo
try {
    docker compose config -q
    if ($LASTEXITCODE -ne 0) { throw 'Invalid Compose configuration.' }
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw 'Lab 7 services could not start.' }
    docker compose build tests
    if ($LASTEXITCODE -ne 0) { throw 'Test image build failed.' }
    docker compose run --rm tests
    if ($LASTEXITCODE -ne 0) { throw 'A Lab 3-7 test failed. Do NOT commit yet.' }
    Invoke-RestMethod http://localhost:8000/ready
}
finally { Pop-Location }
