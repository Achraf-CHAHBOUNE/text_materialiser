"""FastAPI backend for the anonymized-decisions platform (website_brief).

Three surfaces on one API, separated by role:
  - Admin · Integration  — import (with a PII gate), review, correct, publish (audited).
  - Admin · Clients       — account CRUD, suspend, activity.
  - Client space          — browse/search/view PUBLISHED decisions only.

The platform stores only anonymized content. Raw documents never enter it: imports carry
anonymized files + metadata, and the import gate refuses anything that still looks like PII.

Run (local):   uvicorn server:app --port 8000
"""
from __future__ import annotations

import io
import json
import mimetypes
import os
import zipfile
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import auth as authmod
import db
import piigate
import textnorm
from filestore import get_filestore

app = FastAPI(title="Anonymized Decisions Platform", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOW_ORIGINS", "*").split(","),
    allow_methods=["*"], allow_headers=["*"],
)

STORE = get_filestore()
CATEGORIES = ["إدارية", "تجارية", "مدنية", "جنائية", "اجتماعية", "أحوال شخصية", "عقارية"]
# Publish imports straight away (no manual pending step). Set AUTO_PUBLISH=0 to require review.
AUTO_PUBLISH = os.getenv("AUTO_PUBLISH", "1") not in ("0", "false", "False", "no")


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    email, pw = os.getenv("SEED_EMAIL", ""), os.getenv("SEED_PASSWORD", "")
    if email and pw and not db.get_user(email):
        db.upsert_user(email, authmod.hash_password(pw), role="admin")
    ce, cp = os.getenv("SEED_CLIENT_EMAIL", ""), os.getenv("SEED_CLIENT_PASSWORD", "")
    if ce and cp and not db.get_user(ce):
        db.upsert_user(ce, authmod.hash_password(cp), role="client")


# ---------------- auth plumbing ----------------
def _user_from_token(token: str) -> dict:
    email = authmod.verify_token(token or "")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.get_user(email)
    if not user:
        raise HTTPException(status_code=401, detail="Unknown account")
    if user["status"] != "active":               # suspension takes effect immediately (§C-2)
        raise HTTPException(status_code=403, detail="Account suspended")
    return user


def current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _user_from_token(authorization.split(" ", 1)[1])


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


def _flex_user(authorization: Optional[str], token: str) -> dict:
    """Auth for browser file links: Bearer header OR ?token= query."""
    tok = (authorization.split(" ", 1)[1]
           if authorization and authorization.startswith("Bearer ") else token)
    return _user_from_token(tok)


class LoginBody(BaseModel):
    email: str
    password: str


@app.post("/api/auth/login")
def login(body: LoginBody) -> dict:
    user = db.get_user(body.email)
    if not user or not authmod.verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user["status"] != "active":
        raise HTTPException(status_code=403, detail="Account suspended")
    db.touch_login(body.email)
    return {"token": authmod.make_token(body.email), "email": body.email, "role": user["role"]}


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)) -> dict:
    return {"email": user["email"], "role": user["role"], "status": user["status"]}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "storage": type(STORE).__name__}


# ---------------- text extraction ----------------
def _extract_text(name: str, data: bytes) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext == "docx":
        from docx import Document
        return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    if ext == "pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((pg.extract_text() or "") for pg in reader.pages)
    return data.decode("utf-8", "ignore")


