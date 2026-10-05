"""VCF and gVCF from sequencing services (single sample; the first sample
column is used).

* Genotypes (GT) become letters for single-base alleles. Calls failing the
  file's own FILTER, missing alleles (``.``) and symbolic alleles
  (``<NON_REF>``, ``*``) become no-calls. Multi-base (indel) calls are
  counted but not interpreted yet.
* gVCF reference blocks (``END=`` with a 0/0 genotype) are kept in a
  ``ref_blocks`` table: "tested, matches the reference". A position simply
  missing from a VCF is never assumed to be reference.
* Build comes from the header's contig lengths (or reference line). GRCh38
  files are converted to GRCh37 with the UCSC chain, which the caller makes
  available as ``r.liftover_chain``; positions that don't convert are
  dropped and counted, and alleles on reverse-strand chain blocks are
  complemented.
"""

import gzip
import re
from pathlib import Path

from yougene.importers import arrays
from yougene.importers.base import Detection, ImportFailed

CHR1_LENGTH = {249_250_621: "37", 248_956_422: "38"}
# hg19's chrM is the Yoruba sequence (NC_001807), not rCRS (16,569 bases) as
# in GRCh37's MT and GRCh38's chrM; its positions don't line up with ours.
YORUBA_CHRM_LENGTH = 16_571
GZIP_MAGIC = bytes([0x1F, 0x8B])
SYMBOLIC = "(<[^>]*>|\\*)"


def _open(path: Path):
    with path.open("rb") as handle:
        magic = handle.read(2)
    if magic == GZIP_MAGIC:
        return gzip.open(path, "rt", encoding="utf-8", errors="replace"), True
    return path.open("r", encoding="utf-8", errors="replace"), False


def read_header(path: Path) -> dict:
    handle, compressed = _open(path)
    lines = []
    with handle:
        for line in handle:
            if not line.startswith("#"):
                break
            lines.append(line.rstrip("\r\n"))
            if line.startswith("#CHROM"):
                break
    build = None
    for line in lines:
        match = re.match(r"##contig=<ID=(?:chr)?1,length=(\d+)", line)
        if match:
            build = CHR1_LENGTH.get(int(match[1]))
            break
    if build is None:
        reference = next(
            (ln for ln in lines if ln.startswith("##reference")), ""
        ).lower()
        if any(k in reference for k in ("grch38", "hg38")):
            build = "38"
        elif any(k in reference for k in ("grch37", "hg19", "b37", "hs37")):
            build = "37"
    columns = lines[-1].split("\t") if lines and lines[-1].startswith("#CHROM") else []
    yoruba_mt = any(
        re.match(rf"##contig=<ID=(?:chr)?(?:M|MT),length={YORUBA_CHRM_LENGTH}\b", ln)
        for ln in lines
    )
    return {
        "yoruba_mt": yoruba_mt,
        "is_vcf": bool(lines) and lines[0].startswith("##fileformat=VCF"),
        "build": build,
        "samples": columns[9:],
        "compressed": compressed,
    }


def detect(path: Path) -> Detection | None:
    header = read_header(path)
    if not header["is_vcf"]:
        return None
    if not header["samples"]:
        raise ImportFailed("no_sample", "This VCF has no sample column to import.")
    notes = []
    if len(header["samples"]) > 1:
        notes.append(
            f"{len(header['samples'])} samples in the file; the first was used."
        )
    if header["yoruba_mt"]:
        notes.append(
            "Mitochondrial calls use hg19's older chrM sequence rather than rCRS, "
            "so they weren't imported."
        )
    return Detection(
        vendor="VCF", format="vcf", build_from_header=header["build"], notes=notes
    )


