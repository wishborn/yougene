"""Application factory: JSON API under /api, Inertia pages everywhere else."""

from fastapi import FastAPI

from yougene import __version__, pages
from yougene.api import router
from yougene.api_findings import router as findings_router
from yougene.api_genome import router as genome_router
from yougene.security import LoopbackHostMiddleware


def create_app() -> FastAPI:
    app = FastAPI(title="YouGene", version=__version__, docs_url=None, redoc_url=None)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(router)
    app.include_router(findings_router)
    app.include_router(genome_router)
    pages.install(app)
    # Added last so it runs first: the Host/Origin guard wraps everything.
    app.add_middleware(LoopbackHostMiddleware)
    return app
