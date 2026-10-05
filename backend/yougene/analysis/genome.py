"""Genome-wide views computed from a sample's calls: density bins and runs of
homozygosity (ROH)."""

from yougene.genome import AUTOSOMES, CHROMS

# ROH detection, modelled on PLINK --homozyg defaults, adapted to array data:
# a run is a stretch of homozygous SNP calls at least MIN_KB long with at least
# MIN_SNPS calls, allowing a few heterozygous calls (genotyping errors) and
# breaking where the gap between neighbouring probes exceeds MAX_GAP_KB.
ROH_MIN_KB = 1000
ROH_MIN_SNPS = 100
ROH_MAX_HET = 1  # tolerated heterozygous calls per run
ROH_MAX_GAP_KB = 1000
# GRCh37 autosome length (sum of chr1-22), for the share of genome in ROH.
AUTOSOME_BP = 2_881_033_286


def density_bins(con, bin_bp: int) -> dict[str, list[dict]]:
    rows = con.execute(
        """
        SELECT chrom, chrom_order, (pos // ?)::UINTEGER AS bin,
               count(*) AS probes,
               count(*) FILTER (WHERE call_type = 'nocall') AS nocalls,
               count(*) FILTER (WHERE call_type = 'snp' AND ploidy = 2
                                AND alleles[1] <> alleles[2]) AS het,
               count(*) FILTER (WHERE call_type = 'snp' AND ploidy = 2) AS diploid
        FROM calls
        GROUP BY chrom, chrom_order, bin
        ORDER BY chrom_order, bin
        """,
        [bin_bp],
    ).fetchall()
    out: dict[str, list[dict]] = {c: [] for c in CHROMS}
    for chrom, _order, index, probes, nocalls, het, diploid in rows:
        out[chrom].append(
            {
                "start": index * bin_bp,
                "probes": probes,
                "nocalls": nocalls,
                "het_rate": round(het / diploid, 4) if diploid else None,
            }
        )
    return out


def runs_of_homozygosity(con) -> dict:
    segments = []
    for chrom in AUTOSOMES:
        rows = con.execute(
            "SELECT pos, alleles[1] = alleles[2] FROM calls "
            "WHERE chrom = ? AND call_type = 'snp' AND ploidy = 2 ORDER BY pos",
            [chrom],
        ).fetchall()
        segments += _scan(chrom, rows)
    total_bp = sum(s["end"] - s["start"] for s in segments)
    return {
        "segments": segments,
        "total_mb": round(total_bp / 1e6, 1),
        "fraction_of_autosomes": round(total_bp / AUTOSOME_BP, 4),
        "params": {
            "min_kb": ROH_MIN_KB,
            "min_snps": ROH_MIN_SNPS,
            "max_het": ROH_MAX_HET,
            "max_gap_kb": ROH_MAX_GAP_KB,
        },
    }


def _scan(chrom: str, rows: list[tuple[int, bool]]) -> list[dict]:
    found = []
    start = last = None
    snps = hets = 0

    def close():
        if start is not None and snps >= ROH_MIN_SNPS:
            if (last - start) >= ROH_MIN_KB * 1000:
                found.append(
                    {"chrom": chrom, "start": start, "end": last, "snps": snps}
                )

    for pos, homozygous in rows:
        if start is not None and pos - last > ROH_MAX_GAP_KB * 1000:
            close()
            start, snps, hets = None, 0, 0
        if homozygous:
            if start is None:
                start, snps, hets = pos, 0, 0
            snps += 1
            last = pos
        elif start is not None:
            hets += 1
            if hets > ROH_MAX_HET:
                close()
                start, snps, hets = None, 0, 0
    close()
    return found
