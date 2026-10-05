"""Shared loading for consumer genotyping-array exports.

Every vendor format is read into a temporary ``raw`` table of
``(probe_id, chrom, pos, gt)`` strings, then normalised into ``calls`` the same
way: chromosome codes mapped to 1-22/X/Y/MT, genotypes as sorted letters,
no-calls kept, duplicate positions grouped.
"""

from pathlib import Path

from yougene.genome import BUILD_ANCHORS_37, CHROM_ORDER, x_non_par_sql
from yougene.importers.base import CALLS_SCHEMA, Detection, ImportFailed

# Vendor chromosome codes -> ours. AncestryDNA numbers X/Y/PAR/MT as 23-26;
# PAR calls sit on X.
CHROM_CODES = {
    **{c: c for c in CHROM_ORDER},
    "23": "X",
    "24": "Y",
    "25": "X",
    "XY": "X",
    "PAR": "X",
    "26": "MT",
    "M": "MT",
    "MT": "MT",
}
# Rows on chromosomes we can't place (some exports use 0 for unmapped probes)
# are skipped if they're a small share of the file; otherwise the file is refused.
MAX_UNPLACED_SHARE = 0.005


def read_raw(
    con,
    path: Path,
    *,
    vendor: str,
    delim: str,
    two_allele_columns: bool = False,
    quoted: bool = False,
    header_names: tuple[str, ...] = ("rsid",),
) -> None:
    """Create TEMP ``raw``. ``header_names``: first-column values of header
    rows to drop (files sometimes repeat the header when concatenated)."""
    names = ["probe_id", "chrom", "pos", "a1"] + (["a2"] if two_allele_columns else [])
    columns = ", ".join(f"'{n}': 'VARCHAR'" for n in names)
    quote = "'\"'" if quoted else "''"
    try:
        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE raw_in AS
            SELECT * FROM read_csv(
                ?, delim = ?, header = false, comment = '#', quote = {quote},
                escape = {quote}, auto_detect = false, null_padding = true,
                columns = {{{columns}}}
            )
            """,
            [str(path), delim],
        )
    except Exception as error:  # DuckDB raises several types; none carry data we show
        raise ImportFailed(
            "unreadable",
            f"The file couldn't be read as {vendor} raw data. It may be damaged or "
            "in a different format.",
        ) from error

    strip = "trim(replace({}, '\"', ''))"
    gt = (
        f"CASE WHEN {strip.format('a1')} IN ('0', '-') OR {strip.format('a2')} IN "
        f"('0', '-') THEN '--' ELSE {strip.format('a1')} || {strip.format('a2')} END"
        if two_allele_columns
        else strip.format("a1")
    )
    codes = " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in CHROM_CODES.items())
    skip = ", ".join(f"'{h.lower()}'" for h in header_names)
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE raw AS
        SELECT probe_id, CASE upper(chrom) {codes} END AS chrom, chrom AS chrom_in,
               pos, gt
        FROM (
            SELECT {strip.format("probe_id")} AS probe_id,
                   {strip.format("chrom")} AS chrom,
                   {strip.format("pos")} AS pos,
                   upper({gt}) AS gt
            FROM raw_in
        )
        WHERE lower(probe_id) NOT IN ({skip})
        """
    )
    con.execute("DROP TABLE raw_in")


