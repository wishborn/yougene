"""Run and track annotation for stored samples."""

import json
from collections.abc import Callable

from yougene import store
from yougene.annotate.engine import annotate
from yougene.refdata import manager

Progress = Callable[[float, str], None]


def reference_fingerprint() -> dict | None:
    """What the current reference DB was built from, or None if not ready."""
    status = manager.status()
    if not status["ready"]:
        return None
    return {
        s["id"]: {
            "built_at": s["installed"]["built_at"],
            "released": s["installed"].get("released"),
        }
        for s in status["sources"]
        if s["installed"]
    }


def state(sample_id: str) -> dict:
    current = reference_fingerprint()
    con = store.open_annotation(sample_id)
    if con is None:
        return {"state": "none" if current else "no_reference", "reference": current}
    try:
        meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
    finally:
        con.close()
    used = json.loads(meta["reference"])
    stats = json.loads(meta["stats"])
    fresh = current is not None and all(
        used.get(k, {}).get("built_at") == v["built_at"] for k, v in current.items()
    )
    return {
        "state": "current" if fresh else "stale",
        "reference": used,
        "stats": stats,
    }


def annotate_sample(sample_id: str, progress: Progress = lambda v, m: None) -> dict:
    fingerprint = reference_fingerprint()
    if fingerprint is None:
        raise RuntimeError("Reference data isn't installed yet.")
    progress(0.1, "Matching against reference data")
    stats = annotate(
        store.sample_path(sample_id),
        manager.db_path(),
        store.annotation_path(sample_id),
        fingerprint,
    )
    progress(1.0, "Annotated")
    return {"id": sample_id, "stats": stats}


def annotate_all(progress: Progress = lambda v, m: None) -> list[dict]:
    samples = store.list_samples()
    results = []
    for index, sample in enumerate(samples):
        progress(index / max(len(samples), 1), f"Annotating {sample['display_name']}")
        results.append(annotate_sample(sample["id"]))
    return results
