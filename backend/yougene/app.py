"""Application factory. Page routing is pending fancy-inertia-server."""

from fastapi import FastAPI

from yougene import __version__
from yougene.api import router
from yougene.api_findings import router as findings_router
from yougene.api_genome import router as genome_router
from yougene.security import LoopbackHostMiddleware


def create_app() -> FastAPI:
    app = FastAPI(title="YouGene", version=__version__, docs_url=None, redoc_url=None)
    app.add_middleware(LoopbackHostMiddleware)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(router)
    app.include_router(findings_router)
    app.include_router(genome_router)
    return app
