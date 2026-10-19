# Brings the stack up (PS-2.9, architecture 2.4 Scripts); the PowerShell twin
# of launch.sh. Creates .env from .env.example if it is missing, checks Docker
# Compose >= 2.24 and Docker Engine >= 28 (the isolated backend bridge needs
# it), refuses a non-loopback published address outside dev (PS-2.14, Q33a),
# then `compose up -d --no-build --wait` and prints the URLs.
#
# KE_ENV and the published addresses are read from `docker compose config`
# with the same --env-file `up` will use: never our own parser, never
# .env.example. A missing or empty KE_ENV is not dev (fail closed).
# Honors KE_ENV_FILE and COMPOSE_PROJECT_NAME.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

$envFile = if ($env:KE_ENV_FILE) { $env:KE_ENV_FILE } else { '.env' }
if (-not (Test-Path $envFile)) {
    if ($env:KE_ENV_FILE) {
        Write-Error "KE_ENV_FILE does not exist: $envFile"
        exit 1
    }
    Copy-Item '.env.example' '.env'
    Write-Host 'created .env from .env.example (placeholder secrets; edit it before any use beyond local development)'
}

function Get-VersionNumber([string]$Text) {
    $parsed = $null
    if ([version]::TryParse(($Text.Trim().TrimStart('v') -replace '[^0-9.].*$', ''), [ref]$parsed)) {
        return $parsed
    }
    return $null
}

$minimum = [version]'2.24'
$found = (docker compose version --short 2>$null | Out-String).Trim().TrimStart('v')
$parsed = Get-VersionNumber $found
if ($null -eq $parsed -or $parsed -lt $minimum) {
    Write-Error "Docker Compose >= $minimum is required (found: $found)"
    exit 1
}

# Older engines ignore gateway_mode_ipv4 without an error (security M-2), so
# the server version must be exactly MAJOR.MINOR.PATCH with MAJOR >= 28.
$engineMinimum = 28
$engine = (@(docker version --format '{{.Server.Version}}' 2>$null) -join "`n")
if ($LASTEXITCODE -ne 0) {
    Write-Error 'cannot read the Docker Engine version; is the daemon running?'
    exit 1
}
if ($engine -notmatch '^[0-9]+\.[0-9]+\.[0-9]+\z' -or [int64]($engine.Split('.')[0]) -lt $engineMinimum) {
    Write-Error "Docker Engine >= $engineMinimum is required (found: $engine)"
    exit 1
}

$composeArgs = @()
if ($env:KE_ENV_FILE) { $composeArgs += @('--env-file', $env:KE_ENV_FILE) }

$json = docker compose @composeArgs config --format json | Out-String
if ($LASTEXITCODE -ne 0) {
    Write-Error 'docker compose config failed; cannot resolve KE_ENV and KE_BIND_ADDRESS'
    exit 1
}
$model = $json | ConvertFrom-Json
$keEnv = ''
$ports = @()
foreach ($service in $model.services.PSObject.Properties.Value) {
    if (-not $keEnv -and $service.environment -and $service.environment.KE_ENV) {
        $keEnv = [string]$service.environment.KE_ENV
    }
    if ($service.ports) { $ports += @($service.ports) }
}

# IPv4 only; IPv6 is refused in every env. Same rule as the engine's startup
# refusal and docker/gateway/10-ke-bind-check.sh. A published port with no
# host_ip would listen on every interface: treated as 0.0.0.0.
$octet = '(0|[1-9][0-9]{0,2})'
$bind = '127.0.0.1'
foreach ($port in $ports) {
    $hostIp = if ($port.host_ip) { [string]$port.host_ip } else { '0.0.0.0' }
    $valid = $hostIp -match "^$octet\.$octet\.$octet\.$octet$"
    if ($valid) {
        foreach ($part in $Matches[1..4]) { if ([int]$part -gt 255) { $valid = $false } }
    }
    if (-not $valid) {
        Write-Error 'KE_BIND_ADDRESS is not an IPv4 address (IPv6 is not supported)'
        exit 1
    }
    $bind = $hostIp
    if (($hostIp -split '\.')[0] -ne '127') {
        if ($keEnv -ceq 'dev') {
            Write-Warning 'KE_BIND_ADDRESS is not loopback; the stack will be published beyond this host without authentication (dev only)'
        } else {
            Write-Error 'KE_BIND_ADDRESS is not loopback and KE_ENV is not dev; refusing to launch (until auth-audit lands)'
            exit 1
        }
    }
}

docker compose @composeArgs up -d --no-build --wait
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host 'stack is up:'
Write-Host ("  api:     http://{0}:{1}" -f $bind, @($ports)[0].published)
Write-Host ("  phoenix: http://{0}:{1}" -f $bind, @($ports)[1].published)
