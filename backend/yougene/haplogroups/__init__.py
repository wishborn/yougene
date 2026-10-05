"""Maternal (mtDNA) and paternal (Y) haplogroups for a sample."""

from yougene.haplogroups import mt, y

# Single-copy calls only: one letter, or two identical letters.
SINGLE = """
    SELECT pos, alleles[1] AS base
    FROM calls
    WHERE chrom = ? AND call_type = 'snp' AND NOT dup_conflict
      AND (length(alleles) = 1 OR (length(alleles) = 2 AND alleles[1] = alleles[2]))
"""


def _calls(con, chrom: str) -> dict[int, str]:
    return {pos: base for pos, base in con.execute(SINGLE, [chrom]).fetchall()}


def _ref_blocks(con, chrom: str) -> list[tuple[int, int]]:
    try:
        return con.execute(
            'SELECT "start", "end" FROM ref_blocks WHERE chrom = ?', [chrom]
        ).fetchall()
    except Exception:  # array samples have no ref_blocks table
        return []


def for_sample(con, vendor: str, sex: str) -> dict:
    return {
        "maternal": maternal(con, vendor),
        "paternal": paternal(con, sex),
        "sources": sources(),
    }


def maternal(con, vendor: str) -> dict:
    calls = _calls(con, "MT")
    if not calls:
        return {"status": "no_data"}
    rcrs = mt.tree().rcrs
    assumed = False
    if vendor == "VCF":
        blocks = _ref_blocks(con, "MT")
        for start, end in blocks:
            for pos in range(max(1, start), min(end, len(rcrs)) + 1):
                calls.setdefault(pos, rcrs[pos - 1])
        if not blocks:
            # A plain VCF lists only differences. As haplogrep does for
            # sequencing data, positions it doesn't list are taken as rCRS.
            assumed = True
            for pos in range(1, len(rcrs) + 1):
                calls.setdefault(pos, rcrs[pos - 1])
    return {**mt.classify(calls), "assumed_reference": assumed}


def paternal(con, sex: str) -> dict:
    if sex == "XX":
        return {"status": "no_y"}
    if sex != "XY":
        return {"status": "sex_unknown"}
    # Listed calls only: a VCF's reference blocks give the GRCh37 base, which
    # isn't always yhaplo's ancestral allele.
    calls = _calls(con, "Y")
    if not calls:
        return {"status": "no_data"}
    return y.classify(calls)


def sources() -> dict:
    return {
        "maternal": {
            "tree": mt.tree().source,
            "method": "Likelihood over every haplogroup in the tree, using only "
            "tested positions; the most specific branch with at least 99% "
            "probability and a tested defining mutation.",
        },
        "paternal": {
            "tool": "yhaplo (23andMe, Inc.)",
            "url": "https://github.com/23andMe/yhaplo",
            "tree": "ISOGG Y-DNA tree, 2016-01-04",
            "licence": "Non-commercial use. The Yhaplo software was developed "
            "by 23andMe, Inc.",
        },
    }
