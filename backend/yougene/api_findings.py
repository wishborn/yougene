"""API for annotation results: ClinVar (health) and GWAS (traits) findings."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from yougene import store
from yougene.annotate import runner
from yougene.jobs import jobs

router = APIRouter(prefix="/api")

CLINVAR_COLUMNS = [
    "probe_id", "chrom", "pos", "alleles", "ploidy", "dup_conflict", "vcv_id", "rsid",
    "ref", "alt", "sig_cat", "sig_raw", "stars", "revstat", "conditions", "genes",
    "consequences", "low_penetrance", "max_af", "match_via", "sensitive_topic",
    "status", "zygosity", "dosage", "tier", "rare_guard",
]  # fmt: skip
GWAS_COLUMNS = [
    "assoc_id", "probe_id", "chrom", "pos", "alleles", "ploidy", "risk_allele",
    "dosage", "strand", "study_acc", "pmid", "first_author", "published", "study",
    "reported_trait", "mapped_trait", "initial_sample", "risk_af", "p_mlog",
    "p_value", "effect", "effect_type", "beta_direction", "ci_text", "mapped_gene",
    "context",
]  # fmt: skip
SIG_CATS = {
    "pathogenic", "likely_pathogenic", "pathogenic_likely", "uncertain",
    "conflicting", "benign", "drug_response", "risk_factor", "protective",
    "association", "not_provided", "other", "none",
}  # fmt: skip
# Most clinically relevant first; within a group, best-reviewed first.
SIGNIFICANCE_ORDER = (
    "CASE sig_cat WHEN 'pathogenic' THEN 0 WHEN 'pathogenic_likely' THEN 1 "
    "WHEN 'likely_pathogenic' THEN 2 WHEN 'risk_factor' THEN 3 "
    "WHEN 'drug_response' THEN 4 WHEN 'conflicting' THEN 5 WHEN 'uncertain' THEN 6 "
    "WHEN 'protective' THEN 7 WHEN 'association' THEN 8 ELSE 9 END"
)
TOPICS = {"apoe", "hereditary_cancer", "parkinsons", "huntington"}
STRANDS = {"confirmed", "flipped", "assumed", "ambiguous", "mismatch"}


def _sample_or_404(sample_id: str) -> None:
    try:
        found = store.get_sample(sample_id)
    except KeyError:
        found = None
    if found is None:
        raise HTTPException(404, "No such sample.")


def _annotation_or_409(sample_id: str):
    _sample_or_404(sample_id)
    con = store.open_annotation(sample_id)
    if con is None:
        raise HTTPException(409, "This sample hasn't been annotated yet.")
    return con


def _in(column: str, values: list[str]) -> str:
    return f"{column} IN ({', '.join('?' for _ in values)})"


def _page(con, table, columns, where, args, order, page, page_size) -> dict:
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    total = con.execute(f"SELECT count(*) FROM {table} {clause}", args).fetchone()[0]
    rows = con.execute(
        f"SELECT {', '.join(columns)} FROM {table} {clause} ORDER BY {order} "
        "LIMIT ? OFFSET ?",
        [*args, page_size, page * page_size],
    ).fetchall()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "rows": [dict(zip(columns, r, strict=True)) for r in rows],
    }


@router.get("/samples/{sample_id}/annotation")
def annotation_state(sample_id: str):
    _sample_or_404(sample_id)
    return runner.state(sample_id)


@router.post("/samples/{sample_id}/annotate", status_code=202)
def annotate_sample(sample_id: str):
    _sample_or_404(sample_id)
    if runner.reference_fingerprint() is None:
        raise HTTPException(409, "Install the reference data first.")
    job = jobs.submit("annotate", lambda p: runner.annotate_sample(sample_id, p))
    return {"job_id": job.id}


@router.get("/samples/{sample_id}/clinvar/summary")
def clinvar_summary(sample_id: str):
    """Counts only, by category, tier and topic: safe to show before opt-in."""
    con = _annotation_or_409(sample_id)
    try:
        rows = con.execute(
            "SELECT sig_cat, tier, sensitive_topic, rare_guard, count(*) "
            "FROM clinvar_findings WHERE status = 'carried' GROUP BY ALL"
        ).fetchall()
    finally:
        con.close()
    return {
        "counts": [
            {"sig_cat": s, "tier": t, "topic": topic, "rare_guard": rare, "count": n}
            for s, t, topic, rare, n in rows
        ]
    }


@router.get("/samples/{sample_id}/clinvar")
def clinvar_findings(
    sample_id: str,
    sig: Annotated[list[str] | None, Query()] = None,
    min_stars: Annotated[int, Query(ge=0, le=4)] = 0,
    topic: Annotated[list[str] | None, Query()] = None,
    status: Literal["carried", "allele_mismatch"] = "carried",
    page: Annotated[int, Query(ge=0)] = 0,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """Health findings. Sensitive topics (APOE, hereditary cancer, Parkinson's,
    Huntington's) are left out unless named in ``topic``; each has its own
    consent gate in the UI."""
    where, args = ["status = ?", "stars >= ?"], [status, min_stars]
    if sig:
        if bad := [s for s in sig if s not in SIG_CATS]:
            raise HTTPException(422, f"Unknown category {bad[0]!r}.")
        where.append(_in("sig_cat", sig))
        args += sig
    if topic:
        if bad := [t for t in topic if t not in TOPICS]:
            raise HTTPException(422, f"Unknown topic {bad[0]!r}.")
        where.append(f"(sensitive_topic IS NULL OR {_in('sensitive_topic', topic)})")
        args += topic
    else:
        where.append("sensitive_topic IS NULL")
    con = _annotation_or_409(sample_id)
    try:
        return _page(
            con,
            "clinvar_findings",
            CLINVAR_COLUMNS,
            where,
            args,
            SIGNIFICANCE_ORDER + ", stars DESC, chrom_order, pos, vcv_id",
            page,
            page_size,
        )
    finally:
        con.close()


@router.get("/samples/{sample_id}/traits")
def trait_findings(
    sample_id: str,
    min_p_mlog: Annotated[float, Query(ge=0)] = 7.3,  # p < 5e-8
    carrying: bool = True,
    strand: Annotated[list[str] | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=80)] = None,
    sort: Literal["p", "trait", "position"] = "p",
    page: Annotated[int, Query(ge=0)] = 0,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    where, args = ["p_mlog >= ?"], [min_p_mlog]
    if carrying:
        where.append("dosage > 0")
    strands = strand or ["confirmed", "flipped", "assumed"]
    if bad := [s for s in strands if s not in STRANDS]:
        raise HTTPException(422, f"Unknown strand status {bad[0]!r}.")
    where.append(_in("strand", strands))
    args += strands
    if q:
        where.append("(mapped_trait ILIKE ? OR reported_trait ILIKE ? OR probe_id = ?)")
        args += [f"%{q}%", f"%{q}%", q]
    order = {
        "p": "p_mlog DESC, assoc_id",
        "trait": "mapped_trait, p_mlog DESC",
        "position": "chrom_order, pos, assoc_id",
    }[sort]
    con = _annotation_or_409(sample_id)
    try:
        return _page(
            con, "gwas_findings", GWAS_COLUMNS, where, args, order, page, page_size
        )
    finally:
        con.close()
