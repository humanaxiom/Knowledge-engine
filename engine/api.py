"""The api service (architecture §2.4). Only `/healthz` exists so far (PS-2.4)."""

from __future__ import annotations

from fastapi import FastAPI

# No interactive docs or schema routes: the surface is exactly what is listed.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness from process state only: no I/O, no dependency, untraced."""
    return {"status": "ok"}


def main() -> None:
    import uvicorn

    from engine.startup import startup

    settings = startup()
    # All interfaces inside the container; only the gateway publishes (§2.4).
    uvicorn.run(app, host="0.0.0.0", port=settings.api.listen_port, access_log=False)


if __name__ == "__main__":  # pragma: no cover
    main()
