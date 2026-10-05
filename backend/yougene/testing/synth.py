"""Seeded, wholly invented 23andMe-style v5 exports on GRCh37 coordinates.

Only the five public anchor positions are actual SNP mappings. Other probe IDs
and positions are invented and must never be treated as reference annotations.
"""

import argparse
import json
import random
from pathlib import Path

MARKER = "# YOUGENE SYNTHETIC FIXTURE - not a real person"
CHROMS = [str(i) for i in range(1, 23)] + ["X", "Y", "MT"]
LENGTHS = [
    249250621,
    243199373,
    198022430,
    191154276,
    180915260,
    171115067,
    159138663,
    146364022,
    141213431,
    135534747,
    135006516,
    133851895,
    115169878,
    107349540,
    102531392,
    90354753,
    81195210,
    78077248,
    59128983,
    63025520,
    48129895,
    51304566,
    155270560,
    59373566,
    16569,
]
_WEIGHTS = LENGTHS[:-1] + [sum(LENGTHS[:-1]) * 0.003]
CUM_WEIGHTS = [sum(_WEIGHTS[: i + 1]) for i in range(len(_WEIGHTS))]
# Public GRCh37 facts: grch37.rest.ensembl.org/variation/human/<rsid>
# and ncbi.nlm.nih.gov/clinvar/RCV000018395.37/ (CYP2C19).
ANCHORS = [
    ("rs429358", "19", 45411941, "CT"),
    ("rs7412", "19", 45412079, "CC"),
    ("rs4988235", "2", 136608646, "AG"),
    ("rs12913832", "15", 28365618, "AG"),
    ("rs4244285", "10", 96541616, "AG"),
]


def is_x_par(position: int) -> bool:
    # GRCh37 PAR1 = X:60001-2699520, PAR2 = X:154931044-155260560.
    return position <= 2699520 or position >= 154931044


def generate(sex: str, seed: int, rows: int) -> tuple[list[tuple], dict]:
    if sex not in {"male", "female"}:
        raise ValueError("sex must be male or female")
    if rows < 100:
        raise ValueError("at least 100 rows are required for planted cases")
    rng = random.Random(seed)
    calls: list[tuple] = []
    cases: dict[str, list[str]] = {}

    def plant(case: str, probe: str, chrom: str, pos: int, call: str) -> None:
        calls.append((probe, chrom, pos, call))
        cases.setdefault(case, []).append(probe)

    for record in ANCHORS:
        plant("public_anchors", *record)
    plant("internal_snp", "i7000001", "1", 5000000, "AG")
    plant("internal_indel", "i7000002", "1", 5000010, "DI")
    plant("internal_nocall", "i7000003", "1", 5000020, "--")
    for i, call in enumerate(["DD", "DI", "II"]):
        plant("diploid_indels", f"rs90000000{i}", "2", 5000000 + i * 10, call)
    for i, call in enumerate(["D", "I"]):
        plant("haploid_indels", f"i700001{i}", "MT", 500 + i * 10, call)
    for case, pos, second in [
        ("duplicates_agree", 6000000, "AG"),
        ("duplicates_disagree", 6000010, "CC"),
    ]:
        plant(case, f"rs{pos + 900000000}", "3", pos, "AG")
        plant(case, f"i{pos + 7000000}", "3", pos, second)
    plant("palindromic", "rs900000010", "4", 5000000, "AT")
    for i in range(12):
        plant("nocall_block", f"i700010{i:02}", "5", 7000000 + i * 10000, "--")
    for i in range(21):
        plant("roh", f"rs{900000100 + i}", "6", 10000000 + i * 50000, "AA")
    for i, pos in enumerate([100000, 2699520, 2699521, 5000000, 154931043, 155000000]):
        call = "AG" if sex == "female" or is_x_par(pos) else "A"
        plant("x_ploidy", f"rs{900000200 + i}", "X", pos, call)
    plant("y_ploidy", "rs900000210", "Y", 10000000, "G" if sex == "male" else "--")
    plant("mt_ploidy", "rs900000211", "MT", 1000, "C")
    occupied = {(c, p) for _, c, p, _ in calls}
    while len(calls) < rows:
        index = len(calls)
        # Probe density follows chromosome length; MT is tiny, so it gets a
        # fixed small share (~0.3%, like real arrays) to stay satisfiable.
        chrom = rng.choices(CHROMS, cum_weights=CUM_WEIGHTS)[0]
        pos = rng.randint(1, LENGTHS[CHROMS.index(chrom)])
        # Keep planted blocks uncontaminated, and accidental duplicates out.
        if (
            (chrom, pos) in occupied
            or (chrom == "6" and 10000000 <= pos <= 11000000)
            or (chrom == "5" and 7000000 <= pos <= 7110000)
        ):
            continue
        occupied.add((chrom, pos))
        if chrom == "Y" and sex == "female" or rng.random() < 0.02:
            call = "--"
        elif chrom in {"Y", "MT"} or (
            sex == "male" and chrom == "X" and not is_x_par(pos)
        ):
            call = rng.choice("ACGT")
        else:
            call = "".join(sorted(rng.choices("ACGT", k=2)))
        calls.append((f"rs{910000000 + index}", chrom, pos, call))
    order = {chrom: i for i, chrom in enumerate(CHROMS)}
    calls.sort(key=lambda row: (order[row[1]], row[2], row[0]))
    planted_ids = {probe for probes in cases.values() for probe in probes}
    return calls, {
        "synthetic": True,
        "format": "23andMe-v5",
        "build": "GRCh37",
        "sex": sex,
        "seed": seed,
        "rows": rows,
        "cases": cases,
        "planted": [list(row) for row in calls if row[0] in planted_ids],
        "roh_interval": {"chrom": "6", "start": 10000000, "end": 11000000},
    }


def write_fixture(path: Path, sex: str, seed: int, rows: int) -> Path:
    calls, manifest = generate(sex, seed, rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        MARKER,
        "# This data is synthetic and is not from a real person.",
        "# Generated by YouGene; 23andMe v5-style raw data test fixture.",
        "# The calls below are invented, not suitable for interpretation.",
        "# Genotypes are reported on the plus strand of the reference genome.",
        "# Reference human assembly build 37 (GRCh37).",
        "# rsid\tchromosome\tposition\tgenotype",
    ]
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(header) + "\n")
        for probe, chrom, pos, call in calls:
            handle.write(f"{probe}\t{chrom}\t{pos}\t{call}\n")
    manifest_path = path.with_suffix(".json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sex", choices=["male", "female"], required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--rows", type=int, default=5000)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    if args.rows < 100:
        parser.error("at least 100 rows are required")
    write_fixture(args.output, args.sex, args.seed, args.rows)


if __name__ == "__main__":
    main()
