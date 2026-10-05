# YouGene

Explore your own DNA locally. Load a raw genotype file (23andMe first) and browse it by chromosome, gene, trait, health annotation, and drug response.

- Backend: Python (FastAPI, DuckDB)
- Frontend: React 19 + Tailwind v4 + the Fancy UI kit
- Reference data: ClinVar and the GWAS Catalog, downloaded locally (coming next)

Status: P1. You can import 23andMe raw data files (several people per install), see a quality summary and inferred sex chromosomes, and browse every call in a server-paged grid. Annotation (ClinVar, GWAS, pharmacogenomics) and proper page routing come next. The current screen is a temporary development workspace.

## Development (Windows PowerShell)

Python 3.11+ and Node 22.12+ are required. From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e './backend[dev]'
npm --prefix frontend install
python scripts/dev.py
```

The dev launcher starts both servers, prefixes their logs and stops both if either exits or it receives Ctrl-C/SIGTERM. It works on Windows and POSIX. For separate debugging, run these in two terminals:

```powershell
.venv\Scripts\yougene serve            # API on 127.0.0.1:8765
npm --prefix frontend run dev          # Vite on 127.0.0.1:5180
```

Ports: Vite uses `PORT` (Genie injects it) or 5180; the API uses `YOUGENE_API_PORT` or 8765, and Vite's `/api` proxy follows the same variable. Both bind to loopback only.

Data lives in `platformdirs.user_data_dir("yougene")`. Set `YOUGENE_DATA_DIR` to use another folder; the backend refuses locations inside a source checkout. Layout: `registry.duckdb` (samples), `samples/<id>.duckdb` (one per sample), `tmp/` (uploads in flight, emptied after each import).

On macOS/Linux, use `.venv/bin/python` and `.venv/bin/yougene`.

## Genie Site

This workspace runs one site at **https://yougene.gen** with command `python scripts/dev.py` in repo `yougene`; there are no separate Genie processes. Use `manageSite status`, `logs` and `restart` with the site ID. Genie assigns the upstream port through `PORT`; the API stays on 8765. The launcher adds `yougene.gen` to `YOUGENE_ALLOWED_HOSTS` so the API accepts that browser origin.

## Importing

- Raw data from 23andMe, AncestryDNA, MyHeritage, FamilyTreeDNA (Family Finder) and Living DNA: the `.txt`/`.csv` file, the `.zip` download, or FamilyTreeDNA's `.csv.gz`. VCF/gVCF from sequencing services (`.vcf` or `.vcf.gz`, first sample used) is supported too: single-base genotypes become letters, calls failing the file's FILTER and symbolic alleles become no-calls, indels are counted but not yet interpreted, gVCF reference blocks are kept as "tested, reference" (a position missing from a VCF is never assumed to be reference), and GRCh38 files are converted to GRCh37 with the UCSC hg38ToHg19 chain (downloaded automatically, about 1 MB; unconvertible positions are dropped and counted). Uploads up to 2 GB, refused if disk space is short. Vendor chromosome codes (AncestryDNA 23-26) are mapped, and single-copy calls written as two letters (AncestryDNA on X/Y/MT) are reduced to one letter once sex is inferred.
- Every probe is kept: no-calls, 23andMe internal `i` ids, insertion/deletion probes (`D`/`I`, shown but never interpreted) and positions measured by more than one probe (grouped, with disagreements flagged).
- The genome build must be confirmed as GRCh37 by the header and/or five well-known reference SNPs; other builds are refused for now.
- Sex chromosomes are inferred from X heterozygosity outside the pseudo-autosomal regions and the Y call rate; conflicting signals are reported as unknown.
- The original filename is never stored (23andMe names downloads after the account holder). Re-importing the same file offers to replace the existing copy.
- Import speed: about 5 seconds for 1.4 million rows on a desktop machine (`pytest --perf`).

API (all under `/api`): `POST /samples` (raw body, `application/octet-stream`, 200 MB cap), `GET /jobs/{id}`, `GET /samples`, `GET|PATCH|DELETE /samples/{id}`, `GET /samples/{id}/calls` (paging, sort, filters), `DELETE /data` (body `{"confirm": "DELETE ALL"}`).

## Reference data

Public databases are downloaded once, on request, and built into `reference/reference.duckdb` in the data folder (about 390 MB built):

| Source | Use | License |
|---|---|---|
| ClinVar, GRCh37 VCF (NCBI) | Clinical significance, review stars, conditions, genes | Public domain |
| GWAS Catalog associations (EMBL-EBI) | Trait associations, risk alleles, effect sizes | Mostly CC0; some studies other EMBL-EBI terms |
| UCSC hg19 cytoBand | Chromosome band layout | UCSC, free for use |

Install from the workspace ("Download reference data") or the CLI:

```powershell
.venv\Scripts\yougene refdata install                 # download and build all
.venv\Scripts\yougene refdata install --file clinvar=C:\path\clinvar.vcf.gz   # reuse a download
.venv\Scripts\yougene refdata status
```

Each build records the source URL, release date, size and SHA-256. A failed update leaves the previous database untouched. ClinVar records keep every ALT of multi-allelic sites, and a `site_alleles` table lists all known alleles per single-base site, which allele matching needs. GWAS coordinates are GRCh38, so only rsids are used to join them.

## Annotation

After reference data is installed, every sample is matched against it automatically (on import, and again whenever reference data is updated). Results go to `samples/<id>.annot.duckdb`.

- **ClinVar:** matched by GRCh37 position (so 23andMe internal ids and renamed rsids count) and only reported as carried when your called letters are among the site's known alleles and include the variant allele. Each finding has review stars, an evidence tier (established, moderate, limited, research only), zygosity, and a rare-variant warning when population frequency is below 0.1% or unknown. Insertion/deletion probes are never matched.
- **GWAS Catalog:** matched by rsid. Risk-allele strand is checked against your alleles and ClinVar's: `confirmed`, `flipped` (reported on the other strand), `assumed` (only one allele known), or `ambiguous` (A/T or C/G site where you're homozygous; not counted).
- **Health results are opt-in**, and APOE, hereditary cancer genes, Parkinson's genes and HTT each sit behind their own extra consent step. Consent is stored by the local server for the whole install (`GET/PUT /api/consent`), enforced by the API as well as the UI, can be withdrawn at any time (withdrawing health withdraws every topic and drops cached results), and is cleared by "delete all data".
- Speed: about 10 seconds for a million calls against the full ClinVar and GWAS Catalog.

For the browser smoke test, invented reference files lined up with the synthetic fixtures can be generated and installed into the throwaway data folder:

```powershell
.venv\Scripts\python -m yougene.testing.synth_reference --sample backend\tests\fixtures\synthetic\male.txt -o $env:TEMP\yg-ref
.venv\Scripts\yougene refdata install --file clinvar=$env:TEMP\yg-ref\clinvar.vcf.gz --file gwas=$env:TEMP\yg-ref\gwas.zip --file cytoband=$env:TEMP\yg-ref\cytoBand.txt.gz
```

## Medicines (pharmacogenomics)

Curated, array-callable CPIC rules for CYP2C19, CYP2C9, VKORC1, SLCO1B1, DPYD, TPMT, NUDT15 and CYP3A5 (`analysis/pgx.py`). Each defining allele is checked against its ClinVar record's plus-strand alleles; a gene gets a phenotype only when every defining position was read. Results are partial (arrays can't phase or see copy number; CYP2D6 isn't reported) and are never dosing advice.

## Variant detail

Clicking a probe in the calls grid opens everything known about that position: the call(s), ClinVar records with how many copies you carry (after opt-in; sensitive topics need their own), trait associations, and any curated trait or medicine rule that uses it (`GET /api/samples/{id}/variant?chrom=&pos=`).

## Checks

```powershell
.venv\Scripts\python -m pytest backend/tests
.venv\Scripts\python -m pytest backend/tests --perf -k performance -s   # optional
.venv\Scripts\ruff check backend scripts
.venv\Scripts\ruff format --check backend scripts
python scripts/check_no_private_data.py
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

