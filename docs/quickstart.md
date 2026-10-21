# Quickstart

Bring the Knowledge Engine stack up on a fresh machine.

## Prerequisites

- Git
- Docker Engine 28 or later with Compose 2.24 or later (`docker version`, `docker compose version`). The launch scripts refuse older engines: the backend network needs `gateway_mode_ipv4: isolated`, which Docker 28 introduced, so containers cannot reach host services through the bridge.

Supported hosts for the code-first install below are Windows (PowerShell) and Linux (bash). macOS is not supported there; on a Mac use the offline install (arm64 bundle, `install.sh`) described further down.

## Code-first install (primary)

Clone the repository, build, launch. This builds the images natively on the
machine it runs on, x86 or ARM, and needs internet access at build time. Use it
whenever the target machine can reach the network.

### Linux (bash)

```bash
git clone <repository-url> knowledge-engine
cd knowledge-engine
scripts/build.sh      # builds the images and pulls the pinned ones (needs the network)
scripts/launch.sh     # creates .env from .env.example if missing, then starts the stack
scripts/teardown.sh   # stops it; add --volumes to delete the named volumes too
```

### Windows (PowerShell)

```powershell
git clone <repository-url> knowledge-engine
cd knowledge-engine
scripts\build.ps1
scripts\launch.ps1
scripts\teardown.ps1  # add -Volumes to delete the named volumes too
```

### Linux checkout permissions (umask)

`scripts/verify.sh` runs its gates as uid 10001, so the checkout must be
readable by that user. A Linux checkout made under `umask 077` fails loudly;
clone under `umask 022`, or run `chmod -R go+rX` on the checkout.

## Offline bundle (air-gapped machines)

For a machine with no internet access, build and bundle on a connected machine,
carry the bundle across, and install it there. A bundle holds one architecture:
linux/amd64 or linux/arm64. `scripts/bundle.sh` is a bash script and needs a
Linux build host; it only saves images that `scripts/build.sh` already built,
and it bundles for the Docker daemon it talks to.

The build host also needs `jq`; `bundle.sh` refuses to start without it. If
`jq --version` fails, install it: `sudo apt-get install -y jq` (Debian,
Ubuntu) or `sudo dnf install -y jq` (Fedora, RHEL). The target machine does
not need it. `bundle.sh` also needs at least 7 GiB free on the disk that holds
the output directory and refuses otherwise.

On a Windows machine the Linux build host can be WSL, but only with Docker
Desktop's WSL integration turned on for that distro (Docker Desktop, Settings,
Resources, WSL integration). Without it, `docker` inside WSL is a stub that
refuses every command.

### 1. Build and bundle, one per architecture

amd64, against the local daemon on a Linux build host:

```bash
bash scripts/build.sh
bash scripts/bundle.sh --out dist/bundle-amd64
```

arm64 (for example a GB10 or an Apple-silicon Mac), against an arm64 host
reached through a Docker context. Build and bundle with the same context:

```bash
export DOCKER_CONTEXT=<arm host context>   # e.g. docker context create <name> --docker host=ssh://<alias>
bash scripts/build.sh
bash scripts/bundle.sh --out dist/bundle-arm64
```

The `--out` name must end in `-<arch>` (`-amd64` or `-arm64`). `--arch` is only
an assertion that the daemon has that architecture; it never selects one.
`bundle.sh` prints the SHA-256 of the bundle's `MANIFEST.sha256` and writes it
to `dist/bundle-<arch>.manifest.sha256`, beside the bundle and not inside it.

### 2. Carry it across

Carry the `dist/bundle-<arch>` directory and `dist/bundle-<arch>.manifest.sha256`
to the target machine. Send the `.manifest.sha256` file (or just its hash) by a
different channel than the bundle, so tampering with one does not also change the
other.

On the target, first copy the bundle off the shared or removable media (USB
drive, network share, synced folder) into a private directory that only you can
write to, and verify and install from that copy. Anyone who can write to the
media can change the files between your check and your use.

### 3. Verify before running anything from the bundle

The installers ship inside the bundle they check, so a tampered installer could
skip its own check. Use your own tools, in this order, before running them, from
inside the private copy:

1. Compare the hash of the bundle's `MANIFEST.sha256` with the value in
   `<out>.manifest.sha256` that arrived out of band.
   - Linux: `sha256sum MANIFEST.sha256`
   - Mac: `shasum -a 256 MANIFEST.sha256`
   - Windows: `Get-FileHash MANIFEST.sha256 -Algorithm SHA256`. Get-FileHash
     prints uppercase hex; compare it case-insensitively with the expected value.
2. Check every file against the manifest.
   - Linux: `sha256sum -c --strict MANIFEST.sha256`
   - Mac: `shasum -a 256 -c MANIFEST.sha256`
   - Windows: `Get-FileHash install.ps1 -Algorithm SHA256` and compare it with
     the `install.ps1` line in `MANIFEST.sha256` (repeat for any file you will run).

To check item 1 in one command, let your tool compare the out-of-band record
itself. The record names `bundle-<arch>/MANIFEST.sha256`, so run the command
from the directory that holds the bundle (its parent, where the record file sits
beside `bundle-<arch>`), not from inside the bundle:

- Linux: `sha256sum -c bundle-<arch>.manifest.sha256`
- Mac: `shasum -a 256 -c bundle-<arch>.manifest.sha256`

It prints `OK` for the manifest when the hashes match. Item 2 still has to be
run from inside the bundle.

### 4. Install

