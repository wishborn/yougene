"""Curated pharmacogenomic (PGx) rules for genes an array can partly call.

Every defining variant was checked on 2026-10-04 against the ClinVar record
named (plus-strand REF/ALT, GRCh37) and the gene's known direction; reverse-
strand genes (VKORC1, DPYD, TPMT, CYP3A5) are expressed here on the plus
strand. Phenotype rules follow CPIC's allele-function and phenotype tables.

Arrays test only a few defining positions per gene and can't phase or see
copy number, so every result is partial and CYP2D6 is deliberately absent.
A result is only given when every defining position was read; otherwise the
gene is "not determined". This is information to discuss with a clinician,
never dosing advice.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Variant:
    rsid: str
    chrom: str
    pos: int
    normal: str  # plus-strand allele of the reference (*1) haplotype
    variant: str  # plus-strand allele defining the star allele
    star: str
    function: str  # "no", "decreased", "increased"
    clinvar_vcv: int


@dataclass(frozen=True)
class Gene:
    gene: str
    variants: tuple[Variant, ...]
    drugs: tuple[str, ...]
    rule: str  # name of the phenotype rule below
    note: str = ""
    untested: tuple[str, ...] = field(default=())


GENES = (
    Gene(
        "CYP2C19",
        (
            Variant("rs4244285", "10", 96_541_616, "G", "A", "*2", "no", 16897),
            Variant("rs4986893", "10", 96_540_410, "G", "A", "*3", "no", 16899),
            Variant(
                "rs12248560", "10", 96_521_657, "C", "T", "*17", "increased", 39357
            ),
        ),
        drugs=(
            "clopidogrel",
            "voriconazole",
            "omeprazole and other PPIs",
            "citalopram, escitalopram, sertraline",
            "amitriptyline",
        ),  # fmt: skip
        rule="cyp2c19",
        untested=("*4", "*5", "*6", "*7", "*8", "*35"),
    ),
    Gene(
        "CYP2C9",
        (
            Variant("rs1799853", "10", 96_702_047, "C", "T", "*2", "decreased", 8409),
            Variant("rs1057910", "10", 96_741_053, "A", "C", "*3", "no", 8408),
        ),
        drugs=(
            "warfarin (with VKORC1)",
            "phenytoin",
            "celecoxib, ibuprofen and other NSAIDs",
            "siponimod",
        ),  # fmt: skip
        rule="activity",
        untested=("*5", "*6", "*8", "*11"),
    ),
    Gene(
        "VKORC1",
        (
            Variant(
                "rs9923231", "16", 31_107_689, "C", "T", "-1639A", "sensitivity", 2211
            ),
        ),
        drugs=("warfarin",),
        rule="vkorc1",
    ),
    Gene(
        "SLCO1B1",
        (
            Variant(
                "rs4149056", "12", 21_331_549, "T", "C", "c.521C", "decreased", 37346
            ),
        ),
        drugs=("simvastatin", "atorvastatin, rosuvastatin and other statins"),
        rule="slco1b1",
        note="CPIC assigns SLCO1B1 function from this one position when others aren't "
        "tested.",
    ),
    Gene(
        "DPYD",
        (
            Variant("rs3918290", "1", 97_915_614, "C", "T", "*2A", "no", 432),
            Variant("rs55886062", "1", 97_981_343, "A", "C", "*13", "no", 88975),
            Variant(
                "rs67376798", "1", 97_547_947, "T", "A", "c.2846A>T", "decreased", 88974
            ),
            Variant(
                "rs56038477", "1", 98_039_419, "C", "T", "HapB3", "decreased", 100100
            ),
        ),
        drugs=("fluorouracil (5-FU)", "capecitabine"),
        rule="activity",
        note="If two different DPYD variants are present they're assumed to be on "
        "different copies (the more cautious reading); arrays can't tell.",
        untested=("rare variants",),
    ),
    Gene(
        "TPMT",
        (
            Variant("rs1800462", "6", 18_143_955, "C", "G", "*2", "no", 12721),
            Variant("rs1800460", "6", 18_139_228, "C", "T", "*3B", "no", 37126),
            Variant("rs1142345", "6", 18_130_918, "T", "C", "*3C", "no", 12725),
        ),
        drugs=("azathioprine", "mercaptopurine", "thioguanine"),
        rule="tpmt",
        note="*3A is *3B and *3C on the same copy. One copy of each is read as one "
        "*3A (most likely); rarely they sit on different copies, which would mean "
        "poor function.",
        untested=("*4", "*8"),
    ),
    Gene(
        "NUDT15",
        (Variant("rs116855232", "13", 48_619_855, "C", "T", "*3", "no", 225201),),
        drugs=("azathioprine", "mercaptopurine", "thioguanine"),
        rule="count",
        untested=("*2", "*4", "*5", "*6"),
    ),
    Gene(
        "CYP3A5",
        # The GRCh37 reference carries *3 (C); the functional *1 allele is T.
        (Variant("rs776746", "7", 99_270_539, "T", "C", "*3", "no", 226021),),
        drugs=("tacrolimus",),
        rule="count",
        note="Most people of European ancestry have two *3 copies (the usual, "
        "non-expressing state).",
        untested=("*6", "*7"),
    ),
)

PHENOTYPE_BY_NO_FUNCTION = {0: "Normal metabolizer", 1: "Intermediate metabolizer",
                            2: "Poor metabolizer"}  # fmt: skip
WEIGHT = {"no": 1.0, "decreased": 0.5}


def _phenotype(gene: Gene, copies: dict[str, int]) -> tuple[str, str]:
    """Return (phenotype, diplotype-ish description) from variant copy counts."""
    if gene.rule == "cyp2c19":
        no = copies["*2"] + copies["*3"]
        inc = copies["*17"]
        if no >= 2:
            return "Poor metabolizer", "two no-function alleles"
        if no == 1:
            return "Intermediate metabolizer", (
                "one no-function allele" + (" and one *17" if inc else "")
            )
        if inc == 2:
            return "Ultrarapid metabolizer", "*17/*17"
        if inc == 1:
            return "Rapid metabolizer", "*1/*17"
        return "Normal metabolizer", "*1/*1 at tested positions"
    if gene.rule == "activity":
        loss = sum(WEIGHT[v.function] * copies[v.star] for v in gene.variants)
        score = max(0.0, 2.0 - loss)
        if score >= 2:
            label = "Normal metabolizer"
        elif score >= 1:
            label = "Intermediate metabolizer"
        else:
            label = "Poor metabolizer"
        return label, f"activity score {score:g}"
    if gene.rule == "vkorc1":
        n = copies["-1639A"]
        return (
            [
                "Normal warfarin sensitivity",
                "Increased warfarin sensitivity",
                "Highly increased warfarin sensitivity",
            ][n],  # fmt: skip
            f"{n} copies of -1639A",
        )
    if gene.rule == "slco1b1":
        n = copies["c.521C"]
        return (["Normal function", "Decreased function", "Poor function"][n],
                f"{n} copies of c.521C")  # fmt: skip
    if gene.rule == "tpmt":
        b, c, two = copies["*3B"], copies["*3C"], copies["*2"]
        no = two + max(b, c)  # *3B with *3C on one copy counts once (*3A)
        return PHENOTYPE_BY_NO_FUNCTION[min(no, 2)], f"{no} no-function allele(s)"
    if gene.rule == "count":
        n = sum(copies[v.star] for v in gene.variants)
        return PHENOTYPE_BY_NO_FUNCTION[min(n, 2)], f"{n} no-function allele(s)"
    raise ValueError(gene.rule)


def evaluate(con) -> list[dict]:
    results = []
    for gene in GENES:
        positions, copies, problems = [], {}, []
        for v in gene.variants:
            rows = con.execute(
                "SELECT alleles, call_type, dup_conflict FROM calls "
                "WHERE chrom = ? AND pos = ?",
                [v.chrom, v.pos],
            ).fetchall()
            called = [r for r in rows if r[1] == "snp"]
            entry = {"rsid": v.rsid, "star": v.star, "function": v.function,
                     "clinvar_vcv": v.clinvar_vcv, "genotype": None}  # fmt: skip
            if not rows:
                entry["status"] = "not_tested"
            elif not called:
                entry["status"] = "no_call"
            elif len({r[0] for r in called}) > 1 or any(r[2] for r in called):
                entry["status"] = "conflicting"
            elif (
                not set(called[0][0]) <= {v.normal, v.variant} or len(called[0][0]) != 2
            ):
                entry["status"], entry["genotype"] = "unexpected", called[0][0]
            else:
                entry["status"], entry["genotype"] = "ok", called[0][0]
                copies[v.star] = called[0][0].count(v.variant)
            if entry["status"] != "ok":
                problems.append(entry["status"])
            positions.append(entry)
        result = {
            "gene": gene.gene,
            "drugs": list(gene.drugs),
            "note": gene.note,
            "untested_alleles": list(gene.untested),
            "positions": positions,
        }
        if problems:
            result.update(status="not_determined", phenotype=None, detail=None)
        else:
            phenotype, detail = _phenotype(gene, copies)
            result.update(status="ok", phenotype=phenotype, detail=detail)
        results.append(result)
    return results
