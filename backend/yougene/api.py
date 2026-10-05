"""JSON API for samples, import jobs and calls."""

import hashlib
import re
import shutil
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from yougene import imports, store
from yougene.genome import CHROMS
from yougene.jobs import jobs

router = APIRouter(prefix="/api")

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
DELETE_ALL_PHRASE = "DELETE ALL"
SORTABLE = {
    "chrom": "chrom_order",
    "pos": "pos",
    "probe_id": "probe_id",
    "alleles": "alleles",
    "call_type": "call_type",
}
CALL_COLUMNS = [
    "probe_id",
    "id_kind",
    "chrom",
    "pos",
    "alleles",
    "ploidy",
    "call_type",
    "dup_group",
    "dup_conflict",
]


def _sample_or_404(sample_id: str) -> dict:
    try:
        record = store.get_sample(sample_id)
    except KeyError:
        record = None
    if record is None:
        raise HTTPException(404, "No such sample.")
    return record


@router.post("/samples", status_code=202)
async def upload_sample(
    request: Request,
    name: Annotated[str | None, Query(max_length=120)] = None,
    relationship: Annotated[str | None, Query(max_length=60)] = None,
    on_duplicate: Literal["reject", "replace"] = "reject",
):
    """Upload a raw data file as the request body (application/octet-stream)."""
    workdir = store.tmp_dir() / uuid.uuid4().hex
    workdir.mkdir(parents=True)
    upload = workdir / "upload"
    digest, size = hashlib.sha256(), 0
    try:
        with upload.open("wb") as out:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    limit = MAX_UPLOAD_BYTES // (1024 * 1024)
                    raise HTTPException(413, f"Files over {limit} MB aren't accepted.")
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise HTTPException(400, "The upload was empty.")
        file_sha256 = digest.hexdigest()
        existing = store.find_by_hash(file_sha256)
        if existing and on_duplicate == "reject":
            shutil.rmtree(workdir, ignore_errors=True)
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "This file has already been imported.",
                    "code": "already_imported",
                    "sample_id": existing["id"],
                },
            )
    except BaseException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise

    replace_id = existing["id"] if existing else None

    def work(progress):
        return imports.run(
            upload, file_sha256, progress, name, relationship, replace_id=replace_id
        )

    job = jobs.submit("import", work, cleanup=workdir)
    return {"job_id": job.id}


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "No such job.")
    return job.public()


@router.get("/samples")
def list_samples():
    return {"samples": store.list_samples()}


@router.get("/samples/{sample_id}")
def get_sample(sample_id: str):
    return _sample_or_404(sample_id)


class SampleChanges(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    relationship: str | None = Field(default=None, max_length=60)


@router.patch("/samples/{sample_id}")
def update_sample(sample_id: str, changes: SampleChanges):
    _sample_or_404(sample_id)
    values = changes.model_dump(exclude_unset=True)
    if "display_name" in values:
        values["display_name"] = values["display_name"].strip()
        if not values["display_name"]:
            raise HTTPException(422, "A name can't be blank.")
    if "relationship" in values and values["relationship"] is not None:
        values["relationship"] = values["relationship"].strip() or None
    return store.update_sample(sample_id, values)


@router.delete("/samples/{sample_id}", status_code=204)
def delete_sample(sample_id: str):
    _sample_or_404(sample_id)
    if jobs.active():
        raise HTTPException(409, "Wait for the current import to finish.")
    store.delete_sample(sample_id)


class DeleteAll(BaseModel):
    confirm: str


@router.delete("/data", status_code=204)
def delete_all(body: DeleteAll):
    if body.confirm != DELETE_ALL_PHRASE:
        raise HTTPException(422, f'Type "{DELETE_ALL_PHRASE}" to confirm.')
    if jobs.active():
        raise HTTPException(409, "Wait for the current import to finish.")
    store.delete_everything()


def _sort_clause(sort: str | None) -> str:
    parts = []
    for raw in (sort or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        desc = raw.startswith("-")
        key = raw.lstrip("-")
        if key not in SORTABLE:
            raise HTTPException(422, f"Can't sort by {key!r}.")
        parts.append(f"{SORTABLE[key]} {'DESC' if desc else 'ASC'}")
    parts += ["chrom_order ASC", "pos ASC", "probe_id ASC"]
    return ", ".join(parts)


@router.get("/samples/{sample_id}/calls")
def list_calls(
    sample_id: str,
    page: Annotated[int, Query(ge=0)] = 0,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
    sort: str | None = None,
    chrom: Annotated[list[str] | None, Query()] = None,
    call_type: Annotated[
        list[Literal["snp", "indel_code", "nocall"]] | None, Query()
    ] = None,
    probe: Annotated[str | None, Query(max_length=40)] = None,
    alleles: Annotated[str | None, Query(max_length=2)] = None,
    pos_min: Annotated[int | None, Query(ge=0)] = None,
    pos_max: Annotated[int | None, Query(ge=0)] = None,
    duplicates_only: bool = False,
):
    _sample_or_404(sample_id)
    where, args = [], []
    if chrom:
        bad = [c for c in chrom if c not in CHROMS]
        if bad:
            raise HTTPException(422, f"Unknown chromosome {bad[0]!r}.")
        where.append(f"chrom IN ({', '.join('?' for _ in chrom)})")
        args += chrom
    if call_type:
        where.append(f"call_type IN ({', '.join('?' for _ in call_type)})")
        args += call_type
    if probe:
        if not re.fullmatch(r"[A-Za-z0-9_]+", probe):
            raise HTTPException(422, "Probe ids contain only letters, digits and _.")
        where.append("lower(probe_id) LIKE ?")
        args.append(probe.lower() + "%")
    if alleles is not None:
        value = "".join(sorted(alleles.upper())) if alleles != "--" else ""
        where.append("alleles = ?")
        args.append(value)
    if pos_min is not None:
        where.append("pos >= ?")
        args.append(pos_min)
    if pos_max is not None:
        where.append("pos <= ?")
        args.append(pos_max)
    if duplicates_only:
        where.append("dup_group IS NOT NULL")
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    con = store.open_sample(sample_id)
    try:
        total = con.execute(f"SELECT count(*) FROM calls {clause}", args).fetchone()[0]
        rows = con.execute(
            f"SELECT {', '.join(CALL_COLUMNS)} FROM calls {clause} "
            f"ORDER BY {_sort_clause(sort)} LIMIT ? OFFSET ?",
            [*args, page_size, page * page_size],
        ).fetchall()
    finally:
        con.close()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "rows": [dict(zip(CALL_COLUMNS, r, strict=True)) for r in rows],
    }