def build_calls(con, vendor: str) -> dict:
    """Validate TEMP ``raw`` and create ``calls`` from it."""
    total, unplaced, invalid = con.execute(
        """
        SELECT count(*),
               count(*) FILTER (WHERE chrom IS NULL),
               count(*) FILTER (WHERE chrom IS NOT NULL AND NOT (
                   probe_id IS NOT NULL AND probe_id <> ''
                   AND TRY_CAST(pos AS UINTEGER) IS NOT NULL
                   AND TRY_CAST(pos AS UINTEGER) > 0
                   AND regexp_full_match(gt, '([ACGTDI]{1,2}|--)')
               ))
        FROM raw
        """
    ).fetchone()
    if total == 0:
        raise ImportFailed("empty", "The file contains no genotype rows.")
    if invalid:
        raise ImportFailed(
            "invalid_rows",
            f"{invalid:,} of {total:,} rows aren't valid {vendor} calls, so the "
            "file wasn't imported. It may be damaged or edited.",
        )
    if unplaced > total * MAX_UNPLACED_SHARE:
        raise ImportFailed(
            "invalid_rows",
            f"{unplaced:,} of {total:,} rows are on chromosomes YouGene doesn't "
            "recognise, so the file wasn't imported.",
        )

    order = " ".join(f"WHEN '{c}' THEN {n}" for c, n in CHROM_ORDER.items())
    con.execute(CALLS_SCHEMA)
    con.execute(
        f"""
        INSERT INTO calls
        WITH norm AS (
            SELECT
                probe_id,
                CASE WHEN probe_id LIKE 'rs%' THEN 'rs' ELSE 'vendor' END AS id_kind,
                chrom,
                CASE chrom {order} END AS chrom_order,
                CAST(pos AS UINTEGER) AS pos,
                CASE
                    WHEN gt = '--' THEN ''
                    WHEN length(gt) = 2 AND gt[1] > gt[2] THEN gt[2] || gt[1]
                    ELSE gt
                END AS alleles,
                CASE WHEN gt = '--' THEN NULL ELSE length(gt) END AS ploidy,
                CASE
                    WHEN gt = '--' THEN 'nocall'
                    WHEN regexp_matches(gt, '[DI]') THEN 'indel_code'
                    ELSE 'snp'
                END AS call_type
            FROM raw
            WHERE chrom IS NOT NULL
        ),
        groups AS (
            SELECT chrom_order, pos,
                   count(DISTINCT alleles) FILTER (WHERE call_type <> 'nocall') > 1
                       AS conflict
            FROM norm
            GROUP BY chrom_order, pos
            HAVING count(*) > 1
        ),
        numbered AS (
            SELECT *, row_number() OVER (ORDER BY chrom_order, pos) AS group_id
            FROM groups
        )
        SELECT n.probe_id, n.id_kind, n.chrom, n.chrom_order, n.pos, n.alleles,
               n.ploidy, n.call_type, g.group_id, coalesce(g.conflict, false)
        FROM norm n
        LEFT JOIN numbered g USING (chrom_order, pos)
        ORDER BY n.chrom_order, n.pos, n.probe_id
        """
    )
    con.execute("DROP TABLE raw")
    duplicate_ids = con.execute(
        "SELECT count(*) FROM (SELECT probe_id FROM calls "
        "GROUP BY probe_id HAVING count(*) > 1)"
    ).fetchone()[0]
    if duplicate_ids:
        raise ImportFailed(
            "duplicate_ids",
            f"{duplicate_ids:,} probe ids appear more than once. The file may be "
            "damaged or merged from two files.",
        )
    return {"rows": total - unplaced, "skipped_unplaced": unplaced}


def confirm_build(con, detection: Detection) -> dict:
    """Check the build claim against known GRCh37 positions."""
    ids = list(BUILD_ANCHORS_37)
    found = con.execute(
        "SELECT probe_id, chrom, pos FROM calls WHERE probe_id IN "
        f"({', '.join('?' for _ in ids)})",
        ids,
    ).fetchall()
    matched = [p for p, c, pos in found if BUILD_ANCHORS_37[p] == (c, pos)]
    mismatched = [p for p, c, pos in found if BUILD_ANCHORS_37[p] != (c, pos)]
    evidence = {
        "header": detection.build_from_header,
        "anchors_checked": len(found),
        "anchors_matching_grch37": len(matched),
    }
    if mismatched:
        raise ImportFailed(
            "build_mismatch",
            f"{len(mismatched)} reference SNPs sit at positions that don't match "
            "GRCh37 (build 37). YouGene currently reads build 37 files only.",
        )
    header = detection.build_from_header
    if header not in (None, "37"):
        raise ImportFailed(
            "unsupported_build",
            f"This file says it uses genome build {header}. YouGene currently "
            "reads build 37 files only.",
        )
    if header == "37" or len(matched) >= 2:
        return {"build": "GRCh37", **evidence}
    raise ImportFailed(
        "unknown_build",
        "YouGene couldn't confirm which genome build this file uses, so it "
        "wasn't imported.",
    )


def fix_ploidy(con, inferred_sex: str) -> dict:
    """Some vendors (e.g. AncestryDNA) write single-copy calls as two letters.
    MT is always single-copy; X outside the pseudo-autosomal regions and Y are
    single-copy in XY samples. Homozygous two-letter calls there become one
    letter; heterozygous ones are left as they are (they're genotyping noise
    and are visible in QC)."""
    clause = "chrom = 'MT'"
    if inferred_sex == "XY":
        clause = f"({clause} OR chrom = 'Y' OR (chrom = 'X' AND {x_non_par_sql()}))"
    changed = con.execute(
        f"""
        UPDATE calls SET alleles = alleles[1], ploidy = 1
        WHERE {clause} AND ploidy = 2 AND alleles[1] = alleles[2]
        RETURNING 1
        """
    ).fetchall()
    return {"made_single_copy": len(changed)}
