"""Public reference datasets YouGene can download, and where they come from.

The repository ships these definitions and the code that builds them; it never
ships the data itself.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    url: str
    filename: str
    license: str
    attribution: str
    approx_mb: int
    purpose: str


CLINVAR = Source(
    id="clinvar",
    title="ClinVar (GRCh37)",
    url="https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh37/clinvar.vcf.gz",
    filename="clinvar.vcf.gz",
    license="Public domain (NCBI). Cite ClinVar when sharing results.",
    attribution="Landrum MJ et al. ClinVar. NCBI, National Library of Medicine.",
    approx_mb=200,
    purpose="Clinical significance of variants, reviewed by submitters and experts.",
)

GWAS = Source(
    id="gwas",
    title="GWAS Catalog associations",
    url=(
        "https://ftp.ebi.ac.uk/pub/databases/gwas/releases/latest/"
        "gwas-catalog-associations_ontology-annotated-full.zip"
    ),
    filename="gwas-catalog-associations.zip",
    license=(
        "Mostly CC0; some studies carry other EMBL-EBI terms "
        "(see the catalog's usage license column)."
    ),
    attribution="NHGRI-EBI GWAS Catalog, EMBL-EBI.",
    approx_mb=75,
    purpose="Published associations between variants and traits.",
)

CYTOBAND = Source(
    id="cytoband",
    title="Chromosome bands (hg19)",
    url="https://hgdownload.soe.ucsc.edu/goldenPath/hg19/database/cytoBand.txt.gz",
    filename="cytoBand.hg19.txt.gz",
    license="UCSC Genome Browser data, free for use.",
    attribution="UCSC Genome Browser, hg19 cytoBand track.",
    approx_mb=1,
    purpose="Chromosome band layout for the chromosome explorer.",
)

LIFTOVER = Source(
    id="liftover",
    title="GRCh38 to GRCh37 conversion (UCSC chain)",
    url="https://hgdownload.soe.ucsc.edu/goldenPath/hg38/liftOver/hg38ToHg19.over.chain.gz",
    filename="hg38ToHg19.over.chain.gz",
    license="UCSC Genome Browser data, free for use.",
    attribution="UCSC Genome Browser liftOver chain hg38ToHg19.",
    approx_mb=2,
    purpose="Only needed to read sequencing (VCF) files aligned to GRCh38.",
)

SOURCES = {s.id: s for s in (CLINVAR, GWAS, CYTOBAND, LIFTOVER)}
