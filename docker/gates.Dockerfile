# One-shot gate runner: `scripts/verify.sh` re-runs itself in this image so
# local, agent and CI verification are the same command in the same box.
FROM ghcr.io/astral-sh/uv:0.11.21@sha256:ff07b86af50d4d9391d9daf4ff89ce427bc544f9aae87057e69a1cc0aa369946 AS uv

FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update \
 && apt-get install -y --no-install-recommends git jq ca-certificates curl \
      shellcheck=0.9.0-1 libicu72 libssl3 zlib1g \
 && rm -rf /var/lib/apt/lists/* \
 && git config --system --add safe.directory /work \
 && git config --system core.autocrlf true

# Lint tools (scripts/lint.sh, architecture §2.2): PowerShell from the vendor
# tarball, verified against the sha256 in the release's hashes.sha256 asset,
# and PSScriptAnalyzer at a pinned version from the PowerShell Gallery (the
# gallery publishes no checksum, so the version pin is the control).
ARG POWERSHELL_VERSION=7.4.21
ARG POWERSHELL_SHA256_X64=3fc5e1567c450bd7bd5ae69ebb0a9a4a4e0418bbc36b0232cf6dd547f0bfc0eb
ARG POWERSHELL_SHA256_ARM64=d0c216cec4c6c866fc15a105f039740228b53206f8576d2ed0bcd656a35ed6f6
ARG PSSCRIPTANALYZER_VERSION=1.25.0
RUN set -eu; \
    case "$(dpkg --print-architecture)" in \
      amd64) arch=x64; sha="$POWERSHELL_SHA256_X64" ;; \
      arm64) arch=arm64; sha="$POWERSHELL_SHA256_ARM64" ;; \
      *) echo "unsupported architecture" >&2; exit 1 ;; \
    esac; \
    tarball="powershell-${POWERSHELL_VERSION}-linux-${arch}.tar.gz"; \
    curl -fsSL -o "/tmp/$tarball" \
      "https://github.com/PowerShell/PowerShell/releases/download/v${POWERSHELL_VERSION}/$tarball"; \
    echo "$sha  /tmp/$tarball" | sha256sum -c -; \
    mkdir -p /opt/microsoft/powershell; \
    tar -xzf "/tmp/$tarball" -C /opt/microsoft/powershell; \
    chmod +x /opt/microsoft/powershell/pwsh; \
    ln -s /opt/microsoft/powershell/pwsh /usr/local/bin/pwsh; \
    rm "/tmp/$tarball"; \
    pwsh -NoProfile -NonInteractive -Command " \
      \$ErrorActionPreference = 'Stop'; \
      Set-PSRepository PSGallery -InstallationPolicy Trusted; \
      Install-Module PSScriptAnalyzer -RequiredVersion ${PSSCRIPTANALYZER_VERSION} -Scope AllUsers -Force"

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    KE_IN_GATES=1 \
    POWERSHELL_TELEMETRY_OPTOUT=1 \
    POWERSHELL_UPDATECHECK=Off \
    HARNESS_TRACING=off

WORKDIR /work
# Dependencies and the editable project are installed at build time; the
# repo is bind-mounted over /work at run time, so gates run offline.
COPY pyproject.toml uv.lock ./
COPY harness_telemetry ./harness_telemetry
COPY engine ./engine
COPY config ./config
RUN uv sync --locked
# Gates have no network. After the build-time sync, never let uv reach PyPI
# (a stale build cache otherwise sends `uv run` to the index and it fails).
ENV UV_OFFLINE=1
