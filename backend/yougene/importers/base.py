"""Shared importer types and the normalised calls table."""

from dataclasses import dataclass, field

# One row per probe, exactly as the file reported it. Nothing is merged or
# dropped: duplicate positions are kept and grouped, no-calls stay as rows.
CALLS_SCHEMA = """
CREATE TABLE calls (
    probe_id     VARCHAR NOT NULL,  -- rsid or vendor id (e.g. 23andMe i-ids)
    id_kind      VARCHAR NOT NULL,  -- 'rs' | 'vendor'
    chrom        VARCHAR NOT NULL,  -- 1-22, X, Y, MT
    chrom_order  UTINYINT NOT NULL, -- 1-25, for natural sorting
    pos          UINTEGER NOT NULL, -- GRCh37, 1-based
    alleles      VARCHAR NOT NULL,  -- sorted letters; '' for a no-call
    ploidy       UTINYINT,          -- 1 or 2; NULL for a no-call
    call_type    VARCHAR NOT NULL,  -- 'snp' | 'indel_code' | 'nocall'
    dup_group    UINTEGER,          -- set when several probes share a position
    dup_conflict BOOLEAN NOT NULL   -- true when that group's calls disagree
)
"""


class ImportFailed(Exception):
    """An import that can't continue, with a message safe to show the user.

    Messages must never contain genotype content; counts and line numbers only.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Detection:
    vendor: str
    format: str
    build_from_header: str | None
    notes: list[str] = field(default_factory=list)
