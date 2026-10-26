# One-shot gate runner: `scripts/verify.sh` re-runs itself in this image so
# local, agent and CI verification are the same command in the same box.
# Same libpq pin as docker/app.Dockerfile (PSC-25): the tests import the psycopg
# implementation that ships, built on Debian's libpq. Bump both together.
ARG LIBPQ_VERSION=15.19-0+deb12u1

FROM ghcr.io/astral-sh/uv:0.11.21@sha256:ff07b86af50d4d9391d9daf4ff89ce427bc544f9aae87057e69a1cc0aa369946 AS uv

FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
ARG LIBPQ_VERSION
ENV POWERSHELL_TELEMETRY_OPTOUT=1 \
    POWERSHELL_UPDATECHECK=Off
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update \
 && apt-get install -y --no-install-recommends git jq ca-certificates curl \
      shellcheck=0.9.0-1 libicu72 libssl3 zlib1g \
      gcc libc6-dev libpq-dev=${LIBPQ_VERSION} \
 && rm -rf /var/lib/apt/lists/* \
 && git config --system --add safe.directory /work \
 && git config --system core.autocrlf true

# Lint tools (scripts/lint.sh, architecture §2.2): PowerShell from the vendor
# tarball, verified against the sha256 in the release's hashes.sha256 asset,
# and PSScriptAnalyzer 1.25.0 (ARG below) from the PowerShell Gallery, checked
# against the gallery's published SHA-512 PackageHash (ruling Q48: the pin
# EQUALS the OData PackageHash, base64 converted to hex) before it is unpacked.
ARG POWERSHELL_VERSION=7.4.21
ARG POWERSHELL_SHA256_X64=3fc5e1567c450bd7bd5ae69ebb0a9a4a4e0418bbc36b0232cf6dd547f0bfc0eb
ARG POWERSHELL_SHA256_ARM64=d0c216cec4c6c866fc15a105f039740228b53206f8576d2ed0bcd656a35ed6f6
RUN set -eu; \
    case "$(dpkg --print-architecture)" in \
      amd64) arch=x64; sha="$POWERSHELL_SHA256_X64" ;; \
      arm64) arch=arm64; sha="$POWERSHELL_SHA256_ARM64" ;; \
      *) echo "unsupported architecture" >&2; exit 1 ;; \
    esac; \
    tarball="powershell-${POWERSHELL_VERSION}-linux-${arch}.tar.gz"; \
    curl --proto '=https' --tlsv1.2 -fsSL -o "/tmp/$tarball" \
      "https://github.com/PowerShell/PowerShell/releases/download/v${POWERSHELL_VERSION}/$tarball"; \
    echo "$sha  /tmp/$tarball" | sha256sum -c -; \
    mkdir -p /opt/microsoft/powershell; \
    tar -xzf "/tmp/$tarball" -C /opt/microsoft/powershell; \
    chmod +x /opt/microsoft/powershell/pwsh; \
    ln -s /opt/microsoft/powershell/pwsh /usr/local/bin/pwsh; \
    rm "/tmp/$tarball"

ARG PSSCRIPTANALYZER_VERSION=1.25.0
ARG PSSCRIPTANALYZER_SHA512=e7fb573262e604bab29914ae62921d24b97c2f88b519b41277b403ef6ce163f14b7d1b36dc73449a68e5ae5a8d9502891b10c264131fd1813adf29bf131c1663
RUN set -eu; \
    curl --proto '=https' --proto-redir '=https' --tlsv1.2 -fsSL -o /tmp/psa.nupkg \
      "https://www.powershellgallery.com/api/v2/package/PSScriptAnalyzer/${PSSCRIPTANALYZER_VERSION}"; \
    echo "$PSSCRIPTANALYZER_SHA512  /tmp/psa.nupkg" | sha512sum -c -; \
    dir="/usr/local/share/powershell/Modules/PSScriptAnalyzer/${PSSCRIPTANALYZER_VERSION}"; \
    python3 -I -m zipfile -e /tmp/psa.nupkg "/usr/local/share/powershell/Modules/PSScriptAnalyzer/${PSSCRIPTANALYZER_VERSION}"; \
    rm -rf "$dir/_rels" "$dir/package" "$dir/[Content_Types].xml" "$dir/PSScriptAnalyzer.nuspec" "$dir/.signature.p7s" /tmp/psa.nupkg; \
    pwsh -NoProfile -NonInteractive -Command "Import-Module PSScriptAnalyzer -ErrorAction Stop"

# Docker client for the offline check (PS-3.10, architecture §2.2): the static
# `docker` client binary and the compose plugin, each pinned by version and
# SHA-256 and checked before it is installed. No daemon (dockerd, containerd,
# runc, ctr) and no package repository; the gate services get no socket and no
# DOCKER_HOST. Hash provenance (ruling Q48), recorded in
# docs/handoffs/platform-offline.md:
#   - Docker CLI: download.docker.com publishes no checksum for the static
#     tarball, so these hashes are trust-on-first-use over HTTPS (computed from
#     a fresh download on 2026-10-19; security re-fetches them).
#   - compose plugin: each value EQUALS the upstream
#     docker-compose-linux-<arch>.sha256 asset of the v5.6.0 release.
# To bump: change the version and both hashes together; a mismatch fails the build.
ARG DOCKER_VERSION=29.9.1
ARG DOCKER_SHA256_X64=c158ecc55adb3afb01bbd3539ed3b997d20c26dbdc418080506cc1bf5243ff57
ARG DOCKER_SHA256_ARM64=3e93cc6d1a686456a3b18eefdde26467a837a7a2b257af22e27cba1dbc1b2018
RUN set -eu; \
    case "$(dpkg --print-architecture)" in \
      amd64) arch=x86_64; sha="$DOCKER_SHA256_X64" ;; \
      arm64) arch=aarch64; sha="$DOCKER_SHA256_ARM64" ;; \
      *) echo "unsupported architecture" >&2; exit 1 ;; \
    esac; \
    curl --proto '=https' --tlsv1.2 -fsSL -o /tmp/docker.tgz \
      "https://download.docker.com/linux/static/stable/$arch/docker-${DOCKER_VERSION}.tgz"; \
    echo "$sha  /tmp/docker.tgz" | sha256sum -c -; \
    tar -xzf /tmp/docker.tgz -C /usr/local/bin --strip-components=1 \
      --no-same-owner docker/docker; \
    rm /tmp/docker.tgz

ARG COMPOSE_VERSION=5.6.0
ARG COMPOSE_SHA256_X64=40343e21ca777173e69cff5dbafeb37c6f81f3b0d57d9e597f036e95eb63e76a
ARG COMPOSE_SHA256_ARM64=733ec76717ceb59052a9609b9dadfb523b2df8eab57a54212872d10a58078ea2
RUN set -eu; \
    case "$(dpkg --print-architecture)" in \
      amd64) arch=x86_64; sha="$COMPOSE_SHA256_X64" ;; \
      arm64) arch=aarch64; sha="$COMPOSE_SHA256_ARM64" ;; \
      *) echo "unsupported architecture" >&2; exit 1 ;; \
    esac; \
    curl --proto '=https' --tlsv1.2 -fsSL -o /tmp/docker-compose \
      "https://github.com/docker/compose/releases/download/v${COMPOSE_VERSION}/docker-compose-linux-$arch"; \
    echo "$sha  /tmp/docker-compose" | sha256sum -c -; \
    mkdir -p /usr/local/lib/docker/cli-plugins; \
    install -m 0755 /tmp/docker-compose /usr/local/lib/docker/cli-plugins/docker-compose; \
    rm /tmp/docker-compose

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    KE_IN_GATES=1 \
    HARNESS_TRACING=off

WORKDIR /work
# Dependencies and the editable project are installed at build time; the
# repo is bind-mounted over /work at run time, so gates run offline.
COPY pyproject.toml uv.lock ./
COPY harness_telemetry ./harness_telemetry
COPY engine ./engine
COPY config ./config
# The uv cache lives in the image, owned by the gate user, not in root's 0700
# home: `uv run --locked` re-installs the editable project on every run and
# needs both the cache and a writable venv (L-5; never set the no-sync env
# var, it hides lock drift).
ENV UV_CACHE_DIR=/opt/uv-cache
# Ownership is set in the same layer as the sync so the venv and cache are not
# stored twice (L-5): the gate user (10001:10001) owns both, nothing else in
# the image is writable by it.
RUN uv sync --locked --group pq-build --no-install-project \
 && uv sync --locked --group pq-build --group pq-c --no-binary-package psycopg-c --no-install-project \
 && uv sync --locked --group pq-build --group pq-c --no-binary-package psycopg-c \
 && chown -R 10001:10001 /opt/venv /opt/uv-cache
# Gates have no network. After the build-time sync, never let uv reach PyPI
# (a stale build cache otherwise sends `uv run` to the index and it fails).
ENV UV_OFFLINE=1

# Least privilege (security L-5, PS-3.5): the gate services run as 10001:10001
# on a read-only checkout; only /tmp (tmpfs) is writable.
USER 10001:10001
