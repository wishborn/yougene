"""Turn downloaded reference files into tables in the reference DuckDB.

Everything is parsed inside DuckDB for speed. ClinVar INFO values can contain
``#``, so header lines are filtered by their first column rather than with
DuckDB's ``comment`` option (which would truncate those lines).
"""

import zipfile
from pathlib import Path

from yougene.genome import CHROM_ORDER

PRIMARY = ", ".join(f"'{c}'" for c in CHROM_ORDER)
CHROM_ORDER_SQL = " ".join(f"WHEN '{c}' THEN {n}" for c, n in CHROM_ORDER.items())

# ClinVar review status -> stars (https://www.ncbi.nlm.nih.gov/clinvar/docs/review_status/)
STARS = {
    "practice_guideline": 4,
    "reviewed_by_expert_panel": 3,
    "criteria_provided,_multiple_submitters,_no_conflicts": 2,
    "criteria_provided,_single_submitter": 1,
    "criteria_provided,_conflicting_classifications": 1,
}


def _info(field: str) -> str:
    return f"NULLIF(regexp_extract(info, '(?:^|;){field}=([^;]*)', 1), '')"


def build_clinvar(con, path: Path) -> dict:
    stars = " ".join(f"WHEN '{k}' THEN {v}" for k, v in STARS.items())
    con.execute(
        f"""
        CREATE OR REPLACE TABLE clinvar AS
        WITH raw AS (
            SELECT * FROM read_csv(
                ?, delim = '\t', header = false, quote = '', escape = '',
                auto_detect = false, null_padding = true, compression = 'gzip',
                columns = {{
                    'chrom': 'VARCHAR', 'pos': 'VARCHAR', 'vcv': 'VARCHAR',
                    'ref': 'VARCHAR', 'alt': 'VARCHAR', 'qual': 'VARCHAR',
                    'filter': 'VARCHAR', 'info': 'VARCHAR'
                }}
            )
            WHERE NOT starts_with(chrom, '#') AND chrom IN ({PRIMARY})
        ),
        parsed AS (
            SELECT
                chrom,
                CASE chrom {CHROM_ORDER_SQL} END::UTINYINT AS chrom_order,
                CAST(pos AS UINTEGER) AS pos,
                ref,
                alt,
                CAST(vcv AS UINTEGER) AS vcv_id,
                TRY_CAST({_info("ALLELEID")} AS UINTEGER) AS allele_id,
                'rs' || split_part({_info("RS")}, '|', 1) AS rsid,
                {_info("CLNVC")} AS clnvc,
                {_info("CLNSIG")} AS sig_raw,
                lower(split_part({_info("CLNSIG")}, '|', 1)) AS sig1,
                lower({_info("CLNSIG")}) AS sigl,
                {_info("CLNREVSTAT")} AS revstat,
                {_info("CLNDN")} AS clndn,
                {_info("CLNDISDB")} AS clndisdb,
                {_info("GENEINFO")} AS geneinfo,
                {_info("MC")} AS mc,
                TRY_CAST({_info("ORIGIN")} AS UINTEGER) AS origin_bits,
                TRY_CAST({_info("AF_EXAC")} AS DOUBLE) AS af_exac,
                TRY_CAST({_info("AF_TGP")} AS DOUBLE) AS af_tgp,
                TRY_CAST({_info("AF_ESP")} AS DOUBLE) AS af_esp
            FROM raw
        )
        SELECT
            chrom, chrom_order, pos, ref, alt, vcv_id, allele_id, rsid, clnvc,
            sig_raw,
            CASE
                WHEN sig_raw IS NULL THEN 'none'
                WHEN regexp_matches(sig1,
                    '^pathogenic/likely_pathogenic') THEN 'pathogenic_likely'
                WHEN regexp_matches(sig1, '^pathogenic')
                    THEN 'pathogenic'
                WHEN regexp_matches(sig1, '^likely_pathogenic')
                    THEN 'likely_pathogenic'
                WHEN regexp_matches(sig1, '^uncertain')
                    THEN 'uncertain'
                WHEN regexp_matches(sig1, '^conflicting')
                    THEN 'conflicting'
                WHEN regexp_matches(sig1,
                    '^(benign/likely_benign|benign|likely_benign)') THEN 'benign'
                WHEN regexp_matches(sigl, 'drug_response') THEN 'drug_response'
                WHEN regexp_matches(sigl, 'risk_factor') THEN 'risk_factor'
                WHEN regexp_matches(sigl, 'protective') THEN 'protective'
                WHEN regexp_matches(sigl, 'association') THEN 'association'
                WHEN regexp_matches(sigl, 'not_provided') THEN 'not_provided'
                ELSE 'other'
            END AS sig_cat,
            regexp_matches(sigl, 'low_penetrance') AS low_penetrance,
            revstat,
            coalesce(CASE revstat {stars} END, 0)::UTINYINT AS stars,
            list_transform(string_split(replace(clndn, '_', ' '), '|'), x -> trim(x))
                AS conditions,
            clndisdb,
            list_transform(string_split(geneinfo, '|'), x -> split_part(x, ':', 1))
                AS genes,
            list_distinct(list_transform(string_split(mc, ','),
                x -> split_part(x, '|', 2))) AS consequences,
            origin_bits,
            af_exac, af_tgp, af_esp
        FROM parsed
        ORDER BY chrom_order, pos
        """,
        [str(path)],
    )
    # Every allele ClinVar knows at a single-base site (REF plus each ALT).
    # ClinVar splits multi-allelic sites into one record per ALT, so allele
    # checks must look at the whole site, not one record.
    con.execute(
        """
        CREATE OR REPLACE TABLE site_alleles AS
        SELECT chrom, chrom_order, pos,
               list_sort(list_distinct(flatten(list([ref, alt])))) AS alleles
        FROM clinvar
        WHERE length(ref) = 1 AND length(alt) = 1
          AND regexp_full_match(ref, '[ACGT]') AND regexp_full_match(alt, '[ACGT]')
        GROUP BY chrom, chrom_order, pos
        ORDER BY chrom_order, pos
        """
    )
    rows, sites = con.execute(
        "SELECT (SELECT count(*) FROM clinvar), (SELECT count(*) FROM site_alleles)"
    ).fetchone()
    return {"records": rows, "snv_sites": sites}


