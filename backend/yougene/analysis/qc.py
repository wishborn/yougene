"""File-level quality numbers and sex inference, from the calls table alone."""

from yougene.genome import CHROMS, x_non_par_sql

# Thresholds for inferring sex from array data. Diploid X outside the
# pseudo-autosomal regions means two X chromosomes; haploid X plus called Y
# means XY. Anything in between is reported as unknown, never forced.
MIN_X_CALLS = 20
MIN_Y_PROBES = 20
XY_MAX_X_HET = 0.01
XY_MIN_Y_CALL_RATE = 0.5
XX_MIN_X_HET = 0.05
XX_MAX_Y_CALL_RATE = 0.1


def summarise(con) -> dict:
    (
        rows,
        rs_ids,
        vendor_ids,
        nocalls,
        indel_codes,
        snp_calls,
        dup_groups,
        dup_conflicts,
    ) = con.execute(
        """
        SELECT count(*),
               count(*) FILTER (WHERE id_kind = 'rs'),
               count(*) FILTER (WHERE id_kind = 'vendor'),
               count(*) FILTER (WHERE call_type = 'nocall'),
               count(*) FILTER (WHERE call_type = 'indel_code'),
               count(*) FILTER (WHERE call_type = 'snp'),
               count(DISTINCT dup_group),
               count(DISTINCT dup_group) FILTER (WHERE dup_conflict)
        FROM calls
        """
    ).fetchone()

    per_chrom = {
        chrom: {"probes": probes, "nocalls": missing}
        for chrom, probes, missing in con.execute(
            """
            SELECT chrom, count(*), count(*) FILTER (WHERE call_type = 'nocall')
            FROM calls GROUP BY chrom, chrom_order ORDER BY chrom_order
            """
        ).fetchall()
    }

    het_calls, diploid_snps = con.execute(
        """
        SELECT count(*) FILTER (WHERE alleles[1] <> alleles[2]), count(*)
        FROM calls
        WHERE call_type = 'snp' AND ploidy = 2 AND chrom_order <= 22
        """
    ).fetchone()

    return {
        "rows": rows,
        "rs_ids": rs_ids,
        "vendor_ids": vendor_ids,
        "nocalls": nocalls,
        "call_rate": round((rows - nocalls) / rows, 6) if rows else None,
        "snp_calls": snp_calls,
        "indel_codes": indel_codes,
        "duplicate_position_groups": dup_groups,
        "duplicate_position_conflicts": dup_conflicts,
        "autosomal_heterozygosity": (
            round(het_calls / diploid_snps, 6) if diploid_snps else None
        ),
        "per_chromosome": {
            c: per_chrom.get(c, {"probes": 0, "nocalls": 0}) for c in CHROMS
        },
        "sex": infer_sex(con),
    }


def infer_sex(con) -> dict:
    x_calls, x_haploid, x_het, y_probes, y_called = con.execute(
        f"""
        SELECT
            count(*) FILTER (WHERE chrom = 'X' AND call_type = 'snp'
                             AND {x_non_par_sql()}),
            count(*) FILTER (WHERE chrom = 'X' AND call_type = 'snp'
                             AND {x_non_par_sql()} AND ploidy = 1),
            count(*) FILTER (WHERE chrom = 'X' AND call_type = 'snp'
                             AND {x_non_par_sql()} AND ploidy = 2
                             AND alleles[1] <> alleles[2]),
            count(*) FILTER (WHERE chrom = 'Y'),
            count(*) FILTER (WHERE chrom = 'Y' AND call_type <> 'nocall')
        FROM calls
        """
    ).fetchone()
    x_het_rate = x_het / x_calls if x_calls else None
    y_call_rate = y_called / y_probes if y_probes else None
    evidence = {
        "x_non_par_calls": x_calls,
        "x_non_par_haploid_calls": x_haploid,
        "x_non_par_heterozygosity": round(x_het_rate, 6)
        if x_het_rate is not None
        else None,
        "y_probes": y_probes,
        "y_call_rate": round(y_call_rate, 6) if y_call_rate is not None else None,
    }
    if x_calls < MIN_X_CALLS or y_probes < MIN_Y_PROBES:
        return {"inferred": "unknown", "reason": "too few X or Y probes", **evidence}
    if x_het_rate <= XY_MAX_X_HET and y_call_rate >= XY_MIN_Y_CALL_RATE:
        return {"inferred": "XY", "reason": "haploid X and called Y", **evidence}
    if x_het_rate >= XX_MIN_X_HET and y_call_rate <= XX_MAX_Y_CALL_RATE:
        return {"inferred": "XX", "reason": "heterozygous X and no Y", **evidence}
    return {"inferred": "unknown", "reason": "X and Y signals disagree", **evidence}
