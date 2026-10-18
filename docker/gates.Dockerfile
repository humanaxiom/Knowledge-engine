# One-shot gate runner: `scripts/verify.sh` re-runs itself in this image so
# local, agent and CI verification are the same command in the same box.
FROM ghcr.io/astral-sh/uv:0.11.21@sha256:ff07b86af50d4d9391d9daf4ff89ce427bc544f9aae87057e69a1cc0aa369946 AS uv

FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update \
 && apt-get install -y --no-install-recommends git jq \
 && rm -rf /var/lib/apt/lists/* \
 && git config --system --add safe.directory /work \
 && git config --system core.autocrlf true

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
RUN uv sync --locked
# Gates have no network. After the build-time sync, never let uv reach PyPI
# (a stale build cache otherwise sends `uv run` to the index and it fails).
ENV UV_OFFLINE=1
