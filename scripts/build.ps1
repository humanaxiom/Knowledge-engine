# Builds the images (ke-app, ke-gateway, ke-gates) and pulls the digest-pinned
# ones (PS-2.9); the PowerShell twin of build.sh. The only step that needs the
# network. Honors KE_ENV_FILE and COMPOSE_PROJECT_NAME.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

$composeArgs = @()
if ($env:KE_ENV_FILE) { $composeArgs += @('--env-file', $env:KE_ENV_FILE) }
docker compose @composeArgs --profile '*' build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker compose @composeArgs --profile '*' pull --ignore-buildable
exit $LASTEXITCODE
