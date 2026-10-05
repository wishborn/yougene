"""API for annotation results: ClinVar (health) and GWAS (traits) findings."""

import re
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from yougene import store
from yougene.annotate import runner
from yougene.annotate.engine import SENSITIVE_GENES
from yougene.db import connect
from yougene.jobs import jobs
from yougene.refdata import manager

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


def require_health_consent(topics: list[str] | None = None) -> None:
    """Health results are opt-in, enforced here as well as in the UI."""
    consent = store.get_consent()
    if not consent.get("health"):
        raise HTTPException(403, "Health results are hidden until you opt in.")
    for topic in topics or []:
        if not consent.get(f"topic.{topic}"):
            raise HTTPException(403, f"Opt in to the {topic} topic first.")


@router.get("/consent")
def get_consent():
    return store.get_consent()


class ConsentChange(BaseModel):
    name: str
    granted: bool


@router.put("/consent")
def set_consent(change: ConsentChange):
    try:
        return store.set_consent(change.name, change.granted)
    except KeyError:
        raise HTTPException(422, f"Unknown consent {change.name!r}.") from None


@router.get("/samples/{sample_id}/clinvar/summary")
def clinvar_summary(sample_id: str):
    """Counts by category, tier and topic (after opt-in)."""
    require_health_consent()
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
    if topic and (bad := [t for t in topic if t not in TOPICS]):
        raise HTTPException(422, f"Unknown topic {bad[0]!r}.")
    require_health_consent(topic)
    where, args = ["status = ?", "stars >= ?"], [status, min_stars]
    if sig:
        if bad := [s for s in sig if s not in SIG_CATS]:
            raise HTTPException(422, f"Unknown category {bad[0]!r}.")
        where.append(_in("sig_cat", sig))
        args += sig
    if topic:
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


GENE_SYMBOL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,30}")


@router.get("/samples/{sample_id}/gene/{symbol}")
def gene_view(sample_id: str, symbol: str):
    """One gene: how many known disease-linked single-letter variants it has
    in ClinVar, which of those positions this file read and what was read
    there, and any findings carried in the gene. Health opt-in required;
    sensitive genes need their topic opt-in."""
    if not GENE_SYMBOL.fullmatch(symbol):
        raise HTTPException(422, "Not a gene symbol.")
    gene = symbol.upper()
    topic = SENSITIVE_GENES.get(gene)
    require_health_consent([topic] if topic else None)
    _sample_or_404(sample_id)
    ref = manager.open_reference()
    if ref is None:
        raise HTTPException(409, "Install the reference data first.")
    ref.close()
    con = connect()
    try:
        con.execute(f"ATTACH '{manager.db_path().as_posix()}' AS r (READ_ONLY)")
        con.execute(
            f"ATTACH '{store.sample_path(sample_id).as_posix()}' AS s (READ_ONLY)"
        )
        cursor = con.execute(
            """
            WITH v AS (
                SELECT chrom, chrom_order, pos, ref, alt, vcv_id, rsid, sig_cat, stars
                FROM r.clinvar
                WHERE list_contains(list_transform(genes, g -> upper(g)), ?)
                  AND sig_cat IN
                      ('pathogenic', 'likely_pathogenic', 'pathogenic_likely')
                  AND length(ref) = 1 AND length(alt) = 1
            )
            SELECT v.chrom, v.pos, v.ref, v.alt, v.vcv_id, v.rsid, v.sig_cat, v.stars,
                   k.probe_id, k.alleles, k.call_type
            FROM v
            LEFT JOIN s.calls k ON k.chrom_order = v.chrom_order AND k.pos = v.pos
            ORDER BY v.chrom_order, v.pos, v.vcv_id
            """,
            [gene],
        )
        names = [d[0] for d in cursor.description]
        rows = [dict(zip(names, r, strict=True)) for r in cursor.fetchall()]
    finally:
        con.close()
    known = {(r["chrom"], r["pos"], r["alt"]) for r in rows}
    tested_rows = [r for r in rows if r["call_type"] == "snp"]
    tested = {(r["chrom"], r["pos"], r["alt"]) for r in tested_rows}
    carried = [r for r in tested_rows if r["alt"] in (r["alleles"] or "")]
    return {
        "gene": gene,
        "sensitive_topic": topic,
        "known_pathogenic_snvs": len(known),
        "tested": len(tested),
        "carried": carried,
        "tested_positions": tested_rows[:500],
        "region": (
            {
                "chrom": rows[0]["chrom"],
                "start": min(r["pos"] for r in rows),
                "end": max(r["pos"] for r in rows),
            }  # fmt: skip
            if rows
            else None
        ),
    }
