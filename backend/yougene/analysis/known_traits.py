"""A small, curated set of well-known single-SNP traits.

Each entry was checked on 2026-10-04 against:
- Ensembl GRCh37 (grch37.rest.ensembl.org/variation/human/<rsid>): position
  and plus-strand alleles;
- the ClinVar record named in ``clinvar_vcv``, whose REF/ALT (plus strand)
  identify which allele carries the trait.

Genotypes are plus-strand GRCh37, as 23andMe reports them. A call whose letters
aren't the two expected alleles is reported as unexpected, never guessed.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class KnownTrait:
    id: str
    title: str
    rsid: str
    chrom: str
    pos: int
    gene: str
    effect_allele: str
    other_allele: str
    outcomes: dict[int, str]  # copies of effect_allele -> plain-language result
    caveat: str
    clinvar_vcv: int


KNOWN_TRAITS = [
    KnownTrait(
        id="lactase",
        title="Digesting milk as an adult (lactase persistence)",
        rsid="rs4988235",
        chrom="2",
        pos=136_608_646,
        gene="MCM6 (LCT enhancer)",
        effect_allele="A",
        other_allele="G",
        outcomes={
            2: "Two copies of the lactase-persistence allele: very likely to keep "
            "digesting lactose as an adult.",
            1: "One copy of the lactase-persistence allele: usually enough to keep "
            "digesting lactose as an adult.",
            0: "No copies of this lactase-persistence allele: lactase activity often "
            "falls after childhood, unless another persistence variant is present.",
        },
        caveat="This variant explains most lactase persistence in people of European "
        "ancestry. Other populations have different persistence variants that this "
        "file may not test, so having no copies here doesn't prove intolerance.",
        clinvar_vcv=7685,
    ),
    KnownTrait(
        id="eye_colour",
        title="Blue or brown eyes (HERC2/OCA2)",
        rsid="rs12913832",
        chrom="15",
        pos=28_365_618,
        gene="HERC2",
        effect_allele="G",
        other_allele="A",
        outcomes={
            2: "Two copies of the allele linked to blue eyes: blue or other light "
            "eye colour is likely.",
            1: "One copy of the blue-eye-linked allele: brown or intermediate eye "
            "colour is more likely than blue.",
            0: "No copies of the blue-eye-linked allele: brown eyes are likely.",
        },
        caveat="This single SNP is the strongest known eye-colour signal in people of "
        "European ancestry, but other genes also contribute, so it's a likelihood, "
        "not a certainty.",
        clinvar_vcv=4745,
    ),
    KnownTrait(
        id="earwax",
        title="Earwax type (ABCC11)",
        rsid="rs17822931",
        chrom="16",
        pos=48_258_198,
        gene="ABCC11",
        effect_allele="T",
        other_allele="C",
        outcomes={
            2: "Two copies of the dry-earwax allele: dry, flaky earwax and less "
            "underarm odour are expected.",
            1: "One copy of the dry-earwax allele: wet earwax is expected (the dry "
            "type needs two copies).",
            0: "No copies of the dry-earwax allele: wet earwax is expected.",
        },
        caveat="Dry earwax is common in East Asian ancestry and uncommon elsewhere.",
        clinvar_vcv=3558,
    ),
    KnownTrait(
        id="alcohol_flush",
        title="Alcohol flush reaction (ALDH2)",
        rsid="rs671",
        chrom="12",
        pos=112_241_766,
        gene="ALDH2",
        effect_allele="A",
        other_allele="G",
        outcomes={
            2: "Two copies of the reduced-function ALDH2 allele: alcohol typically "
            "causes strong flushing and discomfort.",
            1: "One copy of the reduced-function ALDH2 allele: facial flushing after "
            "alcohol is common. Drinking with this genotype is linked to a higher risk "
            "of oesophageal cancer.",
            0: "No copies of the reduced-function ALDH2 allele: no flushing from this "
            "gene.",
        },
        caveat="The reduced-function allele is common in East Asian ancestry and rare "
        "elsewhere.",
        clinvar_vcv=18390,
    ),
    KnownTrait(
        id="actn3",
        title="Fast-twitch muscle protein (ACTN3 R577X)",
        rsid="rs1815739",
        chrom="11",
        pos=66_328_095,
        gene="ACTN3",
        effect_allele="T",
        other_allele="C",
        outcomes={
            2: "Two copies of the 577X allele: no alpha-actinin-3 in fast-twitch "
            "muscle fibres. This is common and harmless; it's slightly more frequent "
            "among endurance athletes than sprinters.",
            1: "One copy of the 577X allele: alpha-actinin-3 is still made.",
            0: "No copies of the 577X allele: alpha-actinin-3 is made normally; this "
            "genotype is slightly more frequent among sprint and power athletes.",
        },
        caveat="Effects on athletic performance are small and don't predict ability. "
        "The GRCh37 reference genome itself carries the 577X (T) allele.",
        clinvar_vcv=18312,
    ),
    KnownTrait(
        id="secretor",
        title="Secretor status (FUT2)",
        rsid="rs601338",
        chrom="19",
        pos=49_206_674,
        gene="FUT2",
        effect_allele="A",
        other_allele="G",
        outcomes={
            2: "Two copies of the non-secretor allele: blood-group antigens aren't "
            "secreted into saliva and gut. Non-secretors resist some norovirus strains "
            "and tend to have higher vitamin B12 levels.",
            1: "One copy of the non-secretor allele: still a secretor.",
            0: "No copies of the non-secretor allele: a secretor.",
        },
        caveat="This variant defines non-secretors mainly in European and African "
        "ancestry; in East Asian ancestry a different FUT2 variant is more common.",
        clinvar_vcv=12945,
    ),
]


def evaluate(con) -> list[dict]:
    """Look up each curated SNP in a sample's calls (by position, so a renamed
    probe still counts) and interpret it."""
    results = []
    for trait in KNOWN_TRAITS:
        rows = con.execute(
            "SELECT probe_id, alleles, ploidy, call_type, dup_conflict FROM calls "
            "WHERE chrom = ? AND pos = ?",
            [trait.chrom, trait.pos],
        ).fetchall()
        base = {
            "id": trait.id,
            "title": trait.title,
            "rsid": trait.rsid,
            "gene": trait.gene,
            "effect_allele": trait.effect_allele,
            "other_allele": trait.other_allele,
            "caveat": trait.caveat,
            "clinvar_vcv": trait.clinvar_vcv,
        }
        called = [r for r in rows if r[3] == "snp"]
        if not rows:
            results.append({**base, "status": "not_tested", "summary": None})
            continue
        if not called:
            results.append({**base, "status": "no_call", "summary": None})
            continue
        genotypes = {r[1] for r in called}
        if len(genotypes) > 1 or any(r[4] for r in called):
            results.append({**base, "status": "conflicting", "summary": None})
            continue
        alleles = called[0][1]
        expected = {trait.effect_allele, trait.other_allele}
        if not set(alleles) <= expected or called[0][2] != 2:
            results.append(
                {**base, "status": "unexpected", "genotype": alleles, "summary": None}
            )
            continue
        copies = alleles.count(trait.effect_allele)
        results.append(
            {
                **base,
                "status": "ok",
                "genotype": alleles,
                "copies": copies,
                "summary": trait.outcomes[copies],
            }
        )
    return results
