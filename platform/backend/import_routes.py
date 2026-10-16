"""The admin's upload of a delivery: the routes. The import itself is importer.py."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select

import db
import importer
import settings
import storage
from deps import require_editor

router = APIRouter()


# ---------------- admin: integration / import ----------------
# A delivery from the pipeline arrives as a .zip of records.json and the Word files.
# importer.py does the work, the same way the command line does: a small batch is
# imported at once and the answer comes back; a large one is kept in the store and
# imported by the worker, and the page follows it through /api/admin/import/jobs.


@router.post("/api/admin/import")
def import_batch(file: UploadFile = File(...), user: dict = Depends(require_editor)) -> dict:
    import shutil
    import tempfile
    import uuid
    fd, tmp = tempfile.mkstemp(suffix=".zip")
    try:
        with os.fdopen(fd, "wb") as out:
            shutil.copyfileobj(file.file, out, length=1024 * 1024)
        try:
            n = len(importer.open_source(Path(tmp)).records())
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Not a delivery: {e}")
        name = (file.filename or "delivery.zip")[:200]
        with db.session() as s:
            job = importer.ImportJob(file_name=name, size=os.path.getsize(tmp), created_by=user["email"])
            s.add(job)
            s.commit()
            job_id = job.id
        if n <= settings.S.import_inline_max:
            importer._save(job_id, status="running", started_at=dt.datetime.utcnow())
            result = importer.run(Path(tmp), publish=settings.S.auto_publish, actor=user["email"], store=storage.STORE, workers=1)
            importer._save(job_id, status="done", finished_at=dt.datetime.utcnow(),
                           result=json.dumps(result, ensure_ascii=False))
        else:
            key = f"import-{uuid.uuid4().hex}.zip"
            storage.STORE.put_file(key, tmp)
            importer._save(job_id, file_key=key,
                           result=json.dumps({"total_records": n}, ensure_ascii=False))
    finally:
        os.unlink(tmp)
    with db.session() as s:
        return importer.job_dict(s.get(importer.ImportJob, job_id))


@router.get("/api/admin/import/jobs")
def import_jobs(_: dict = Depends(require_editor)) -> list:
    with db.session() as s:
        rows = s.scalars(select(importer.ImportJob).order_by(importer.ImportJob.id.desc()).limit(20))
        return [importer.job_dict(j) for j in rows]


@router.get("/api/admin/import/jobs/{job_id}")
def import_job(job_id: int, _: dict = Depends(require_editor)) -> dict:
    with db.session() as s:
        j = s.get(importer.ImportJob, job_id)
        if not j:
            raise HTTPException(status_code=404, detail="Not found")
        return importer.job_dict(j)