def build_gwas(con, path: Path, workdir: Path) -> dict:
    """The catalog ships as one TSV inside a zip; DuckDB can't read zips, so the
    TSV is extracted to ``workdir`` and removed afterwards."""
    with zipfile.ZipFile(path) as archive:
        members = [m for m in archive.infolist() if m.filename.endswith(".tsv")]
        if len(members) != 1:
            raise ValueError("Expected one TSV in the GWAS Catalog download.")
        tsv = Path(archive.extract(members[0], workdir))
    try:
        con.execute(
            """
            CREATE OR REPLACE TABLE gwas AS
            WITH raw AS (
                SELECT * FROM read_csv(
                    ?, delim = '\t', header = true, quote = '', escape = '',
                    all_varchar = true, null_padding = true
                )
            ),
            shaped AS (
                SELECT
                    row_number() OVER () AS assoc_id,
                    "STUDY ACCESSION" AS study_acc,
                    TRY_CAST("PUBMEDID" AS UBIGINT) AS pmid,
                    "FIRST AUTHOR" AS first_author,
                    TRY_CAST("DATE" AS DATE) AS published,
                    "STUDY" AS study,
                    "DISEASE/TRAIT" AS reported_trait,
                    "MAPPED_TRAIT" AS mapped_trait,
                    string_split("MAPPED_TRAIT_URI", ', ') AS trait_uris,
                    "INITIAL SAMPLE SIZE" AS initial_sample,
                    "REPLICATION SAMPLE SIZE" AS replication_sample,
                    "SNPS" AS snps,
                    CASE WHEN regexp_full_match("SNP_ID_CURRENT", '\\d+')
                         THEN 'rs' || "SNP_ID_CURRENT" END AS rsid_current,
                    "STRONGEST SNP-RISK ALLELE" AS risk_raw,
                    regexp_extract("STRONGEST SNP-RISK ALLELE",
                        '^rs\\d+-([ACGT])$', 1) AS risk_allele,
                    TRY_CAST("RISK ALLELE FREQUENCY" AS DOUBLE) AS risk_af,
                    TRY_CAST("PVALUE_MLOG" AS DOUBLE) AS p_mlog,
                    "P-VALUE" AS p_value,
                    "P-VALUE (TEXT)" AS p_text,
                    TRY_CAST("OR or BETA" AS DOUBLE) AS effect,
                    "95% CI (TEXT)" AS ci_text,
                    "MAPPED_GENE" AS mapped_gene,
                    "CONTEXT" AS context,
                    "CHR_ID" AS chr_grch38,
                    "CHR_POS" AS pos_grch38
                FROM raw
            )
            SELECT *,
                CASE
                    WHEN effect IS NULL THEN 'none'
                    WHEN regexp_matches(lower(coalesce(ci_text, '')),
                        '(increase|decrease)') THEN 'beta'
                    ELSE 'or'
                END AS effect_type,
                CASE WHEN regexp_matches(lower(coalesce(ci_text, '')), 'decrease')
                     THEN 'decrease'
                     WHEN regexp_matches(lower(coalesce(ci_text, '')), 'increase')
                     THEN 'increase' END AS beta_direction,
                regexp_full_match(snps, 'rs\\d+') AS single_rs,
                regexp_full_match(snps, 'rs\\d+') AND risk_allele <> ''
                    AS usable
            FROM shaped
            """,
            [str(tsv)],
        )
    finally:
        tsv.unlink(missing_ok=True)
    total, usable, rsids = con.execute(
        "SELECT count(*), count(*) FILTER (WHERE usable), "
        "count(DISTINCT snps) FILTER (WHERE single_rs) FROM gwas"
    ).fetchone()
    return {"associations": total, "usable": usable, "rsids": rsids}


def build_cytoband(con, path: Path) -> dict:
    con.execute(
        f"""
        CREATE OR REPLACE TABLE cytoband AS
        SELECT chrom, CASE chrom {CHROM_ORDER_SQL} END::UTINYINT AS chrom_order,
               "start", "end", band, stain
        FROM (
            SELECT CASE WHEN c = 'chrM' THEN 'MT' ELSE replace(c, 'chr', '') END
                       AS chrom,
                   CAST(s AS UINTEGER) AS "start", CAST(e AS UINTEGER) AS "end",
                   b AS band, g AS stain
            FROM read_csv(?, delim = '\t', header = false, auto_detect = false,
                          compression = 'gzip',
                          columns = {{'c': 'VARCHAR', 's': 'VARCHAR', 'e': 'VARCHAR',
                                      'b': 'VARCHAR', 'g': 'VARCHAR'}})
        )
        WHERE chrom IN ({PRIMARY})
        ORDER BY chrom_order, "start"
        """,
        [str(path)],
    )
    return {"bands": con.execute("SELECT count(*) FROM cytoband").fetchone()[0]}


BUILDERS = {"clinvar": build_clinvar, "gwas": build_gwas, "cytoband": build_cytoband}
