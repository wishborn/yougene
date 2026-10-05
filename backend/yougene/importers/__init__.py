"""Offline importers: detect a raw-data format and load it into a sample DB.

Every importer turns a vendor file into the same normalised ``calls`` table
(see ``base.CALLS_SCHEMA``). Importers never touch the network.
"""

from pathlib import Path

from yougene.importers import twentythree
from yougene.importers.base import Detection, ImportFailed
from yougene.importers.vendors import VENDORS

# 23andMe first: its comment header is the most specific signature.
IMPORTERS = [twentythree, *VENDORS]


def detect(path: Path) -> tuple[object, Detection]:
    """Return the importer module that recognises ``path`` and its detection."""
    for importer in IMPORTERS:
        found = importer.detect(path)
        if found is not None:
            return importer, found
    raise ImportFailed(
        "unrecognised_format",
        "This file isn't a format YouGene can read yet. "
        "Supported today: raw data from 23andMe, AncestryDNA, MyHeritage, "
        "FamilyTreeDNA and Living DNA (the .txt/.csv file or the .zip download).",
    )


__all__ = ["Detection", "ImportFailed", "detect"]
