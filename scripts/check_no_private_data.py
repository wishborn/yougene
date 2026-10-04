"""Reject private data; allow only explicitly marked synthetic fixtures."""

import re
import subprocess
import sys
from pathlib import Path

NAME = re.compile(
    r"(genome_|23andme|ancestry.*\.txt$|\.vcf(\.gz)?$|\.duckdb$|\.sqlite3?$)",
    re.IGNORECASE,
)
MARKER = b"# YOUGENE SYNTHETIC FIXTURE - not a real person"
FIXTURES = Path("backend/tests/fixtures/synthetic")
ROW = re.compile(rb"^(?:rs\d+|i\d+)\t\w+\t\d+\t[ACGTDI-]{1,2}$")


def check_file(path: Path, root: Path) -> str | None:
    relative = path.relative_to(root)
    if path.is_symlink():
        return (
            "symlinks are not allowed in synthetic fixtures"
            if FIXTURES in relative.parents
            else None
        )
    try:
        with path.open("rb") as handle:
            first = handle.readline().rstrip(b"\r\n")
            if first == MARKER and FIXTURES in relative.parents:
                return None
            if FIXTURES in relative.parents and path.suffix == ".txt":
                return "synthetic fixture missing exact marker"
            if NAME.search(relative.as_posix()):
                return "filename looks like genome/reference data"
            if ROW.fullmatch(first) or b"rsid\tchromosome\tposition\tgenotype" in first:
                return "contains raw genotype rows"
            for line in handle:
                line = line.rstrip(b"\r\n")
                if (
                    ROW.fullmatch(line)
                    or b"rsid\tchromosome\tposition\tgenotype" in line
                ):
                    return "contains raw genotype rows"
    except FileNotFoundError:
        return None
    return None


def main() -> int:
    root = Path.cwd()
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True)
    bad = []
    for name in out.stdout.decode("utf-8").split("\0"):
        if name:
            reason = check_file(root / name, root)
            if reason:
                bad.append(f"{name}: {reason}")
    if bad:
        print("Private data check FAILED:\n" + "\n".join(bad))
        return 1
    print("Private data check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