Run the installer from the bundle root with the hash from step 1 (64 hex
characters), and with a clean, absolute `PATH` (only absolute directories you
trust). install.sh refuses an empty or relative `PATH` entry; install.ps1
refuses a relative entry and, on Windows, drops empty entries. The target
directory must not exist or must be empty.

install.ps1 is for Windows; use install.sh on Linux and macOS.

The installer refuses a target parent directory that anyone other than you can
write to or own. The parent must be owned by you (root, or on Windows SYSTEM and
Administrators, are also accepted) and writable by no one else. A parent that
others can write is refused even when it is sticky, such as `/tmp` (mode 1777),
and so is `C:\`; a parent it cannot check is refused too. Do not put the target
directly under `C:\` or `/opt`. Pick a directory under your home directory, or
an operator-owned directory you created yourself.

Keep the directories above the parent not writable by others either: someone who
can write an ancestor directory can swap the parent out from under the check.
Do not install the target into a synced or shared folder (OneDrive, Dropbox, a
network share or drive): the check cannot see who can write there.

Linux and Mac (bash; `bash` is used so the file mode does not matter):

```bash
cd bundle-<arch>
bash ./install.sh --expect-manifest <sha256> ~/knowledge-engine
```

An operator-owned directory under `/opt` also works, for example after
`sudo mkdir -p /opt/ke && sudo chown "$USER" /opt/ke && chmod 755 /opt/ke`
(a parent writable only by the operator):

```bash
bash ./install.sh --expect-manifest <sha256> /opt/ke/knowledge-engine
```

Windows (PowerShell 7.3 or later, installed separately; Windows PowerShell 5.1
cannot run the installer). ConstrainedLanguage mode and AppLocker policies that
force it are not supported:

```powershell
cd bundle-<arch>
pwsh -NoProfile -File .\install.ps1 -Target $HOME\knowledge-engine -ExpectManifest <sha256>
```

The installer refuses a bundle whose architecture differs from the local Docker
daemon's, loads the images, and prints the accepted manifest hash and the next
step.

### 5. Configure, launch and check

Create `.env` from `.env.example`, make it private, and set real secrets in it
before the first launch. Replace both `changeme-...` passwords
(`KE_STORES__POSTGRES__PASSWORD` and `KE_STORES__NEO4J__PASSWORD`) with your
own, and change the ports there if the defaults clash. If you skip this,
`launch.sh` creates `.env` for you with `KE_ENV=dev` and the placeholder
secrets, which is fine only for local development.

Choose the compose project name before you launch. Every install on a host
shares the compose project `knowledge-engine` and its volumes. Keep to one
install per host, or give each install a distinct `COMPOSE_PROJECT_NAME` (for
example `ke-site-b`), set the same way for `launch.sh`, `smoke.sh` and
`teardown.sh`. Running `bash scripts/teardown.sh --volumes` deletes the data (the
volumes) of whichever project it resolves to, so check the name first.

```bash
cd ~/knowledge-engine
cp .env.example .env
chmod 600 .env
# edit .env: set real passwords (and ports, if needed)
# name this install's compose project; use a distinct name for a second install on this host
export COMPOSE_PROJECT_NAME=ke-site-a
bash scripts/launch.sh
```

The copy holds your real secrets, and `cp` leaves it readable by every local
user unless you run `chmod 600 .env`, so run it before you put the secrets in.
On Windows use `Copy-Item .env.example .env` and keep the install under your
user profile, so that `.env` is readable only by you and administrators. To
remove other access explicitly, run this in PowerShell from the install
directory:
`icacls .env /inheritance:r /grant:r "*$([System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value):(R,W)"`.
It grants your account by SID, not by name, so a local account with the same
name as yours cannot shadow you.

This release runs in dev mode only. Keep `KE_ENV=dev` (the value
`.env.example` ships) on a trusted host with the default loopback binding
(`KE_BIND_ADDRESS=127.0.0.1`), and still set real secrets, because the stack
has no authentication yet and anyone who can reach it can use it.

Production mode is not available yet. `KE_ENV=prod` requires authentication
(`KE_AUTH__ENABLED=true`), which arrives with the auth-audit work, and the
engine refuses to start in prod until then. `.env.example` ships
`KE_AUTH__ENABLED=false`; leave it so for now.

On Windows run `scripts\launch.ps1` in the target directory.

Keep the same `COMPOSE_PROJECT_NAME` exported in any new shell before you run
`smoke.sh` or `teardown.sh`.

Then run `bash scripts/smoke.sh` to check the stack. If the project is already
running, smoke checks it and leaves it up; it skips the store-outage check, so it
does not stop your postgres. If the project is stopped, smoke launches it itself,
runs the store-outage check (it stops and restarts postgres and watches
`/readyz`), and tears the project down again without `--volumes` when it ends.

### macOS (offline install only)

An Apple-silicon Mac runs the arm64 bundle with `install.sh` (bash) against
Docker Desktop; follow steps 2 to 5 above, using `shasum -a 256 -c`.
macOS is offered for this offline install only. Notes:

- `/tmp` is a symlink on a Mac. For the offline install pick a target under your home directory, such as
  `~/knowledge-engine`.
- Finder adds `.DS_Store` and `._*` files, and OneDrive or other synced folders
  add or change files; either breaks verification. Copy the bundle to a plain
  folder under your home directory (outside OneDrive) and delete those files
  before you verify.
- The smoke test (`bash scripts/smoke.sh`) is not run on the Mac; skip it there and
  check the stack by `launch` reporting every service healthy.

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
