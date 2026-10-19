# Stops and removes the project's containers and networks (PS-2.9); the
# PowerShell twin of teardown.sh. Named volumes are kept unless -Volumes is
# given. Honors KE_ENV_FILE and COMPOSE_PROJECT_NAME.
#
# Afterwards it lists what is still labelled with the project (containers and
# networks, plus volumes when -Volumes was asked) and exits non-zero if
# anything is left, naming it. It only reports: it never removes a leftover
# itself (F3, security L-9).
param([switch]$Volumes)
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

$composeArgs = @()
if ($env:KE_ENV_FILE) { $composeArgs += @('--env-file', $env:KE_ENV_FILE) }
$down = @()
if ($Volumes) { $down += '--volumes' }

# The project name is the one compose resolves, not a guess; without it the
# leftover check could not be scoped, so nothing is taken down.
$config = docker compose @composeArgs config
if ($LASTEXITCODE -ne 0) {
    [Console]::Error.WriteLine('teardown: FAIL (docker compose config failed)')
    exit 1
}
$project = ($config | Where-Object { $_ -match '^name:\s*(\S+)' } | Select-Object -First 1)
if ($project) { $project = ($project -replace '^name:\s*', '').Trim() }
if (-not $project) {
    [Console]::Error.WriteLine('teardown: FAIL (cannot read the compose project name)')
    exit 1
}

docker compose @composeArgs down @down
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$filter = "label=com.docker.compose.project=$project"
$left = @()
$containers = docker ps -a --filter $filter --format '{{.Names}}'
if ($LASTEXITCODE -ne 0) { [Console]::Error.WriteLine('teardown: FAIL (cannot list containers)'); exit 1 }
foreach ($name in @($containers)) { if ($name) { $left += "container $name" } }
$networks = docker network ls --filter $filter --format '{{.Name}}'
if ($LASTEXITCODE -ne 0) { [Console]::Error.WriteLine('teardown: FAIL (cannot list networks)'); exit 1 }
foreach ($name in @($networks)) { if ($name) { $left += "network $name" } }
if ($Volumes) {
    $vols = docker volume ls --filter $filter --format '{{.Name}}'
    if ($LASTEXITCODE -ne 0) { [Console]::Error.WriteLine('teardown: FAIL (cannot list volumes)'); exit 1 }
    foreach ($name in @($vols)) { if ($name) { $left += "volume $name" } }
}
if ($left.Count -gt 0) {
    [Console]::Error.WriteLine("teardown: FAIL (project $project still has resources after down; remove them by hand):")
    foreach ($item in $left) { [Console]::Error.WriteLine("  $item") }
    exit 1
}
exit 0
