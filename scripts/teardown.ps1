# Stops and removes the project's containers and networks (PS-2.9); the
# PowerShell twin of teardown.sh. Named volumes are kept unless -Volumes is
# given. Honors KE_ENV_FILE and COMPOSE_PROJECT_NAME.
param([switch]$Volumes)
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

$composeArgs = @()
if ($env:KE_ENV_FILE) { $composeArgs += @('--env-file', $env:KE_ENV_FILE) }
$down = @()
if ($Volumes) { $down += '--volumes' }
docker compose @composeArgs down @down
exit $LASTEXITCODE
