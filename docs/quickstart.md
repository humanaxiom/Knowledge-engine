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

## Readiness

http://localhost:47100/readyz returns 200 when postgres, neo4j and valkey are
ready and 503 otherwise. Each check carries `ok` and a `reason` (null, or one
of `refused`, `timeout`, `unreachable`, `auth_failed`, `egress_denied`,
`not_configured`, `error:<ExceptionClass>`). The model host is listed as
`model_host`, is not required, and shows `not_configured` until
`KE_MODEL_UPSTREAM` is set.

## Model host

Set `KE_MODEL_UPSTREAM` (`host:port`) in `.env` and add its host to
`KE_EGRESS_ALLOWLIST`. The gateway refuses to start with an upstream that is not
on the allowlist. This deployment:

```
KE_MODEL_UPSTREAM=aria-gb10-2:11434
KE_EGRESS_ALLOWLIST=aria-gb10-2
```

`scripts/verify.sh full` runs the model-calling checks only when both are set
(the caller's environment wins over `.env`) and the host is reachable; it skips
them with a named reason otherwise.

## Teardown leftovers

`scripts/teardown.sh` (`teardown.ps1`) reports any container, network or (with
`--volumes`) volume of its own project that survives `down`, exits non-zero and
prints what to remove by hand, for example
`docker compose -p <project> down --volumes`. It never removes anything itself.
