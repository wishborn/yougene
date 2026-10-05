"""API for genome-wide views: cytobands, density bins, ROH, markers, coverage."""

import re
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from yougene import store
from yougene.analysis import genome, pgx
from yougene.analysis import known_traits as known_traits_module
from yougene.annotate.engine import SENSITIVE_GENES
from yougene.db import connect
from yougene.genome import CHROMS
from yougene.refdata import manager

router = APIRouter(prefix="/api")
GENE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,30}")
DISEASE = ("pathogenic", "likely_pathogenic", "pathogenic_likely")


def _sample_or_404(sample_id: str) -> None:
    try:
        found = store.get_sample(sample_id)
    except KeyError:
        found = None
    if found is None:
        raise HTTPException(404, "No such sample.")


def _reference_or_409():
    con = manager.open_reference()
    if con is None:
        raise HTTPException(409, "Install the reference data first.")
    return con


@router.get("/reference/cytobands")
def cytobands():
    con = _reference_or_409()
    try:
        rows = con.execute(
            'SELECT chrom, "start", "end", band, stain FROM cytoband '
            'ORDER BY chrom_order, "start"'
        ).fetchall()
    finally:
        con.close()
    out: dict[str, list[dict]] = {c: [] for c in CHROMS}
    for chrom, start, end, band, stain in rows:
        out[chrom].append({"start": start, "end": end, "band": band, "stain": stain})
    lengths = {c: (bands[-1]["end"] if bands else 0) for c, bands in out.items()}
    return {"bands": out, "lengths": lengths}


@router.get("/samples/{sample_id}/genome/bins")
def bins(sample_id: str, bin_kb: Annotated[int, Query(ge=100, le=50_000)] = 1000):
    _sample_or_404(sample_id)
    con = store.open_sample(sample_id)
    try:
        return {
            "bin_bp": bin_kb * 1000,
            "chroms": genome.density_bins(con, bin_kb * 1000),
        }
    finally:
        con.close()


@lru_cache(maxsize=16)
def _roh(sample_id: str, mtime: float) -> dict:
    con = store.open_sample(sample_id)
    try:
        return genome.runs_of_homozygosity(con)
    finally:
        con.close()


@router.get("/samples/{sample_id}/genome/roh")
def roh(sample_id: str):
    _sample_or_404(sample_id)
    return _roh(sample_id, store.sample_path(sample_id).stat().st_mtime)


@router.get("/samples/{sample_id}/genome/markers")
def markers(sample_id: str, health: bool = False):
    """Positions of findings for the explorer. ClinVar markers only when the
    caller says the user opted in to health results."""
    _sample_or_404(sample_id)
    con = store.open_annotation(sample_id)
    if con is None:
        return {"traits": [], "health": []}
    try:
        traits = con.execute(
            "SELECT DISTINCT chrom, pos, probe_id FROM gwas_findings "
            "WHERE dosage > 0 AND p_mlog >= 7.3 "
            "AND strand IN ('confirmed', 'flipped', 'assumed') ORDER BY chrom, pos"
        ).fetchall()
        health_rows = []
        # Health markers need the install-wide opt-in, whatever the caller asks.
        if health and store.get_consent().get("health"):
            health_rows = con.execute(
                "SELECT DISTINCT chrom, pos, probe_id FROM clinvar_findings "
                "WHERE status = 'carried' AND sensitive_topic IS NULL "
                f"AND sig_cat IN {DISEASE} AND stars >= 2 ORDER BY chrom, pos"
            ).fetchall()
    finally:
        con.close()

    def shape(rows):
        return [{"chrom": c, "pos": p, "probe_id": i} for c, p, i in rows]

    return {"traits": shape(traits), "health": shape(health_rows)}


@router.get("/samples/{sample_id}/coverage")
def coverage(sample_id: str, gene: Annotated[list[str], Query(min_length=1)]):
    """How many single-base ClinVar pathogenic/likely pathogenic variants each
    gene has, and how many of those positions this file measured. A clear
    result only speaks for the measured ones."""
    _sample_or_404(sample_id)
    genes = sorted({g.upper() for g in gene})[:50]
    if bad := [g for g in genes if not GENE.fullmatch(g)]:
        raise HTTPException(422, f"Not a gene symbol: {bad[0]!r}.")
    ref = _reference_or_409()
    ref.close()
    con = connect()
    try:
        con.execute(f"ATTACH '{manager.db_path().as_posix()}' AS r (READ_ONLY)")
        con.execute(
            f"ATTACH '{store.sample_path(sample_id).as_posix()}' AS s (READ_ONLY)"
        )
        rows = con.execute(
            f"""
            WITH v AS (
                SELECT DISTINCT g AS gene, chrom_order, pos
                FROM (SELECT unnest(genes) AS g, chrom_order, pos FROM r.clinvar
                      WHERE sig_cat IN {DISEASE} AND length(ref) = 1
                        AND length(alt) = 1)
                WHERE upper(g) IN ({", ".join("?" for _ in genes)})
            )
            SELECT upper(v.gene), count(*),
                   count(*) FILTER (WHERE EXISTS (
                       SELECT 1 FROM s.calls k
                       WHERE k.chrom_order = v.chrom_order AND k.pos = v.pos
                         AND k.call_type <> 'nocall'))
            FROM v GROUP BY 1
            """,
            genes,
        ).fetchall()
    finally:
        con.close()
    found = {g: {"known_pathogenic_snvs": n, "tested": t} for g, n, t in rows}
    return {
        "genes": {
            g: found.get(g, {"known_pathogenic_snvs": 0, "tested": 0}) for g in genes
        }
    }


