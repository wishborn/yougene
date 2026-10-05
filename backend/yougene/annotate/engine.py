"""Allele-aware annotation of one sample against the reference database.

Rules (spec section 4):

* Only SNP calls are interpreted. No-calls are skipped; 23andMe insertion /
  deletion codes carry no sequence and are never matched.
* A call matches a reference record by position (GRCh37). ``match_via`` says
  whether the probe's rsid agreed too, or the match came from position alone
  (23andMe ``i`` ids and merged rsids).
* "Carries" means carries the annotated allele, counted per copy. A rare REF
  allele can itself be the risk allele, so nothing assumes REF is safe.
* ClinVar and 23andMe are both plus-strand: an allele outside the site's known
  alleles is a mismatch, never silently flipped.
* GWAS risk alleles may be reported on either strand. Orientation is decided
  from the site's allele set (the person's own alleles plus every allele
  ClinVar knows there); palindromic A/T and C/G sites are only interpretable
  when the person is heterozygous.
"""

import json
from pathlib import Path

from yougene.db import connect

COMPLEMENT = str.maketrans("ACGT", "TGCA")

# Topics with their own opt-in gate in the UI (spec section 5, rule 4).
SENSITIVE_GENES = {
    "APOE": "apoe",
    "BRCA1": "hereditary_cancer",
    "BRCA2": "hereditary_cancer",
    "MLH1": "hereditary_cancer",
    "MSH2": "hereditary_cancer",
    "MSH6": "hereditary_cancer",
    "PMS2": "hereditary_cancer",
    "EPCAM": "hereditary_cancer",
    "LRRK2": "parkinsons",
    "GBA": "parkinsons",
    "GBA1": "parkinsons",
    "SNCA": "parkinsons",
    "HTT": "huntington",
}
RARE_AF = 0.001  # rare-variant guard: arrays are unreliable below this


def tier_for_stars(stars: int) -> str:
    return {4: "established", 3: "established", 2: "moderate", 1: "limited"}.get(
        stars, "research"
    )


def _gwas_orientation(alleles: str, ploidy: int, site: set[str], risk: str):
    """Return (dosage or None, strand status)."""
    user = set(alleles)
    known = user | site
    rc = risk.translate(COMPLEMENT)
    palindromic = len(known) >= 2 and (known <= {"A", "T"} or known <= {"C", "G"})
    if palindromic:
        if len(user) == 2:  # heterozygous at A/T or C/G: one copy either way
            return 1, "confirmed"
        return None, "ambiguous"
    if len(known) >= 2:
        if risk in known:
            return alleles.count(risk), "confirmed"
        if rc in known:
            return alleles.count(rc), "flipped"
        return None, "mismatch"
    # Only the person's own (homozygous or haploid) allele is known.
    (only,) = known
    if only == risk:
        return ploidy, "assumed"  # forward strand assumed; flip would mean 0
    if only == rc:
        return 0, "assumed"
    return 0, "confirmed"  # neither orientation can be present


def annotate(sample_db: Path, reference_db: Path, out_db: Path, ref_meta: dict) -> dict:
    """Write ``clinvar_findings``, ``gwas_findings`` and ``meta`` to ``out_db``."""
    partial = out_db.with_name(out_db.name + ".partial")
    partial.unlink(missing_ok=True)
    con = connect(partial)
    try:
        con.execute(f"ATTACH '{sample_db.as_posix()}' AS s (READ_ONLY)")
        con.execute(f"ATTACH '{reference_db.as_posix()}' AS r (READ_ONLY)")
        stats = {}
        stats["clinvar"] = _clinvar(con)
        stats["gwas"] = _gwas(con)
        con.execute("CREATE TABLE meta (key VARCHAR PRIMARY KEY, value JSON)")
        con.execute(
            "INSERT INTO meta VALUES ('reference', ?), ('stats', ?)",
            [json.dumps(ref_meta), json.dumps(stats)],
        )
        con.execute("DETACH s")
        con.execute("DETACH r")
        con.execute("CHECKPOINT")
    except BaseException:
        con.close()
        partial.unlink(missing_ok=True)
        raise
    con.close()
    partial.replace(out_db)
    return stats


