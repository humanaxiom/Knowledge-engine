# ke-app: the api (and later the worker) image. Build context is the
# repository root. .env.example is never copied (.dockerignore excludes .env*).
# The final stage ships without uv (ADR-KE-013 amendment 1, D10): uv only
# builds the venv in the builder stage.
# libpq5 is pinned (PSC-25, N0): psycopg-c is built against Debian's libpq and
# the runtime stage installs the same version. Debian updates postgresql-15, so
# the old version leaves the mirror and the build fails by name; bump it here
# and in docker/gates.Dockerfile together (never unpin).
ARG LIBPQ_VERSION=15.19-0+deb12u1

FROM ghcr.io/astral-sh/uv:0.11.21@sha256:ff07b86af50d4d9391d9daf4ff89ce427bc544f9aae87057e69a1cc0aa369946 AS uv

FROM python:3.12-slim-bookworm@sha256:6dd8b6dab6b3adc7812bab69eca5dbdc1a5cc690ad28306d234ffb4ef8ac9753 AS builder
ARG LIBPQ_VERSION
COPY --from=uv /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy

# psycopg-c compiles against libpq-dev (pg_config); none of this ships.
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc libc6-dev libpq-dev=${LIBPQ_VERSION} \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Dependencies first: a code change rebuilds only the layers below (N11).
COPY pyproject.toml uv.lock ./
# 1: the hash-locked build requirements (psycopg-c builds without isolation).
RUN uv sync --locked --no-dev --group pq-build --no-install-project
# 2: compile psycopg-c from its locked sdist against Debian's libpq.
RUN uv sync --locked --no-dev --group pq-build --group pq-c \
    --no-binary-package psycopg-c --no-install-project
COPY harness_telemetry ./harness_telemetry
COPY engine ./engine
COPY config ./config
# uv leaves an empty 0666 lock file in the venv; it must not ship (I-1).
# 3: exact sync, so pq-build (setuptools, wheel) is removed and does not ship.
RUN uv sync --locked --no-dev --group pq-c --no-binary-package psycopg-c \
    --no-editable \
    && rm -f /opt/venv/.lock

# The shipped files: the base, libpq5, and no pip (PSC-14, N10a). Its layers
# do not ship: the last stage copies its / whole.
FROM python:3.12-slim-bookworm@sha256:6dd8b6dab6b3adc7812bab69eca5dbdc1a5cc690ad28306d234ffb4ef8ac9753 AS runtime
ARG LIBPQ_VERSION
# The shared library psycopg-c loads; apt adds only its missing dependencies.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5=${LIBPQ_VERSION} \
 && rm -rf /var/lib/apt/lists/*
# pip's RECORD lists its files; both commands fail the build if pip is gone.
RUN python -m pip uninstall -y pip \
 && rm /usr/local/lib/python3.12/ensurepip/_bundled/pip-*.whl

# One layer: a delete in a layer on the base would leave pip in the saved tar.
# ENV: the base sets PATH, LANG, GPG_KEY, PYTHON_VERSION and PYTHON_SHA256. The
# last three only served the base build (nothing reads them), so they are dropped.
FROM scratch
COPY --from=runtime / /
ENV PATH=/opt/venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin \
    LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app
WORKDIR /app
RUN useradd --no-create-home --uid 10001 ke

USER ke
CMD ["python", "-m", "engine.api"]
