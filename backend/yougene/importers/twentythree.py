"""23andMe raw data (all chip versions export the same 4-column TSV).

Header comment lines start with ``#``; the last one names the columns:
``# rsid  chromosome  position  genotype``. Calls are plus-strand on GRCh37.
Genotypes: two letters (diploid), one letter (haploid X/Y/MT), ``--`` for a
no-call, and ``D``/``I`` codes for insertion/deletion probes.
"""

import re
from pathlib import Path

from yougene.genome import BUILD_ANCHORS_37, CHROM_ORDER
from yougene.importers.base import CALLS_SCHEMA, Detection, ImportFailed

COLUMN_LINE = "# rsid\tchromosome\tposition\tgenotype"
BUILD = re.compile(r"build\s*(\d+)", re.IGNORECASE)
HEADER_LINES = 60


def _head(path: Path) -> list[str]:
    lines = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.startswith("#"):
                break
            lines.append(line.rstrip("\r\n"))
            if len(lines) >= HEADER_LINES:
                break
    return lines


def detect(path: Path) -> Detection | None:
    head = _head(path)
    is_23andme = COLUMN_LINE in head or any("23andme" in line.lower() for line in head)
    if not is_23andme:
        return None
    build = None
    for line in head:
        if "build" in line.lower():
            match = BUILD.search(line)
            if match:
                build = match[1]
                break
    return Detection(vendor="23andMe", format="23andme-tsv", build_from_header=build)


def load(con, path: Path) -> dict:
    """Create the ``calls`` table from ``path``. Returns load statistics.

    Raises ImportFailed if the file can't be read as 23andMe data or its build
    can't be confirmed as GRCh37.
    """
    try:
        con.execute(
            """
            CREATE TEMP TABLE raw AS
            SELECT * FROM read_csv(
                ?, delim = '\t', header = false, comment = '#', quote = '',
                escape = '', auto_detect = false, null_padding = true,
                columns = {
                    'probe_id': 'VARCHAR', 'chrom': 'VARCHAR',
                    'pos': 'VARCHAR', 'gt': 'VARCHAR'
                }
            )
            """,
            [str(path)],
        )
    except Exception as error:  # DuckDB raises several types; none carry data we show
        raise ImportFailed(
            "unreadable",
            "The file couldn't be read as 23andMe raw data "
            "(it should be tab-separated with 4 columns).",
        ) from error

    chroms = ", ".join(f"'{c}'" for c in CHROM_ORDER)
    total, invalid = con.execute(
        f"""
        SELECT count(*),
               count(*) FILTER (WHERE NOT (
                   probe_id IS NOT NULL AND probe_id <> ''
                   AND chrom IN ({chroms})
                   AND TRY_CAST(pos AS UINTEGER) IS NOT NULL
                   AND TRY_CAST(pos AS UINTEGER) > 0
                   AND regexp_full_match(gt, '([ACGTDI]{{1,2}}|--)')
               ))
        FROM raw
        """
    ).fetchone()
    if total == 0:
        raise ImportFailed("empty", "The file contains no genotype rows.")
    if invalid:
        raise ImportFailed(
            "invalid_rows",
            f"{invalid:,} of {total:,} rows aren't valid 23andMe calls, so the "
            "file wasn't imported. It may be damaged or edited.",
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
            f"{duplicate_ids:,} probe ids appear more than once, which 23andMe "
            "files never do. The file may be damaged or merged from two files.",
        )
    return {"rows": total}


def confirm_build(con, detection: Detection) -> dict:
    """Check the header's build claim against known GRCh37 positions."""
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
        "wasn't imported. 23andMe files normally state build 37 in the header.",
    )