CI runs the backend on Python 3.11 and 3.14, the frontend build, and the private-data guard.

Browser smoke test (imports the synthetic fixtures, checks QC, sorting, filters, paging, rename, delete, themes and mobile layout). Always run it against a throwaway data folder and spare ports, never the site you use for real data:

```powershell
npm --prefix frontend exec -- playwright install chromium
$env:YOUGENE_DATA_DIR = (New-Item -ItemType Directory "$env:TEMP\yougene-smoke-data").FullName
$env:YOUGENE_API_PORT = "8799"; $env:PORT = "5190"
python scripts/dev.py            # in one terminal
$env:YOUGENE_SMOKE_URL = "http://127.0.0.1:5190"; npm --prefix frontend run smoke
```

Screenshots go to the OS temp folder, outside the repository.

## Layout and synthetic fixtures

- `backend/yougene/`: app factory, API, importers, QC, storage, jobs, CLI, synthetic generator.
- `backend/tests/`: tests and two 5,000-row synthetic fixtures with JSON manifests.
- `frontend/`: React 19, Vite, strict TypeScript, Tailwind v4 and Fancy UI.
- `scripts/`: dev launcher and tracked-file privacy guard.

Generate larger fixtures outside the repository:

```powershell
.venv\Scripts\python -m yougene.testing.synth --sex male --seed 1 --rows 25000 -o "$env:TEMP\yougene-synthetic.txt"
```

Only the five public anchor SNP coordinates are real reference mappings; their genotypes and every other call are invented. Adjacent JSON files list all planted edge cases.

## Privacy and security

Everything runs on your machine. **This repository must never contain anyone's real genome data.** Raw files, downloaded reference databases and local databases are git-ignored, and CI (`scripts/check_no_private_data.py`) fails if genotype-looking data in 23andMe, AncestryDNA, MyHeritage/FTDNA or VCF form is tracked. Genotype-looking fixtures are allowed only under `backend/tests/fixtures/synthetic/` with the exact synthetic marker as their first line.

- Servers bind to loopback. Every request must name an allowed Host (DNS-rebinding guard).
- Requests that change data are refused when they carry an Origin from another site, and uploads must be `application/octet-stream`, so a web page open in your browser can't import or delete anything.
- Importers, analysis and annotation code can't import network libraries (AST-checked in CI), and DuckDB's extension auto-install is switched off.
- Error messages and logs carry counts only, never genotypes.
- No telemetry, external fonts or CDN assets.

YouGene is not a medical device. Consumer DNA arrays are not clinical grade; nothing here is a diagnosis.

## License

MIT