# ---------------- admin: integration / import ----------------
@app.post("/api/admin/import")
async def import_batch(file: UploadFile = File(...), user: dict = Depends(require_admin)) -> dict:
    """Import a pipeline batch: a .zip of records.json + anonymized files.

    Import gate (§I-2): a record with no matching file is rejected; a file that still
    trips the PII detector is quarantined. Re-importing the same doc_id UPDATES (§I-8).
    """
    raw = await file.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Upload must be a .zip")

    names = zf.namelist()
    rec_name = next((n for n in names if n.rsplit("/", 1)[-1] == "records.json"), "")
    if not rec_name:
        raise HTTPException(status_code=400, detail="records.json not found in the archive")
    records = json.loads(zf.read(rec_name).decode("utf-8"))
    by_base = {n.rsplit("/", 1)[-1]: n for n in names}

    imported = updated = 0
    rejected, quarantined = [], []
    for rec in records:
        doc_id = rec.get("doc_id")
        fname = rec.get("anonymized_file") or (doc_id + ".docx")
        if fname not in by_base:
            rejected.append({"doc_id": doc_id, "reason": "no matching file in archive"})
            continue
        data = zf.read(by_base[fname])
        text = _extract_text(fname, data)
        findings = piigate.scan(text)
        if findings:                                   # gate: refuse anything that looks like PII
            quarantined.append({"doc_id": doc_id,
                                "findings": [f"{f.type}:{f.value}" for f in findings[:5]]})
            continue

        existed = db.get_decision(doc_id) is not None
        fields = rec.get("fields", {})
        def fv(label): return (fields.get(label) or {}).get("value", "")
        cat = rec.get("category")
        cat = cat.get("value", "") if isinstance(cat, dict) else (cat or "")
        db.upsert_decision({
            "doc_id": doc_id, "source_file": rec.get("source_file", ""),
            "fmt": rec.get("format", ""), "read_method": rec.get("read_method", ""),
            "category": cat or "غير محدد", "level": rec.get("level", ""),
            "court": rec.get("court", ""),
            "decision_no": fv("رقم القرار"), "file_no": fv("رقم الملف"),
            "decision_date": fv("تاريخ القرار"), "case_id": rec.get("case_id", ""),
            "outcome": rec.get("outcome", ""),
            "pii_removed": rec.get("pii", {}).get("removed_count", 0),
            "review": rec.get("review", "ok"),
        }, body_text=text, file_name=fname)
        db.set_links(doc_id, rec.get("links", []))
        STORE.put(fname, data)
        if AUTO_PUBLISH:                       # publish directly — no manual pending step
            db.set_decision_state(doc_id, "published", user["email"])
        imported += 0 if existed else 1
        updated += 1 if existed else 0

    db.add_audit(user["email"], "import", "batch", rec_name,
                 new=f"imported={imported} updated={updated} "
                     f"rejected={len(rejected)} quarantined={len(quarantined)}")
    return {"imported": imported, "updated": updated,
            "rejected": rejected, "quarantined": quarantined,
            "total_records": len(records)}


@app.get("/api/admin/decisions")
def admin_decisions(state: str = "", category: str = "", level: str = "",
                    limit: int = 200, offset: int = 0,
                    _: dict = Depends(require_admin)) -> list:
    states = (state,) if state else None
    return db.list_decisions(states=states, category=category, level=level,
                             limit=limit, offset=offset)


@app.get("/api/admin/queue")
def admin_queue(_: dict = Depends(require_admin)) -> list:
    return db.work_queue()


@app.get("/api/admin/stats")
def admin_stats(_: dict = Depends(require_admin)) -> dict:
    return db.counts()


@app.get("/api/admin/decisions/{doc_id}")
def admin_decision(doc_id: str, _: dict = Depends(require_admin)) -> dict:
    d = db.get_decision(doc_id, body=True)
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    d["links"] = db.links_for(doc_id)
    d["audit"] = db.audit_for(doc_id)
    return d


class FieldPatch(BaseModel):
    changes: dict


@app.patch("/api/admin/decisions/{doc_id}")
def admin_correct(doc_id: str, body: FieldPatch, user: dict = Depends(require_admin)) -> dict:
    d = db.update_decision_fields(doc_id, body.changes, user["email"])
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    return d


class StateBody(BaseModel):
    state: str


@app.post("/api/admin/decisions/{doc_id}/state")
def admin_set_state(doc_id: str, body: StateBody, user: dict = Depends(require_admin)) -> dict:
    d = db.set_decision_state(doc_id, body.state, user["email"])
    if not d:
        raise HTTPException(status_code=400, detail="Unknown decision or state")
    return d


@app.post("/api/admin/decisions/{doc_id}/file")
async def admin_replace_file(doc_id: str, file: UploadFile = File(...),
                             user: dict = Depends(require_admin)) -> dict:
    """Correct/replace the anonymized file itself (§I-4), re-checked by the gate."""
    d = db.get_decision(doc_id)
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    data = await file.read()
    text = _extract_text(file.filename, data)
    findings = piigate.scan(text)
    if findings:
        raise HTTPException(status_code=422,
                            detail=f"File still contains PII patterns: "
                                   f"{[f'{f.type}:{f.value}' for f in findings[:5]]}")
    db.upsert_decision({"doc_id": doc_id}, body_text=text, file_name=file.filename)
    STORE.put(file.filename, data)
    db.add_audit(user["email"], "replace_file", "decision", doc_id, new=file.filename)
    return {"ok": True}


@app.get("/api/admin/decisions/{doc_id}/file")
def admin_file(doc_id: str, authorization: Optional[str] = Header(None),
               token: str = "") -> StreamingResponse:
    user = _flex_user(authorization, token)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return _serve_file(doc_id)


