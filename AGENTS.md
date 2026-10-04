# YouGene agent orientation

Work inside this repository. Backend: `backend/yougene` (Python 3.11+, FastAPI,
DuckDB); tests: `backend/tests`; frontend: `frontend` (React 19, strict TS,
Vite, Tailwind v4, Fancy); privacy guard: `scripts/check_no_private_data.py`.

Privacy is rule zero: never read or use personal genetic data or external
reference-data directories. All tests and screenshots use invented synthetic
data. Keep runtime data and screenshots outside the repository. No telemetry,
CDN assets or external fonts. Bind servers to loopback; preserve the Host guard.
Accuracy comes first; never imply a finding the data cannot support.

Windows setup: `python -m venv .venv`, then
`.venv\Scripts\python -m pip install -e './backend[dev]'` and
`npm --prefix frontend install`. Run `python scripts/dev.py` for both servers.
In Genie, use ONE `manageSite` at `https://yougene.gen`, repo `yougene`, command
`["python", "scripts/dev.py"]`, genName `yougene.gen`; no separate processes.
Use `manageSite status/logs/restart` with the returned site ID. API is loopback
8765; Vite uses Genie's injected `PORT` or 5180 locally, with strictPort.
Proxy `/api` uses changeOrigin; Vite's allowedHosts includes `yougene.gen`.
Backend optional `YOUGENE_ALLOWED_HOSTS` adds literal hostnames only.

Checks from root: `.venv\Scripts\python -m pytest backend/tests`,
`.venv\Scripts\ruff check backend scripts`,
`.venv\Scripts\ruff format --check backend scripts`,
`python scripts/check_no_private_data.py`,
`npm --prefix frontend run typecheck`, `npm --prefix frontend run build`.
Browser check: from `frontend`, `npm run smoke` with the site running. If private
`.gen` routing is unavailable in standalone Chromium, use `YOUGENE_SMOKE_URL`
with the managed site's reported `localOrigin` and disclose that limitation.

Routing pending fancy-inertia-server. Do not implement an Inertia adapter or
install Inertia/fancy-query packages during P0. The labelled kit smoke page is
temporary. Memoize chart options and grid data; follow installed Fancy types.
