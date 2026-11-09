# Read-only security-aware cache demonstration. Uses a local demo password; never prints it.
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
Push-Location -LiteralPath $repo
try {
    $envline = Get-Content '.env' | Where-Object { $_ -match '^LAB5_DEMO_PASSWORD=' } | Select-Object -First 1
    if (-not $envline) { throw 'LAB5_DEMO_PASSWORD is missing in local .env' }
    $password = $envline.Substring('LAB5_DEMO_PASSWORD='.Length).Trim().Trim('"')
    $loginBody = @{
        query = 'mutation($input:LoginInput!){ login(input:$input){ token } }'
        variables = @{ input = @{ email = 'student@example.test'; password = $password } }
    } | ConvertTo-Json -Depth 8 -Compress
    $login = Invoke-RestMethod -Uri 'http://localhost:8000/graphql/' -Method Post `
        -ContentType 'application/json' -Body $loginBody
    if ($login.errors -or -not $login.data.login.token) {
        throw ('JWT login failed: ' + ($login.errors | ConvertTo-Json -Depth 5))
    }
    $jwt = $login.data.login.token
    $header = @{ Authorization = 'Bearer ' + $jwt; 'X-Correlation-ID' = 'lab7-cache-demo' }
    $query = @{query = 'query{ subjects(page:{limit:20,offset:0}){items{id name}} }'} | ConvertTo-Json -Compress
    for ($i=1; $i -le 2; $i++) {
        $result = Invoke-RestMethod -Uri 'http://localhost:8000/graphql/' -Method Post `
            -ContentType 'application/json' -Headers $header -Body $query
        if ($result.errors) { throw ($result.errors | ConvertTo-Json -Depth 5) }
        Write-Host ('GraphQL subjects request #{0}: {1} items' -f $i, $result.data.subjects.items.Count)
    }
    Write-Host 'Cache logs: look for catalog_cache with hit/miss, correlation_id=lab7-cache-demo.'
    docker compose logs --tail=50 catalog
}
finally { Pop-Location }
