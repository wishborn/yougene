"""GRCh37 reference facts shared by importers and analysis."""

CHROMS = [str(i) for i in range(1, 23)] + ["X", "Y", "MT"]
CHROM_ORDER = {chrom: index + 1 for index, chrom in enumerate(CHROMS)}
AUTOSOMES = CHROMS[:22]

# Pseudo-autosomal regions on X (GRCh37, 1-based, inclusive):
# PAR1 = X:60001-2699520, PAR2 = X:154931044-155260560.
PAR1_END = 2_699_520
PAR2_START = 154_931_044

# Public, well-characterised SNPs with stable GRCh37 positions. Used only to
# confirm a file's genome build; never as annotations.
BUILD_ANCHORS_37 = {
    "rs429358": ("19", 45_411_941),
    "rs7412": ("19", 45_412_079),
    "rs4988235": ("2", 136_608_646),
    "rs12913832": ("15", 28_365_618),
    "rs4244285": ("10", 96_541_616),
}


def x_non_par_sql(pos: str = "pos") -> str:
    """SQL predicate for X positions outside both pseudo-autosomal regions."""
    return f"({pos} > {PAR1_END} AND {pos} < {PAR2_START})"
