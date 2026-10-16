"""The one store of the Word files, shared by every route module.

`storage.STORE` is read where it is used, never copied at import, so `reset()` (tests,
each with their own folder) reaches every module at once.
"""
from __future__ import annotations

import io
import mimetypes

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

import db
from filestore import get_filestore

STORE = get_filestore()


def reset() -> None:
    global STORE
    STORE = get_filestore()


def serve(doc_id: str) -> StreamingResponse:
    d = db.get_decision(doc_id)
    if not d or not d["file_name"] or not STORE.exists(d["file_name"]):
        raise HTTPException(status_code=404, detail="File not found")
    data = STORE.get(d["file_name"])
    media = mimetypes.guess_type(d["file_name"])[0] or "application/octet-stream"
    return StreamingResponse(io.BytesIO(data), media_type=media,
                             headers={"Content-Disposition": f'inline; filename="{d["file_name"]}"'})
