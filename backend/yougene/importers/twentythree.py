"""23andMe raw data (all chip versions export the same 4-column TSV).

Header comment lines start with ``#``; the last one names the columns:
``# rsid  chromosome  position  genotype``. Calls are plus-strand on GRCh37.
Genotypes: two letters (diploid), one letter (haploid X/Y/MT), ``--`` for a
no-call, and ``D``/``I`` codes for insertion/deletion probes.
"""

import re
from pathlib import Path

from yougene.importers import arrays
from yougene.importers.base import Detection

VENDOR = "23andMe"
COLUMN_LINE = "# rsid\tchromosome\tposition\tgenotype"
BUILD = re.compile(r"build\s*(\d+)", re.IGNORECASE)
HEADER_LINES = 60


def head(path: Path, limit: int = HEADER_LINES) -> list[str]:
    """Leading comment lines (and the first data line) of a text file."""
    lines = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            lines.append(line.rstrip("\r\n"))
            if not line.startswith("#") or len(lines) >= limit:
                break
    return lines


def build_from_header(lines: list[str]) -> str | None:
    for line in lines:
        if line.startswith("#") and "build" in line.lower():
            match = BUILD.search(line)
            if match:
                return match[1]
    return None


def detect(path: Path) -> Detection | None:
    lines = head(path)
    comments = [line for line in lines if line.startswith("#")]
    is_23andme = COLUMN_LINE in comments or any(
        "23andme" in c.lower() for c in comments
    )
    if not is_23andme:
        return None
    return Detection(
        vendor=VENDOR, format="23andme-tsv", build_from_header=build_from_header(lines)
    )


def load(con, path: Path) -> dict:
    arrays.read_raw(con, path, vendor=VENDOR, delim="\t")
    return arrays.build_calls(con, VENDOR)


confirm_build = arrays.confirm_build
