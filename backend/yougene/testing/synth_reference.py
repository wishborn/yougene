"""Invented ClinVar / GWAS Catalog / cytoBand files lined up with a synthetic
sample, for browser smoke tests and demos. Nothing here is real reference data.

    python -m yougene.testing.synth_reference --sample male.txt -o OUTDIR
    yougene refdata install --file clinvar=OUTDIR/clinvar.vcf.gz \\
        --file gwas=OUTDIR/gwas.zip --file cytoband=OUTDIR/cytoBand.txt.gz
"""

import argparse
import gzip
import random
import zipfile
from pathlib import Path

from yougene.testing.synth import CHROMS, LENGTHS

GWAS_COLUMNS = [
    "DATE ADDED TO CATALOG", "PUBMEDID", "FIRST AUTHOR", "DATE", "JOURNAL", "LINK",
    "STUDY", "DISEASE/TRAIT", "INITIAL SAMPLE SIZE", "REPLICATION SAMPLE SIZE",
    "REGION", "CHR_ID", "CHR_POS", "REPORTED GENE(S)", "MAPPED_GENE",
    "UPSTREAM_GENE_ID", "DOWNSTREAM_GENE_ID", "SNP_GENE_IDS",
    "UPSTREAM_GENE_DISTANCE", "DOWNSTREAM_GENE_DISTANCE",
    "STRONGEST SNP-RISK ALLELE", "SNPS", "MERGED", "SNP_ID_CURRENT", "CONTEXT",
    "INTERGENIC", "RISK ALLELE FREQUENCY", "P-VALUE", "PVALUE_MLOG",
    "P-VALUE (TEXT)", "OR or BETA", "95% CI (TEXT)",
    "PLATFORM [SNPS PASSING QC]", "CNV", "MAPPED_TRAIT", "MAPPED_TRAIT_URI",
    "STUDY ACCESSION", "GENOTYPING TECHNOLOGY",
]  # fmt: skip
SIGS = [
    ("Pathogenic", "reviewed_by_expert_panel"),
    ("Likely_pathogenic", "criteria_provided,_multiple_submitters,_no_conflicts"),
    ("Uncertain_significance", "criteria_provided,_single_submitter"),
    ("Benign", "criteria_provided,_multiple_submitters,_no_conflicts"),
    ("drug_response", "practice_guideline"),
    ("risk_factor", "no_assertion_criteria_provided"),
]
TRAITS = ["invented trait A", "invented trait B", "invented height-like trait",
          "invented metabolic trait"]  # fmt: skip


def read_calls(path: Path) -> list[tuple[str, str, int, str]]:
    calls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        probe, chrom, pos, gt = line.split("\t")
        if gt != "--" and not set(gt) & {"D", "I"}:
            calls.append((probe, chrom, int(pos), gt))
    return calls


def write(sample: Path, out: Path, seed: int = 11, records: int = 120) -> dict:
    rng = random.Random(seed)
    calls = read_calls(sample)
    picked = rng.sample(calls, min(records, len(calls)))
    out.mkdir(parents=True, exist_ok=True)

    lines = ["##fileformat=VCFv4.1", "##source=YouGene synthetic reference",
             "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"]  # fmt: skip
    for index, (probe, chrom, pos, gt) in enumerate(picked):
        other = rng.choice([b for b in "ACGT" if b not in gt])
        carried = index % 2 == 0
        alt = gt[-1] if carried else other
        ref = gt[0] if carried and gt[0] != alt else other if carried else gt[0]
        if ref == alt:
            ref = other
        sig, rev = SIGS[index % len(SIGS)]
        rs = probe[2:] if probe.startswith("rs") else ""
        gene = "APOE:348" if index == 0 else f"GENE{index}:{1000 + index}"
        info = (
            f"ALLELEID={index + 1};CLNSIG={sig};CLNREVSTAT={rev};"
            f"CLNDN=Invented_condition_{index}|not_provided;GENEINFO={gene};"
            f"MC=SO:0001583|missense_variant;ORIGIN=1"
            + (f";RS={rs}" if rs else "")
            + (";AF_EXAC=0.2" if index % 3 else "")
        )
        lines.append(f"{chrom}\t{pos}\t{900000 + index}\t{ref}\t{alt}\t.\t.\t{info}")
    with gzip.open(out / "clinvar.vcf.gz", "wt") as handle:
        handle.write("\n".join(lines) + "\n")

    rows = []
    for index, (probe, _chrom, _pos, gt) in enumerate(
        c for c in picked if c[0].startswith("rs")
    ):
        row = dict.fromkeys(GWAS_COLUMNS, "")
        risk = gt[index % len(gt)]
        row.update({
            "PUBMEDID": str(10000000 + index), "FIRST AUTHOR": "Example A",
            "DATE": "2020-05-01", "STUDY": "Invented study for testing",
            "DISEASE/TRAIT": TRAITS[index % len(TRAITS)],
            "MAPPED_TRAIT": TRAITS[index % len(TRAITS)],
            "INITIAL SAMPLE SIZE": "10,000 European ancestry individuals",
            "STRONGEST SNP-RISK ALLELE": f"{probe}-{risk}", "SNPS": probe,
            "SNP_ID_CURRENT": probe[2:], "RISK ALLELE FREQUENCY": "0.3",
            "PVALUE_MLOG": str(6 + index % 10), "P-VALUE": f"1E-{6 + index % 10}",
            "OR or BETA": "1.15" if index % 2 else "0.05",
            "95% CI (TEXT)": "[1.05-1.25]" if index % 2 else "[0.02-0.08] increase",
            "STUDY ACCESSION": f"GCST9{index:05}",
        })  # fmt: skip
        rows.append("\t".join(row[c] for c in GWAS_COLUMNS))
    with zipfile.ZipFile(out / "gwas.zip", "w") as archive:
        archive.writestr(
            "associations.tsv", "\t".join(GWAS_COLUMNS) + "\n" + "\n".join(rows) + "\n"
        )

    bands = []
    for chrom, length in zip(CHROMS, LENGTHS, strict=True):
        name = "chrM" if chrom == "MT" else f"chr{chrom}"
        step = max(length // 8, 1)
        for i in range(8):
            start, end = i * step, length if i == 7 else (i + 1) * step
            stain = "acen" if i == 3 else ("gneg" if i % 2 else "gpos50")
            bands.append(
                f"{name}\t{start}\t{end}\t{'p' if i < 4 else 'q'}{i + 1}\t{stain}"
            )
    with gzip.open(out / "cytoBand.txt.gz", "wt") as handle:
        handle.write("\n".join(bands) + "\n")
    return {"clinvar": len(lines) - 3, "gwas": len(rows), "bands": len(bands)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()
    print(write(args.sample, args.output, args.seed))


if __name__ == "__main__":
    main()
