"""Fail if anything that looks like raw genome data is tracked or staged."""
import re
import subprocess
import sys

NAME = re.compile(r"(genome_|23andme|ancestry.*\.txt$|\.vcf(\.gz)?$|\.duckdb$|\.sqlite3?$)", re.I)
HEADER = "rsid\tchromosome\tposition\tgenotype"
MAX_BYTES = 5_000_000


def tracked():
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
    return [p for p in out.decode().split("\0") if p]


bad = []
for path in tracked():
    if NAME.search(path):
        bad.append(f"{path}: filename looks like genome/reference data")
        continue
    try:
        with open(path, "rb") as f:
            head = f.read(MAX_BYTES)
    except OSError:
        continue
    text = head.decode("utf-8", "ignore")
    if HEADER in text or re.search(r"^rs\d+\t\w+\t\d+\t[ACGTDI-]{1,2}$", text, re.M):
        bad.append(f"{path}: contains raw genotype rows")

if bad:
    print("Private data check FAILED:\n" + "\n".join(bad))
    sys.exit(1)
print("Private data check passed.")