def _clinvar(con) -> dict:
    sensitive = " ".join(
        f"WHEN list_contains(c.genes, '{gene}') THEN '{topic}'"
        for gene, topic in SENSITIVE_GENES.items()
    )
    con.execute(
        f"""
        CREATE TABLE clinvar_findings AS
        WITH snv AS (
            SELECT * FROM r.clinvar
            WHERE length(ref) = 1 AND length(alt) = 1
              AND (origin_bits IS NULL OR origin_bits & 1 = 1 OR origin_bits = 0)
        ),
        joined AS (
            SELECT
                k.probe_id, k.chrom, k.chrom_order, k.pos, k.alleles, k.ploidy,
                k.dup_conflict,
                c.vcv_id, c.rsid, c.ref, c.alt, c.sig_cat, c.sig_raw, c.stars,
                c.revstat, c.conditions, c.genes, c.consequences, c.low_penetrance,
                greatest(coalesce(c.af_exac, -1), coalesce(c.af_tgp, -1),
                         coalesce(c.af_esp, -1)) AS max_af,
                sa.alleles AS site_alleles,
                CASE WHEN k.probe_id = c.rsid THEN 'rsid' ELSE 'pos' END AS match_via,
                CASE {sensitive} END AS sensitive_topic
            FROM s.calls k
            JOIN snv c USING (chrom_order, pos)
            JOIN r.site_alleles sa USING (chrom_order, pos)
            WHERE k.call_type = 'snp'
        )
        SELECT *,
            -- every called letter must be an allele ClinVar knows at the site
            list_has_all(site_alleles, string_split(alleles, '')) AS alleles_consistent,
            length(alleles) - length(replace(alleles, alt, '')) AS dosage
        FROM joined
        """
    )
    con.execute(
        """
        ALTER TABLE clinvar_findings ADD COLUMN status VARCHAR;
        UPDATE clinvar_findings SET status =
            CASE WHEN NOT alleles_consistent THEN 'allele_mismatch'
                 WHEN dosage > 0 THEN 'carried'
                 ELSE 'not_carried' END;
        ALTER TABLE clinvar_findings ADD COLUMN zygosity VARCHAR;
        UPDATE clinvar_findings SET zygosity =
            CASE WHEN status <> 'carried' THEN NULL
                 WHEN ploidy = 1 THEN 'hemizygous'
                 WHEN dosage = 2 THEN 'homozygous'
                 ELSE 'heterozygous' END;
        ALTER TABLE clinvar_findings ADD COLUMN tier VARCHAR;
        UPDATE clinvar_findings SET tier =
            CASE WHEN stars >= 3 THEN 'established' WHEN stars = 2 THEN 'moderate'
                 WHEN stars = 1 THEN 'limited' ELSE 'research' END;
        ALTER TABLE clinvar_findings ADD COLUMN rare_guard BOOLEAN;
        """
    )
    con.execute(
        "UPDATE clinvar_findings SET rare_guard = "
        f"(max_af < 0 OR max_af < {RARE_AF}) "
        "AND sig_cat IN ('pathogenic', 'likely_pathogenic', 'pathogenic_likely')"
    )
    # Only keep what can be shown: carried alleles and mismatches. Records
    # where the person has the reference allele are summarised as counts.
    counts = dict(
        con.execute(
            "SELECT status, count(*) FROM clinvar_findings GROUP BY status"
        ).fetchall()
    )
    con.execute("DELETE FROM clinvar_findings WHERE status = 'not_carried'")
    return {
        "records_at_tested_positions": sum(counts.values()),
        "carried": counts.get("carried", 0),
        "allele_mismatch": counts.get("allele_mismatch", 0),
        "not_carried": counts.get("not_carried", 0),
    }


