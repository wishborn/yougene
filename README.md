# YouGene

Explore your own DNA locally. Load a raw genotype file (23andMe first) and browse it by chromosome, gene, trait, health annotation, and drug response.

- Backend: Python (FastAPI)
- Frontend: React 19 + Tailwind v4 + the Fancy UI kit
- Reference data: ClinVar and the GWAS Catalog, downloaded locally

Status: P0 scaffold. The temporary kit smoke page uses invented calls; importing
samples, annotation and application routing are pending.

## Development (Windows PowerShell)

Python 3.11+ and Node 22.12+ are required. From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e './backend[dev]'
npm --prefix frontend install
.venv\Scripts\yougene version
python scripts/dev.py
```

The dev launcher starts both servers, prefixes their logs and stops both if
either exits or it receives Ctrl-C/SIGTERM. It uses the repo's venv and local
Vite installation; it works on Windows and POSIX. For separate debugging, run
these commands in two terminals:

```powershell
.venv\Scripts\yougene serve --port 8765
npm --prefix frontend run dev
```

Open http://127.0.0.1:5180 for direct local development. Vite proxies `/api`
to 127.0.0.1:8765 with `changeOrigin` so FastAPI sees a loopback Host. Both
servers bind to loopback. `yougene serve` alone defaults to port 8000;
`--port` is configurable. Update the Vite proxy if changing the API port.

## Genie Site

This workspace runs one site at **https://yougene.gen**, with command
`python scripts/dev.py`, repo `yougene`, port 5180 and explicit genName
`yougene.gen`. There are no separate Genie background processes. Create it with
`manageSite`, then use its returned site ID for `status`, `logs` and `restart`.
Open the address in Genie's Browser.

Genie allocates the actual upstream port for command sites and exports `PORT`.
The launcher uses that value for Vite, falling back to 5180 for direct runs;
the API stays on 8765. `status` reports the current `localOrigin`. Vite allows
only the additional `yougene.gen` hostname. FastAPI defaults to loopback hosts;
`YOUGENE_ALLOWED_HOSTS=yougene.gen` adds that literal hostname for future direct
page serving, without changing the bind address or allowing wildcards.

On macOS/Linux, use `.venv/bin/python` and `.venv/bin/yougene` in place of
the Windows paths above. Storage defaults to `platformdirs.user_data_dir("yougene")`.
Set `YOUGENE_DATA_DIR` to an external directory to override it; the backend
rejects locations inside a source checkout. P0 does not create sample databases.

## Checks

```powershell
.venv\Scripts\python -m pytest backend/tests
.venv\Scripts\ruff check backend scripts
.venv\Scripts\ruff format --check backend scripts
python scripts/check_no_private_data.py
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

CI runs backend checks on Python 3.11 and 3.14, frontend checks using `npm ci`,
and the private-data guard. Browser verification (with both dev servers running):

```powershell
npm --prefix frontend exec -- playwright install chromium
cd frontend
npm run smoke
```

The browser check defaults to http://127.0.0.1:5180 for direct local runs.
For the Genie Site, set `YOUGENE_SMOKE_URL` to its current `localOrigin` from
`manageSite status`; the printed result records which origin was checked.
The `.gen` address uses Genie's own routing and Browser, so verify it with
`manageSite status` (`ready:true`) and `manageSite open` separately.
`npm run smoke -- --offline` mocks health for an
explicitly labelled UI-only check, not live integration verification.

The browser check covers light, dark and system themes, chart rendering,
grid sorting, the health proxy and absence of external resource requests.
Screenshots go to the OS temp directory, outside the repository.

## Layout and synthetic fixtures

- `backend/yougene/`: FastAPI factory, CLI, storage config and synthetic generator.
- `backend/tests/`: tests and two 5,000-row synthetic fixtures with JSON manifests.
- `frontend/`: React 19, Vite, strict TypeScript, Tailwind v4 and Fancy UI.
- `scripts/`: tracked-file privacy guard.

Generate larger fixtures into an external temporary directory:

```powershell
.venv\Scripts\python -m yougene.testing.synth --sex male --seed 1 --rows 25000 -o "$env:TEMP\yougene-synthetic.txt"
```

Only the five public anchor SNP coordinates are real reference mappings; their
genotypes and every other call are invented. Fixtures use the 23andMe v5 tabular
export structure, plus-strand calls and GRCh37 coordinates. They do not reproduce
a person's data or a vendor's full probe panel. Adjacent JSON files identify all
planted edge cases. Routing is pending `fancy-inertia-server`; P0 has no Inertia
packages or adapter.

## Privacy

Everything runs on your machine. **This repository must never contain anyone's real genome data.** Raw files, downloaded reference databases, and local databases are git-ignored, and CI (`scripts/check_no_private_data.py`) fails if genotype-looking data is tracked. Tests use small synthetic fixtures only.

The guard permits genotype-looking fixtures only beneath
`backend/tests/fixtures/synthetic/` with the exact first-line synthetic marker.
Analysis, annotation and importer packages are AST-checked for network imports.
There is no telemetry, external font or CDN asset. The smoke page requests only
the local health endpoint. Session tokens, consent and full application security
belong to later phases before sample handling is enabled.

YouGene is not a medical device. Consumer DNA arrays are not clinical grade; nothing here is a diagnosis.
