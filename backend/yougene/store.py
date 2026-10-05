"""Sample registry and per-sample databases, all under the data directory.

Layout::

    <data_dir>/registry.duckdb      samples table (one row per imported file)
    <data_dir>/samples/<id>.duckdb  that sample's calls + QC
    <data_dir>/tmp/                 uploads in flight; emptied after import

Original filenames are never stored: 23andMe names downloads after the
account holder, and a sample is labelled by the name the user gives it.
"""

import json
import shutil
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from yougene.config import data_dir
from yougene.db import connect

_lock = threading.RLock()

REGISTRY_SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    id           VARCHAR PRIMARY KEY,
    display_name VARCHAR NOT NULL,
    relationship VARCHAR,
    vendor       VARCHAR NOT NULL,
    format       VARCHAR NOT NULL,
    build        VARCHAR NOT NULL,
    file_sha256  VARCHAR NOT NULL UNIQUE,
    qc           JSON NOT NULL,
    created_at   TIMESTAMP NOT NULL,
    updated_at   TIMESTAMP NOT NULL
)
"""

FIELDS = [
    "id",
    "display_name",
    "relationship",
    "vendor",
    "format",
    "build",
    "file_sha256",
    "qc",
    "created_at",
    "updated_at",
]


def root() -> Path:
    path = data_dir()
    (path / "samples").mkdir(parents=True, exist_ok=True)
    (path / "tmp").mkdir(parents=True, exist_ok=True)
    return path


def tmp_dir() -> Path:
    return root() / "tmp"


def sample_path(sample_id: str) -> Path:
    if not sample_id or not all(ch in "0123456789abcdef" for ch in sample_id):
        raise KeyError(sample_id)
    return root() / "samples" / f"{sample_id}.duckdb"


def annotation_path(sample_id: str) -> Path:
    """Findings live beside the sample, rebuilt whenever reference data changes."""
    return sample_path(sample_id).with_name(f"{sample_id}.annot.duckdb")


def open_annotation(sample_id: str):
    path = annotation_path(sample_id)
    if not path.exists():
        return None
    return connect(path, read_only=True)


def new_sample_id() -> str:
    return uuid.uuid4().hex


def _registry():
    con = connect(root() / "registry.duckdb")
    con.execute(REGISTRY_SCHEMA)
    return con


def _row(values) -> dict:
    record = dict(zip(FIELDS, values, strict=True))
    record["qc"] = json.loads(record["qc"])
    for key in ("created_at", "updated_at"):
        record[key] = record[key].replace(tzinfo=UTC).isoformat()
    return record


def list_samples() -> list[dict]:
    with _lock:
        con = _registry()
        try:
            rows = con.execute(
                f"SELECT {', '.join(FIELDS)} FROM samples ORDER BY created_at"
            ).fetchall()
        finally:
            con.close()
    return [_row(r) for r in rows]


def get_sample(sample_id: str) -> dict | None:
    with _lock:
        con = _registry()
        try:
            row = con.execute(
                f"SELECT {', '.join(FIELDS)} FROM samples WHERE id = ?", [sample_id]
            ).fetchone()
        finally:
            con.close()
    return _row(row) if row else None


def find_by_hash(file_sha256: str) -> dict | None:
    with _lock:
        con = _registry()
        try:
            row = con.execute(
                f"SELECT {', '.join(FIELDS)} FROM samples WHERE file_sha256 = ?",
                [file_sha256],
            ).fetchone()
        finally:
            con.close()
    return _row(row) if row else None


def add_sample(record: dict) -> dict:
    now = datetime.now(UTC).replace(tzinfo=None)
    values = {**record, "created_at": now, "updated_at": now}
    values["qc"] = json.dumps(record["qc"])
    with _lock:
        con = _registry()
        try:
            con.execute(
                f"INSERT INTO samples ({', '.join(FIELDS)}) VALUES "
                f"({', '.join('?' for _ in FIELDS)})",
                [values[f] for f in FIELDS],
            )
        finally:
            con.close()
    return get_sample(record["id"])


def update_sample(sample_id: str, changes: dict) -> dict | None:
    allowed = {
        k: v for k, v in changes.items() if k in ("display_name", "relationship")
    }
    if not allowed:
        return get_sample(sample_id)
    sets = ", ".join(f"{k} = ?" for k in allowed)
    now = datetime.now(UTC).replace(tzinfo=None)
    with _lock:
        con = _registry()
        try:
            con.execute(
                f"UPDATE samples SET {sets}, updated_at = ? WHERE id = ?",
                [*allowed.values(), now, sample_id],
            )
        finally:
            con.close()
    return get_sample(sample_id)


def delete_sample(sample_id: str) -> bool:
    with _lock:
        con = _registry()
        try:
            deleted = con.execute(
                "DELETE FROM samples WHERE id = ? RETURNING id", [sample_id]
            ).fetchall()
        finally:
            con.close()
        path = sample_path(sample_id)
        annot = annotation_path(sample_id)
        for candidate in (path, annot):
            candidate.unlink(missing_ok=True)
            candidate.with_name(candidate.name + ".wal").unlink(missing_ok=True)
    return bool(deleted)


def delete_everything() -> None:
    """Remove every sample, the registry and temp files."""
    with _lock:
        base = root()
        for name in ("samples", "tmp"):
            shutil.rmtree(base / name, ignore_errors=False)
        for name in ("registry.duckdb", "registry.duckdb.wal"):
            (base / name).unlink(missing_ok=True)
        root()  # recreate empty folders


def open_sample(sample_id: str):
    path = sample_path(sample_id)
    if not path.exists():
        raise KeyError(sample_id)
    return connect(path, read_only=True)
