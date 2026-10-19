# Quickstart

Bring the Knowledge Engine stack up on a fresh machine.

## Prerequisites

- Git
- Docker Engine 28 or later with Compose 2.24 or later (`docker version`, `docker compose version`). The launch scripts refuse older engines: the backend network needs `gateway_mode_ipv4: isolated`, which Docker 28 introduced, so containers cannot reach host services through the bridge.

Supported hosts are Windows (PowerShell) and Linux (bash). macOS is not supported.

## Linux (bash)

```bash
git clone <repository-url> knowledge-engine
cd knowledge-engine
scripts/build.sh      # builds the images and pulls the pinned ones (needs the network)
scripts/launch.sh     # creates .env from .env.example if missing, then starts the stack
scripts/teardown.sh   # stops it; add --volumes to delete the named volumes too
```

## Windows (PowerShell)

```powershell
git clone <repository-url> knowledge-engine
cd knowledge-engine
scripts\build.ps1
scripts\launch.ps1
scripts\teardown.ps1  # add -Volumes to delete the named volumes too
```

## What you get

`launch` waits until every service reports healthy, then prints the URLs. Only
the gateway publishes ports, on `KE_BIND_ADDRESS` (127.0.0.1 unless you change
it in `.env`): the API on `KE_API_PORT` and the Phoenix trace UI on
`KE_PHOENIX_PORT`.

`.env.example` ships placeholder secrets. A `KE_BIND_ADDRESS` other than
loopback is refused unless `KE_ENV=dev`, because the stack has no
authentication yet.

The API answers at http://localhost:47100/healthz and Phoenix at
http://localhost:47101 by default.

## Model host

Set `KE_MODEL_UPSTREAM` (`host:port`, for example `aria-gb10-2:PORT`) in `.env`
and add its host to `KE_EGRESS_ALLOWLIST`. The gateway refuses to start with an
upstream that is not on the allowlist.
