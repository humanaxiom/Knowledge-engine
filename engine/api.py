"""The api service (architecture §2.4): `/healthz` (PS-2.4) and `/readyz` (PS-2.5)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request, Response

from engine.config import Settings
from engine.readiness import check_all
from harness_telemetry import chain_span

# No interactive docs or schema routes: the surface is exactly what is listed.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness from process state only: no I/O, no dependency, untraced."""
    return {"status": "ok"}


def get_settings(request: Request) -> Settings:
    """The Settings `startup()` returned, kept on the app by `main()`."""
    settings: Settings = request.app.state.settings
    return settings


@app.get("/readyz")
def readyz(response: Response, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    """Readiness: postgres, neo4j and valkey decide the status; the model
    host is reported but never required (PS-Q6). Public until auth-audit."""
    with chain_span("api.readyz") as span:
        result = check_all(settings)
        span.set_attribute("ke.readyz.ready", result["ready"])
    if not result["ready"]:
        response.status_code = 503
    return result


def main() -> None:
    import uvicorn

    from engine.startup import startup

    settings = startup()
    app.state.settings = settings
    # All interfaces inside the container; only the gateway publishes (§2.4).
    uvicorn.run(app, host="0.0.0.0", port=settings.api.listen_port, access_log=False)


if __name__ == "__main__":  # pragma: no cover
    main()