@router.get("/samples/{sample_id}/known-traits")
def known_traits(sample_id: str):
    _sample_or_404(sample_id)
    con = store.open_sample(sample_id)
    try:
        return {"traits": known_traits_module.evaluate(con)}
    finally:
        con.close()


@router.get("/samples/{sample_id}/pgx")
def pharmacogenomics(sample_id: str):
    _sample_or_404(sample_id)
    con = store.open_sample(sample_id)
    try:
        return {"genes": pgx.evaluate(con)}
    finally:
        con.close()


@router.get("/samples/{sample_id}/variant")
def variant_detail(
    sample_id: str,
    chrom: str,
    pos: Annotated[int, Query(ge=1)],
):
    """Everything known about one position: this sample's call(s), ClinVar
    records there (only after opt-in; sensitive topics need their own), trait
    associations for the probe, and curated trait / medicine rules using it."""
    _sample_or_404(sample_id)
    if chrom not in CHROMS:
        raise HTTPException(422, f"Unknown chromosome {chrom!r}.")
    con = store.open_sample(sample_id)
    try:
        cursor = con.execute(
            "SELECT probe_id, id_kind, alleles, ploidy, call_type, dup_group, "
            "dup_conflict FROM calls WHERE chrom = ? AND pos = ? ORDER BY probe_id",
            [chrom, pos],
        )
        names = [d[0] for d in cursor.description]
        calls = [dict(zip(names, r, strict=True)) for r in cursor.fetchall()]
    finally:
        con.close()
    if not calls:
        raise HTTPException(404, "This sample has no call at that position.")
    probes = [c["probe_id"] for c in calls]

    clinvar, hidden = [], 0
    ref = manager.open_reference()
    if ref is not None:
        try:
            cursor = ref.execute(
                "SELECT vcv_id, rsid, ref, alt, sig_cat, stars, conditions, genes, "
                "consequences, revstat FROM clinvar WHERE chrom = ? AND pos = ? "
                "ORDER BY stars DESC, vcv_id",
                [chrom, pos],
            )
            names = [d[0] for d in cursor.description]
            records = [dict(zip(names, r, strict=True)) for r in cursor.fetchall()]
        finally:
            ref.close()
        consent = store.get_consent()
        called = [c["alleles"] for c in calls if c["call_type"] == "snp"]
        for record in records:
            topic = next(
                (
                    SENSITIVE_GENES[g]
                    for g in record["genes"] or []
                    if g in SENSITIVE_GENES
                ),
                None,
            )
            allowed = consent.get("health") and (
                topic is None or consent.get(f"topic.{topic}")
            )
            if not allowed:
                hidden += 1
                continue
            single = len(record["ref"]) == 1 and len(record["alt"]) == 1
            record["your_copies"] = (
                max((a.count(record["alt"]) for a in called), default=None)
                if single and called
                else None
            )
            record["sensitive_topic"] = topic
            clinvar.append(record)

    traits = []
    annot = store.open_annotation(sample_id)
    if annot is not None:
        try:
            cursor = annot.execute(
                "SELECT mapped_trait, reported_trait, risk_allele, dosage, strand, "
                "effect, effect_type, beta_direction, p_value, p_mlog, pmid, "
                "first_author, published FROM gwas_findings "
                f"WHERE probe_id IN ({', '.join('?' for _ in probes)}) "
                "ORDER BY p_mlog DESC LIMIT 50",
                probes,
            )
            names = [d[0] for d in cursor.description]
            traits = [dict(zip(names, r, strict=True)) for r in cursor.fetchall()]
        finally:
            annot.close()

    curated = [
        {"kind": "trait", "id": t.id, "title": t.title}
        for t in known_traits_module.KNOWN_TRAITS
        if (t.chrom, t.pos) == (chrom, pos)
    ] + [
        {"kind": "medicine", "id": g.gene, "title": f"{g.gene} ({v.star})"}
        for g in pgx.GENES
        for v in g.variants
        if (v.chrom, v.pos) == (chrom, pos)
    ]
    return {
        "chrom": chrom,
        "pos": pos,
        "calls": calls,
        "clinvar": clinvar,
        "clinvar_hidden": hidden,
        "traits": traits,
        "curated": curated,
    }