def load(con, path: Path) -> dict:
    header = read_header(path)
    if header["build"] not in ("37", "38"):
        raise ImportFailed(
            "unknown_build",
            "YouGene couldn't tell which genome build this VCF uses (its header "
            "has no contig lengths or reference name).",
        )
    names = [
        "chrom",
        "pos",
        "id",
        "ref",
        "alt",
        "qual",
        "filter",
        "info",
        "format",
        "sample",
    ]
    columns = ", ".join(f"'{n}': 'VARCHAR'" for n in names)
    compression = "'gzip'" if header["compressed"] else "'none'"
    try:
        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE vcf_in AS
            SELECT * FROM read_csv(
                ?, delim = '\t', header = false, quote = '', escape = '',
                auto_detect = false, null_padding = true, strict_mode = false,
                compression = {compression}, columns = {{{columns}}}
            )
            WHERE NOT starts_with(chrom, '#')
            """,
            [str(path)],
        )
    except Exception as error:  # DuckDB raises several types; none carry data we show
        raise ImportFailed("unreadable", "The VCF couldn't be read.") from error

    codes = " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in arrays.CHROM_CODES.items())
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE vcf AS
        WITH base AS (
            SELECT
                CASE upper(regexp_replace(chrom, '^chr', '', 'i')) {codes} END AS chrom,
                TRY_CAST(pos AS UBIGINT) AS pos,
                id, upper(ref) AS ref, upper(alt) AS alt, filter, info,
                CASE WHEN starts_with(format, 'GT')
                     THEN split_part(sample, ':', 1) END AS gt
            FROM vcf_in
        )
        SELECT *,
            list_concat([ref], string_split(alt, ',')) AS allele_list,
            regexp_split_to_array(gt, '[/|]') AS idx,
            TRY_CAST(regexp_extract(info, '(?:^|;)END=(\\d+)', 1) AS UBIGINT) AS block_end
        FROM base
        """
    )
    con.execute("DROP TABLE vcf_in")

    # gVCF reference blocks: tested, homozygous reference over [pos, END].
    con.execute(
        f"""
        CREATE TABLE ref_blocks AS
        SELECT chrom, pos AS "start", block_end AS "end"
        FROM vcf
        WHERE block_end IS NOT NULL AND chrom IS NOT NULL
          AND list_bool_and(list_transform(idx, i -> i = '0'))
          AND regexp_full_match(alt, '({SYMBOLIC}|\\.)(,{SYMBOLIC})*')
        """
    )
    stats = dict(
        zip(
            ["records", "ref_blocks", "indels", "filtered"],
            con.execute(
                f"""
                SELECT count(*),
                       count(*) FILTER (WHERE block_end IS NOT NULL
                           AND regexp_full_match(alt, '({SYMBOLIC}|\\.)(,{SYMBOLIC})*')),
                       count(*) FILTER (WHERE length(ref) > 1 OR list_bool_or(
                           list_transform(string_split(alt, ','),
                               a -> length(a) > 1 AND NOT regexp_full_match(a, '{SYMBOLIC}')))),
                       count(*) FILTER (WHERE filter NOT IN ('PASS', '.'))
                FROM vcf
                """
            ).fetchone(),
            strict=True,
        )
    )

    # One genotype string per single-base site (letters, or '--').
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE raw AS
        WITH sites AS (
            SELECT * FROM vcf
            WHERE length(ref) = 1 AND ref IN ('A', 'C', 'G', 'T')
              AND NOT (block_end IS NOT NULL
                       AND regexp_full_match(alt, '({SYMBOLIC}|\\.)(,{SYMBOLIC})*'))
              AND list_bool_and(list_transform(string_split(alt, ','),
                  a -> length(a) = 1 OR regexp_full_match(a, '{SYMBOLIC}')))
        ),
        called AS (
            SELECT chrom, pos, id,
                list_transform(idx, i -> CASE WHEN i = '.' THEN NULL
                    ELSE allele_list[TRY_CAST(i AS INTEGER) + 1] END) AS letters,
                filter
            FROM sites
        )
        SELECT
            CASE WHEN id LIKE 'rs%' THEN split_part(id, ';', 1)
                 ELSE chrom || ':' || pos END AS probe_id,
            chrom, chrom AS chrom_in, CAST(pos AS VARCHAR) AS pos,
            CASE
                WHEN filter NOT IN ('PASS', '.') THEN '--'
                WHEN letters IS NULL OR len(letters) = 0 THEN '--'
                WHEN list_bool_or(list_transform(letters,
                    x -> x IS NULL OR NOT regexp_full_match(x, '[ACGT]'))) THEN '--'
                ELSE array_to_string(letters, '')
            END AS gt
        FROM called
        """
    )
    # Probe ids must be unique: repeat rsids (split multi-allelic records) get
    # their position appended.
    con.execute(
        """
        UPDATE raw SET probe_id = probe_id || '@' || chrom || ':' || pos
        WHERE probe_id IN (SELECT probe_id FROM raw GROUP BY probe_id HAVING count(*) > 1)
        """
    )
    if header["yoruba_mt"]:
        stats["mt_dropped"] = con.execute(
            "SELECT count(*) FROM raw WHERE chrom = 'MT'"
        ).fetchone()[0]
        con.execute("DELETE FROM raw WHERE chrom = 'MT'")
        con.execute("DELETE FROM ref_blocks WHERE chrom = 'MT'")
    if header["build"] == "38":
        stats.update(_lift(con))
    stats.update(arrays.build_calls(con, "VCF"))
    con.execute("DROP TABLE vcf")
    return stats


def _lift(con) -> dict:
    """Convert raw (and ref_blocks) from GRCh38 to GRCh37 with r.liftover_chain."""
    try:
        con.execute("SELECT 1 FROM r.liftover_chain LIMIT 1")
    except Exception as error:
        raise ImportFailed(
            "needs_liftover",
            "This VCF uses GRCh38. YouGene needs the GRCh38-to-GRCh37 conversion "
            "data to read it.",
        ) from error
    before = con.execute("SELECT count(*) FROM raw").fetchone()[0]
    # GRCh38's chrM is rCRS, as is GRCh37's MT: same positions, no lifting.
    # (The UCSC chain maps it to hg19's Yoruba chrM instead.)
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE raw AS
        SELECT probe_id, chrom, chrom_in, pos, gt FROM raw WHERE chrom = 'MT'
        UNION ALL
        SELECT x.probe_id, c.q_chrom AS chrom, x.chrom_in,
               CAST(CASE WHEN c.q_strand = '+'
                    THEN c.q_first + (CAST(x.pos AS UBIGINT) - 1 - c.t_start)
                    ELSE c.q_first - (CAST(x.pos AS UBIGINT) - 1 - c.t_start)
               END + 1 AS VARCHAR) AS pos,
               CASE WHEN c.q_strand = '+' OR x.gt = '--' THEN x.gt
                    ELSE translate(x.gt, 'ACGT', 'TGCA') END AS gt
        FROM raw x
        JOIN r.liftover_chain c
          ON c.t_chrom = x.chrom
         AND CAST(x.pos AS UBIGINT) - 1 >= c.t_start
         AND CAST(x.pos AS UBIGINT) - 1 < c.t_end
        WHERE x.chrom <> 'MT'
        """
    )
    after = con.execute("SELECT count(*) FROM raw").fetchone()[0]
    # Reference blocks would need splitting across chain gaps; dropped for
    # GRCh38 input rather than converted approximately (MT's need no change).
    con.execute("DELETE FROM ref_blocks WHERE chrom <> 'MT'")
    return {"lifted_from": "GRCh38", "unmapped_after_liftover": before - after}


def confirm_build(con, detection: Detection) -> dict:
    """VCF build comes from the header; GRCh38 input has been converted by
    ``load``. Any anchor SNPs present must sit at their GRCh37 positions."""
    lifted = detection.build_from_header == "38"
    result = arrays.confirm_build(
        con, Detection(detection.vendor, detection.format, "37", detection.notes)
    )
    return {
        **result,
        "header": detection.build_from_header,
        "lifted_from_grch38": lifted,
    }
