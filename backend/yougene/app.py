"""Application factory. Routing and sample handling are pending."""

from fastapi import FastAPI

from yougene import __version__
from yougene.security import LoopbackHostMiddleware


def create_app() -> FastAPI:
    app = FastAPI(title="YouGene", version=__version__, docs_url=None, redoc_url=None)
    app.add_middleware(LoopbackHostMiddleware)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app