# ---------------- admin: clients ----------------
class ClientCreate(BaseModel):
    email: str
    password: str


class ClientPatch(BaseModel):
    status: Optional[str] = None
    password: Optional[str] = None


@app.get("/api/admin/clients")
def list_clients(_: dict = Depends(require_admin)) -> list:
    out = []
    for c in db.list_clients():
        c.pop("password_hash", None)
        c["recent_activity"] = db.activity_for(c["email"], limit=5)
        out.append(c)
    return out


@app.post("/api/admin/clients")
def create_client(body: ClientCreate, user: dict = Depends(require_admin)) -> dict:
    if db.get_user(body.email):
        raise HTTPException(status_code=409, detail="Account already exists")
    db.upsert_user(body.email, authmod.hash_password(body.password), role="client")
    db.add_audit(user["email"], "create_client", "user", body.email)
    return {"email": body.email, "role": "client", "status": "active"}


@app.patch("/api/admin/clients/{email}")
def update_client(email: str, body: ClientPatch, user: dict = Depends(require_admin)) -> dict:
    target = db.get_user(email)
    if not target or target["role"] != "client":
        raise HTTPException(status_code=404, detail="Client not found")
    if body.status in ("active", "suspended"):
        db.set_user_status(email, body.status)
        db.add_audit(user["email"], body.status, "user", email, field="status")
    if body.password:
        db.upsert_user(email, authmod.hash_password(body.password), role="client",
                       status=body.status or target["status"])
        db.add_audit(user["email"], "reset_password", "user", email)
    result = db.get_user(email)
    result.pop("password_hash", None)
    return result


@app.delete("/api/admin/clients/{email}")
def delete_client(email: str, user: dict = Depends(require_admin)) -> dict:
    target = db.get_user(email)
    if not target or target["role"] != "client":
        raise HTTPException(status_code=404, detail="Client not found")
    db.delete_user(email)
    db.add_audit(user["email"], "delete_client", "user", email)
    return {"deleted": email}


@app.get("/api/admin/clients/{email}/activity")
def client_activity(email: str, _: dict = Depends(require_admin)) -> list:
    return db.activity_for(email, limit=200)


# ---------------- client space (published only) ----------------
def _serve_file(doc_id: str) -> StreamingResponse:
    d = db.get_decision(doc_id)
    if not d or not d["file_name"] or not STORE.exists(d["file_name"]):
        raise HTTPException(status_code=404, detail="File not found")
    data = STORE.get(d["file_name"])
    media = mimetypes.guess_type(d["file_name"])[0] or "application/octet-stream"
    return StreamingResponse(io.BytesIO(data), media_type=media,
                             headers={"Content-Disposition": f'inline; filename="{d["file_name"]}"'})


@app.get("/api/categories")
def categories(_: dict = Depends(current_user)) -> list:
    return CATEGORIES


@app.get("/api/decisions")
def client_decisions(category: str = "", level: str = "",
                     limit: int = 50, offset: int = 0,
                     _: dict = Depends(current_user)) -> list:
    return db.list_decisions(states=("published",), category=category, level=level,
                             limit=limit, offset=offset)


@app.get("/api/search")
def client_search(q: str = Query(""), category: str = "", level: str = "",
                  user: dict = Depends(current_user)) -> list:
    db.log_activity(user["email"], "search", q[:80])
    return db.search_decisions(q, states=("published",), category=category, level=level)


@app.get("/api/decisions/{doc_id}")
def client_decision(doc_id: str, user: dict = Depends(current_user)) -> dict:
    d = db.get_decision(doc_id, body=True)
    if not d or d["state"] != "published":            # not guessable into unpublished data
        raise HTTPException(status_code=404, detail="Not found")
    # only expose links whose target is also published
    d["links"] = [l for l in db.links_for(doc_id)
                  if (db.get_decision(l["to"]) or {}).get("state") == "published"]
    db.log_activity(user["email"], "view", doc_id)
    return d


@app.get("/api/decisions/{doc_id}/file")
def client_file(doc_id: str, authorization: Optional[str] = Header(None),
                token: str = "") -> StreamingResponse:
    user = _flex_user(authorization, token)
    d = db.get_decision(doc_id)
    if not d or d["state"] != "published":            # clients get published files only
        raise HTTPException(status_code=404, detail="Not found")
    db.log_activity(user["email"], "download", doc_id)
    return _serve_file(doc_id)
