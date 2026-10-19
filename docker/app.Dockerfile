# ke-app: the api (and later the worker) image. Build context is the
# repository root. .env.example is never copied (.dockerignore excludes .env*).
FROM ghcr.io/astral-sh/uv:0.11.21@sha256:ff07b86af50d4d9391d9daf4ff89ce427bc544f9aae87057e69a1cc0aa369946 AS uv

FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
COPY --from=uv /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY harness_telemetry ./harness_telemetry
COPY engine ./engine
COPY config ./config
RUN uv sync --locked --no-dev --no-editable \
 && useradd --no-create-home --uid 10001 ke

USER ke
CMD ["python", "-m", "engine.api"]
