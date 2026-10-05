"""Page routes, served with the Inertia protocol by fancy-inertia-server.

Each route renders a React page component (frontend/src/pages/<Name>.tsx)
with its props. Data-heavy views (calls grid, traits, findings) still load
from the JSON API with TanStack Query; pages get only what they need to
render straight away.

Assets: in development the Vite dev server fronts the site and proxies page
requests here, so the root template loads scripts from the same origin
(including the React-refresh preamble @vitejs/plugin-react needs). In
production FastAPI serves the built files under /build from the manifest.
"""

import os
from pathlib import Path

from fancy_inertia_server import InertiaConfig, InertiaMiddleware, inertia
from fancy_inertia_server.vite import asset_tags, manifest_version, root_template
from fastapi import APIRouter, FastAPI, HTTPException, Request

from yougene import store

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
DIST = FRONTEND / "dist"
MANIFEST = DIST / ".vite" / "manifest.json"
ENTRY = "src/main.tsx"

DEV_TAGS = (
    '<script type="module">'
    'import RefreshRuntime from "/@react-refresh";'
    "RefreshRuntime.injectIntoGlobalHook(window);"
    "window.$RefreshReg$ = () => {};"
    "window.$RefreshSig$ = () => (type) => type;"
    "window.__vite_plugin_react_preamble_installed__ = true;"
    "</script>"
    '<script type="module" src="/@vite/client"></script>'
    f'<script type="module" src="/{ENTRY}"></script>'
)

router = APIRouter(include_in_schema=False)


def dev_mode() -> bool:
    return os.environ.get("YOUGENE_DEV") == "1"


def install(app: FastAPI) -> None:
    if dev_mode():
        assets = lambda: DEV_TAGS  # noqa: E731
        version = "dev"
    else:
        built = asset_tags(entry=ENTRY, manifest_path=MANIFEST, base="/build/")

        def assets() -> str:
            if not MANIFEST.exists():
                # A readable message beats a blank page.
                return (
                    "<noscript></noscript><script>document.addEventListener("
                    "'DOMContentLoaded',()=>{document.body.insertAdjacentHTML('afterbegin',"
                    '\'<p style="font:16px system-ui;margin:2rem">The YouGene frontend '
                    "isn't built. Run <code>npm --prefix frontend run build</code>, or "
                    "start development with <code>python scripts/dev.py</code>.</p>')})"
                    "</script>"
                )
            return built()

        version = manifest_version(MANIFEST)
        if DIST.exists():
            from starlette.staticfiles import StaticFiles

            app.mount("/build", StaticFiles(directory=DIST), name="build")
    app.add_middleware(
        InertiaMiddleware,
        config=InertiaConfig(
            version=version,
            root_template=root_template(
                assets=assets,
                title="YouGene",
                head='<meta name="color-scheme" content="light dark">',
            ),
            share=lambda scope: {"samples": _sample_summaries()},
        ),
    )
    app.include_router(router)


def _sample_summaries() -> list[dict]:
    return [
        {
            "id": s["id"],
            "display_name": s["display_name"],
            "relationship": s["relationship"],
        }
        for s in store.list_samples()
    ]


def _sample(sample_id: str) -> dict:
    try:
        record = store.get_sample(sample_id)
    except KeyError:
        record = None
    if record is None:
        raise HTTPException(404, "No such sample.")
    return record


@router.get("/")
async def home(request: Request):
    return inertia(request).render("Home")


@router.get("/settings")
async def settings(request: Request):
    return inertia(request).render("Settings")


SAMPLE_VIEWS = {
    "": "Sample/Overview",
    "calls": "Sample/Calls",
    "chromosomes": "Sample/Chromosomes",
    "traits": "Sample/Traits",
    "medicines": "Sample/Medicines",
    "health": "Sample/Health",
}


@router.get("/samples/{sample_id}")
async def sample_overview(request: Request, sample_id: str):
    return inertia(request).render(SAMPLE_VIEWS[""], {"sample": _sample(sample_id)})


@router.get("/samples/{sample_id}/{view}")
async def sample_view(request: Request, sample_id: str, view: str):
    if view not in SAMPLE_VIEWS or not view:
        raise HTTPException(404, "No such page.")
    return inertia(request).render(SAMPLE_VIEWS[view], {"sample": _sample(sample_id)})
