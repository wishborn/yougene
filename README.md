# YouGene

Explore your own DNA locally. Load a raw genotype file (23andMe first) and browse it by chromosome, gene, trait, health annotation, and drug response.

- Backend: Python (FastAPI)
- Frontend: React 19 + Tailwind v4 + the Fancy UI kit
- Reference data: ClinVar and the GWAS Catalog, downloaded locally

Status: early planning. Nothing is built yet.

## Privacy

Everything runs on your machine. **This repository must never contain anyone's real genome data.** Raw files, downloaded reference databases, and local databases are git-ignored, and CI (`scripts/check_no_private_data.py`) fails if genotype-looking data is tracked. Tests use small synthetic fixtures only.

YouGene is not a medical device. Consumer DNA arrays are not clinical grade; nothing here is a diagnosis.
