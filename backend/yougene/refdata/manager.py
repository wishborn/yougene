"""Download and build the reference database, and report what's installed.

Layout under the data dir::

    reference/downloads/<file>   last downloaded copy of each source
    reference/reference.duckdb   built tables + a ``sources`` provenance table
    reference/work/              scratch space for a build; emptied afterwards

A build always writes ``reference.duckdb.partial`` and swaps it in only when
every requested source built, so a failed update never breaks a working DB.
"""

import json
import shutil
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path

from yougene.config import data_dir
from yougene.db import connect
from yougene.refdata import builders, fetch
from yougene.refdata.sources import SOURCES

Progress = Callable[[float, str], None]
CORE = ("clinvar", "gwas", "cytoband")
MIN_FREE_BYTES = 300 * 1024 * 1024


def ref_dir() -> Path:
    path = data_dir() / "reference"
    (path / "downloads").mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return ref_dir() / "reference.duckdb"


def open_reference():
    path = db_path()
    if not path.exists():
        return None
    return connect(path, read_only=True)


def status() -> dict:
    """What's installed, per source, plus what could be installed."""
    installed: dict[str, dict] = {}
    con = open_reference()
    if con is not None:
        try:
            for source_id, meta in con.execute(
                "SELECT source, meta FROM sources"
            ).fetchall():
                installed[source_id] = json.loads(meta)
        finally:
            con.close()
    return {
        "sources": [
            {
                "id": s.id,
                "title": s.title,
                "purpose": s.purpose,
                "license": s.license,
                "attribution": s.attribution,
                "approx_mb": s.approx_mb,
                "url": s.url,
                "installed": installed.get(s.id),
            }
            for s in SOURCES.values()
        ],
        "ready": all(i in installed for i in CORE),
    }


def install(
    source_ids: Iterable[str] = CORE,
    progress: Progress = lambda value, message: None,
    download=None,
    refresh: bool = True,
    keep_downloads: bool = False,
) -> dict:
    """Download (unless ``refresh`` is false and a copy exists) and build.

    Downloads are deleted after a successful build unless ``keep_downloads``:
    they're only needed to rebuild offline, and they're large.
    """
    download = download or fetch.download
    ids = [i for i in source_ids if i in SOURCES]
    if not ids:
        raise ValueError("No known sources requested.")
    base = ref_dir()
    downloads = base / "downloads"
    work = base / "work"
    work.mkdir(exist_ok=True)

    # Keep provenance of sources that aren't being rebuilt this time.
    kept = {
        entry["id"]: entry["installed"]
        for entry in status()["sources"]
        if entry["installed"] and entry["id"] not in ids
    }

    # Rough space needed: downloads, the new database (about twice the
    # download size), plus a copy of the old one when other sources are kept.
    needed = sum(SOURCES[i].approx_mb for i in ids) * 3 * 1024 * 1024
    if kept and db_path().exists():
        needed += db_path().stat().st_size
    free = shutil.disk_usage(base).free
    if free < needed + MIN_FREE_BYTES:
        raise fetch.DownloadFailed(
            f"Updating reference data needs about {needed // (1024 * 1024):,} MB of "
            f"free disk space; {free // (1024 * 1024):,} MB is free."
        )

    fetched: dict[str, dict] = {}
    share = 0.6 / len(ids)
    for index, source_id in enumerate(ids):
        source = SOURCES[source_id]
        existing = downloads / source.filename
        if not refresh and existing.exists():
            fetched[source_id] = {
                "source": source_id,
                "path": str(existing),
                "reused_download": True,
            }
            continue

        def report(done: int, total: int | None, i=index, title=source.title) -> None:
            part = done / total if total else 0.0
            mb = done / 1e6
            progress(i * share + part * share, f"Downloading {title} ({mb:.0f} MB)")

        fetched[source_id] = download(source, downloads, report)

    partial = db_path().with_name("reference.duckdb.partial")
    partial.unlink(missing_ok=True)
    if kept and db_path().exists():
        shutil.copyfile(db_path(), partial)  # keep tables of other sources
    con = connect(partial)
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS sources (source VARCHAR PRIMARY KEY, meta JSON)"
        )
        results = {}
        share = 0.4 / len(ids)
        for index, source_id in enumerate(ids):
            source = SOURCES[source_id]
            progress(0.6 + index * share, f"Building {source.title}")
            path = Path(fetched[source_id]["path"])
            builder = builders.BUILDERS[source_id]
            stats = (
                builder(con, path, work)
                if source_id in ("gwas", "liftover")
                else builder(con, path)
            )
            meta = {
                **{k: v for k, v in fetched[source_id].items() if k != "path"},
                "stats": stats,
                "built_at": datetime.now(UTC).isoformat(),
                "license": source.license,
            }
            con.execute(
                "INSERT OR REPLACE INTO sources VALUES (?, ?)",
                [source_id, json.dumps(meta)],
            )
            results[source_id] = meta
        con.execute("CHECKPOINT")
    except BaseException:
        con.close()
        partial.unlink(missing_ok=True)
        if not keep_downloads:
            for meta in fetched.values():
                Path(meta["path"]).unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
    con.close()
    partial.replace(db_path())
    if not keep_downloads:
        for source_id in ids:
            Path(fetched[source_id]["path"]).unlink(missing_ok=True)
    progress(1.0, "Reference data ready")
    return {"built": results, "kept": sorted(kept)}