# The same rules as ``_gwas_orientation``, as a DuckDB macro so the whole join
# stays in the database (a Python loop plus inserts took minutes on real data).
# tests/test_annotate.py checks the two agree on every combination.
GWAS_ORIENT_MACRO = """
CREATE OR REPLACE TEMP MACRO gwas_orient(alleles, ploidy, site, risk) AS (
    WITH v AS (
        SELECT
            list_distinct(string_split(alleles, '')) AS u,
            list_distinct(list_concat(string_split(alleles, ''), site)) AS k,
            translate(risk, 'ACGT', 'TGCA') AS rc
    ),
    w AS (
        SELECT u, k, rc,
               len(k) >= 2 AND (list_has_all(['A', 'T'], k)
                                OR list_has_all(['C', 'G'], k)) AS pal
        FROM v
    )
    SELECT CASE
        WHEN pal AND len(u) = 2 THEN {'dosage': 1, 'strand': 'confirmed'}
        WHEN pal THEN {'dosage': NULL, 'strand': 'ambiguous'}
        WHEN len(k) >= 2 AND list_contains(k, risk) THEN
            {'dosage': length(alleles) - length(replace(alleles, risk, '')),
             'strand': 'confirmed'}
        WHEN len(k) >= 2 AND list_contains(k, rc) THEN
            {'dosage': length(alleles) - length(replace(alleles, rc, '')),
             'strand': 'flipped'}
        WHEN len(k) >= 2 THEN {'dosage': NULL, 'strand': 'mismatch'}
        WHEN k[1] = risk THEN {'dosage': ploidy, 'strand': 'assumed'}
        WHEN k[1] = rc THEN {'dosage': 0, 'strand': 'assumed'}
        ELSE {'dosage': 0, 'strand': 'confirmed'}
    END
    FROM w
)
"""


def _gwas(con) -> dict:
    con.execute(GWAS_ORIENT_MACRO)
    con.execute(
        """
        CREATE TABLE gwas_hits AS
        WITH g AS (
            SELECT assoc_id, snps, rsid_current, risk_allele FROM r.gwas WHERE usable
        ),
        k AS (SELECT * FROM s.calls WHERE call_type = 'snp'),
        pairs AS (
            -- two equi-joins rather than one OR join, which would not use a hash join
            SELECT g.assoc_id, k.probe_id FROM k JOIN g ON k.probe_id = g.snps
            UNION
            SELECT g.assoc_id, k.probe_id FROM k JOIN g ON k.probe_id = g.rsid_current
        ),
        joined AS (
            SELECT p.assoc_id, k.probe_id, k.chrom, k.chrom_order, k.pos, k.alleles,
                   k.ploidy, g.risk_allele, coalesce(sa.alleles, []) AS site
            FROM pairs p
            JOIN k USING (probe_id)
            JOIN g USING (assoc_id)
            LEFT JOIN r.site_alleles sa USING (chrom_order, pos)
        )
        SELECT assoc_id, probe_id, chrom, chrom_order, pos, alleles, ploidy,
               risk_allele, o.dosage::UTINYINT AS dosage, o.strand AS strand
        FROM (SELECT *, gwas_orient(alleles, ploidy, site, risk_allele) AS o
              FROM joined)
        """
    )
    con.execute(
        """
        CREATE TABLE gwas_findings AS
        SELECT h.*, g.study_acc, g.pmid, g.first_author, g.published, g.study,
               g.reported_trait, g.mapped_trait, g.trait_uris, g.initial_sample,
               g.risk_af, g.p_mlog, g.p_value, g.effect, g.effect_type,
               g.beta_direction, g.ci_text, g.mapped_gene, g.context
        FROM gwas_hits h JOIN r.gwas g USING (assoc_id)
        """
    )
    con.execute("DROP TABLE gwas_hits")
    counts = dict(
        con.execute(
            "SELECT strand, count(*) FROM gwas_findings GROUP BY strand"
        ).fetchall()
    )
    carried = con.execute(
        "SELECT count(*) FROM gwas_findings WHERE dosage > 0"
    ).fetchone()[0]
    return {
        "associations_at_tested_snps": sum(counts.values()),
        "by_strand": counts,
        "carrying_risk_allele": carried,
    }
