"""Turn an uploaded file into a stored sample: unpack, detect, load, check, QC."""

import gzip
import hashlib
import logging
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from yougene import importers, store
from yougene.analysis import qc
from yougene.annotate import runner
from yougene.db import connect
from yougene.importers import arrays
from yougene.importers.base import ImportFailed

log = logging.getLogger("yougene.imports")
MAX_UNPACKED_BYTES = 600 * 1024 * 1024
Progress = Callable[[float, str], None]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


GZIP_MAGIC = bytes([0x1F, 0x8B])


def _copy_limited(source, target: Path) -> None:
    written = 0
    with target.open("wb") as out:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            written += len(chunk)
            if written > MAX_UNPACKED_BYTES:
                raise ImportFailed("too_large", "The unpacked file is too large.")
            out.write(chunk)


def unpack(path: Path, workdir: Path) -> Path:
    """Return a plain text file: ``path`` itself, the one .txt/.csv inside a
    zip, or the decompressed content of a .gz (FamilyTreeDNA ships .csv.gz)."""
    with path.open("rb") as handle:
        magic = handle.read(2)
    if magic == GZIP_MAGIC:
        target = workdir / "unpacked.txt"
        try:
            with gzip.open(path, "rb") as source:
                _copy_limited(source, target)
        except (OSError, EOFError) as error:
            raise ImportFailed("unreadable", "The .gz file is damaged.") from error
        return target
    if not zipfile.is_zipfile(path):
        return path
    with zipfile.ZipFile(path) as archive:
        members = [
            m
            for m in archive.infolist()
            if not m.is_dir() and m.filename.lower().endswith((".txt", ".csv"))
        ]
        if len(members) != 1:
            raise ImportFailed(
                "zip_contents",
                "The zip file should contain exactly one .txt or .csv raw data file "
                f"(found {len(members)}).",
            )
        member = members[0]
        if member.file_size > MAX_UNPACKED_BYTES:
            raise ImportFailed("too_large", "The file inside the zip is too large.")
        target = workdir / "unpacked.txt"
        with archive.open(member) as source:
            _copy_limited(source, target)
    return target


def default_name(vendor: str) -> str:
    return f"{vendor} sample ({datetime.now(UTC):%Y-%m-%d})"


def run(
    upload: Path,
    file_sha256: str,
    progress: Progress,
    display_name: str | None = None,
    relationship: str | None = None,
    replace_id: str | None = None,
) -> dict:
    """Import ``upload``. With ``replace_id``, the old sample is removed only
    after the new one has loaded successfully."""
    workdir = upload.parent
    progress(0.05, "Reading file")
    text = unpack(upload, workdir)
    importer, detection = importers.detect(text)

    sample_id = store.new_sample_id()
    final = store.sample_path(sample_id)
    partial = final.with_name(final.name + ".partial")
    partial.unlink(missing_ok=True)
    con = connect(partial)
    try:
        progress(0.15, f"Loading {detection.vendor} calls")
        importer.load(con, text)
        progress(0.6, "Checking genome build")
        build = importer.confirm_build(con, detection)
        progress(0.7, "Checking chromosome copy numbers")
        ploidy = arrays.fix_ploidy(con, qc.infer_sex(con)["inferred"])
        progress(0.75, "Computing quality summary")
        summary = qc.summarise(con)
        summary["build_evidence"] = build
        summary["ploidy_normalisation"] = ploidy
        progress(0.9, "Saving")
        con.execute("CREATE INDEX calls_probe ON calls (probe_id)")
        con.execute("CHECKPOINT")
    except BaseException:
        con.close()
        partial.unlink(missing_ok=True)
        raise
    con.close()
    partial.replace(final)
    if replace_id:
        store.delete_sample(replace_id)

    try:
        record = store.add_sample(
            {
                "id": sample_id,
                "display_name": (display_name or "").strip()
                or default_name(detection.vendor),
                "relationship": (relationship or "").strip() or None,
                "vendor": detection.vendor,
                "format": detection.format,
                "build": build["build"],
                "file_sha256": file_sha256,
                "qc": summary,
            }
        )
    except BaseException:
        final.unlink(missing_ok=True)
        raise
    if runner.reference_fingerprint() is not None:
        progress(0.95, "Matching against reference data")
        try:
            runner.annotate_sample(sample_id)
        except Exception:
            # The sample is stored; annotation can be re-run from the workspace.
            log.error("annotation after import failed for sample %s", sample_id)
    progress(1.0, "Done")
    return record
