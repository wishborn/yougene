# YouGene agent orientation

Work inside this repository. Backend: `backend/yougene` (Python 3.11+, FastAPI,
DuckDB); tests: `backend/tests`; frontend: `frontend` (React 19, strict TS,
Vite, Tailwind v4, Fancy); privacy guard: `scripts/check_no_private_data.py`.

Privacy is rule zero: never read or use personal genetic data or external
reference-data directories. All tests and screenshots use invented synthetic
data. Keep runtime data and screenshots outside the repository. Never log or
return genotype content in errors. No telemetry, CDN assets or external fonts.
Bind servers to loopback; keep the Host and Origin guard in `security.py`.
Accuracy comes first: report "unknown" rather than guess, and never imply a
finding the data can't support.

Windows setup: `python -m venv .venv`, then
`.venv\Scripts\python -m pip install -e './backend[dev]'` and
`npm --prefix frontend install`. Run `python scripts/dev.py` for both servers.
In Genie, use ONE `manageSite` at `https://yougene.gen`, repo `yougene`, command
`python scripts/dev.py`; no separate processes. API on loopback
`YOUGENE_API_PORT` (default 8765); Vite on Genie's `PORT` (default 5180).

Checks from root: `.venv\Scripts\python -m pytest backend/tests`,
`.venv\Scripts\ruff check backend scripts`,
`.venv\Scripts\ruff format --check backend scripts`,
`python scripts/check_no_private_data.py`,
`npm --prefix frontend run typecheck`, `npm --prefix frontend run build`.
Browser smoke: run the launcher with a throwaway `YOUGENE_DATA_DIR` and spare
ports (see README), then `YOUGENE_SMOKE_URL=... npm --prefix frontend run smoke`.
Never point the smoke test at the real site's data.

Imports: `importers/` (format detection + DuckDB load into the normalised
`calls` table), `analysis/qc.py`, `store.py` (registry + per-sample DBs),
`jobs.py` (one background worker), `api.py`. GRCh37 facts in `genome.py`.

Routing is pending `fancy-inertia-server` (being built by the Fancy team). The
current screen is a temporary workspace. Memoize chart options and grid data,
pass every fancy-grid state slice explicitly, and follow installed Fancy types.
