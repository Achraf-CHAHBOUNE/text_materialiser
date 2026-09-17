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
import re
import zipfile
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import auth as authmod
import db
import docedit
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
    rejected, quarantined, kept_edited = [], [], []
    for rec in records:
        doc_id = rec.get("doc_id")
        # The pipeline's leak gate is the only check that knows which real names
        # survived; a file it held back carries one in plain text, which the pattern
        # scan below cannot recognise. Never import it, whatever the zip contains.
        if rec.get("quarantined") or rec.get("status") == "quarantined":
            quarantined.append({"doc_id": doc_id, "findings": ["held by the pipeline"]})
            continue
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
        kept = not db.upsert_decision({
            "doc_id": doc_id, "source_file": rec.get("source_file", ""),
            "fmt": rec.get("format", ""), "read_method": rec.get("read_method", ""),
            "category": cat or "غير محدد", "level": rec.get("level", ""),
            "court": rec.get("court", ""),
            "decision_no": fv("رقم القرار"), "file_no": fv("رقم الملف"),
            "decision_date": fv("تاريخ القرار"),
            "city": rec.get("city") or fv("المدينة"),
            "year": rec.get("year") or fv("تاريخ القرار")[-4:],
            "case_id": rec.get("case_id", ""),
            "outcome": rec.get("outcome", ""),
            "pii_removed": rec.get("pii", {}).get("removed_count", 0),
            "review": rec.get("review", "ok"),
        }, body_text=text, file_name=fname)
        if kept:                     # edited by hand: its text and file stay as edited
            kept_edited.append(doc_id)
            continue
        db.set_links(doc_id, rec.get("links", []))
        STORE.put(fname, data)
        if AUTO_PUBLISH:                       # publish directly — no manual pending step
            db.set_decision_state(doc_id, "published", user["email"])
        imported += 0 if existed else 1
        updated += 1 if existed else 0

    db.add_audit(user["email"], "import", "batch", rec_name,
                 new=f"imported={imported} updated={updated} "
                     f"rejected={len(rejected)} quarantined={len(quarantined)} "
                     f"kept_edited={len(kept_edited)}")
    return {"imported": imported, "updated": updated,
            "rejected": rejected, "quarantined": quarantined,
            "kept_edited": kept_edited, "total_records": len(records)}


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


COURTS = ("محكمة النقض", "محكمة الاستئناف", "المحكمة الابتدائية", "المحكمة الدستورية",
          "المجلس الأعلى للحسابات")
_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def _check_fields(changes: dict) -> None:
    """The court and chamber are written into the Word file's title, so they come from
    fixed lists: a free-text title is one more place a name could be typed."""
    bad = {}
    if "category" in changes and changes["category"] not in (*CATEGORIES, "غير محدد"):
        bad["category"] = "unknown chamber"
    if "court" in changes and changes["court"] not in COURTS:
        bad["court"] = "unknown court"
    date = str(changes.get("decision_date") or "")
    if date and not _DATE.match(date):
        bad["decision_date"] = "use DD/MM/YYYY"
    year = str(changes.get("year") or "")
    if year and not (year.isdigit() and len(year) == 4):
        bad["year"] = "use four digits"
    if "review" in changes and changes["review"] not in ("ok", "check"):
        bad["review"] = "ok or check"
    for k in ("decision_no", "file_no", "city", "outcome"):
        if len(str(changes.get(k) or "")) > 200:
            bad[k] = "too long"
    if bad:
        raise HTTPException(status_code=422, detail={"fields": bad})


@app.patch("/api/admin/decisions/{doc_id}")
def admin_correct(doc_id: str, body: FieldPatch, user: dict = Depends(require_admin)) -> dict:
    _check_fields(body.changes)
    d = db.update_decision_fields(doc_id, body.changes, user["email"])
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    old_court, old_chamber = d.pop("_old_title_parts")
    old_title = docedit.title_for(old_court, old_chamber)
    new_title = docedit.title_for(d["court"], d["category"])
    if old_title != new_title:
        st = db.editing_state(doc_id)
        if st and st["file_name"].lower().endswith(".docx"):
            current = STORE.get(st["file_name"])
            done = docedit.retitle(current, old_title, new_title)
            if done:
                new_file, text = done
                try:
                    db.apply_version(doc_id, base_version=st["version"], current_file=current,
                                     new_file=new_file, new_text=text, actor=user["email"],
                                     action="title", summary=new_title)
                    STORE.put(st["file_name"], new_file)
                except db.Conflict:
                    raise HTTPException(status_code=409, detail=CONFLICT)
    return db.get_decision(doc_id, body=True) or d


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
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Upload a Word (.docx) file")
    st = db.editing_state(doc_id)
    if not st:
        raise HTTPException(status_code=404, detail="Not found")
    data = await file.read()
    text = docedit.read_text(data)
    _gate(text)
    return _save_edit(st, text, user["email"], "replace_file", new_file=data)


@app.get("/api/admin/decisions/{doc_id}/file")
def admin_file(doc_id: str, authorization: Optional[str] = Header(None),
               token: str = "") -> StreamingResponse:
    user = _flex_user(authorization, token)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return _serve_file(doc_id)


# ---------------- admin: editing a ruling ----------------
# Two paths, decided by what the change does, never by who asks:
#   removal (hiding) -> live at once;   anything that adds text -> a draft to approve.
# Every change is applied to the Word file itself, and every applied change is a
# version that can be restored. See docedit.py for the rules.
CONFLICT = "This ruling was changed by someone else meanwhile. Reload it and redo your edit."


def _gate(text: str) -> None:
    findings = piigate.scan(text)
    if findings:
        raise HTTPException(status_code=422, detail={
            "gate": [f"{f.type}: {f.value}" for f in findings[:5]]})


def _editable(doc_id: str, base_version: Optional[int]) -> dict:
    st = db.editing_state(doc_id)
    if not st:
        raise HTTPException(status_code=404, detail="Not found")
    if base_version is not None and st["version"] != base_version:
        raise HTTPException(status_code=409, detail=CONFLICT)
    if not st["file_name"].lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only Word (.docx) rulings can be edited here")
    return st


def _outcome(doc_id: str, **extra) -> dict:
    return dict(extra, decision=db.get_decision(doc_id, body=True), history=db.history(doc_id))


def _go_live(st: dict, new_text: str, actor: str, action: str, summary: str, *,
             new_file: Optional[bytes] = None, restore_of: Optional[int] = None,
             draft_id: Optional[int] = None) -> int:
    current = STORE.get(st["file_name"])
    if new_file is None:
        new_file, new_text = docedit.apply_to_docx(current, new_text)
    else:
        new_text = docedit.read_text(new_file)
    _gate(new_text)
    try:
        version = db.apply_version(st["doc_id"], base_version=st["version"], current_file=current,
                                   new_file=new_file, new_text=new_text, actor=actor,
                                   action=action, summary=summary, restore_of=restore_of,
                                   draft_id=draft_id)
    except db.Conflict:
        raise HTTPException(status_code=409, detail=CONFLICT)
    STORE.put(st["file_name"], new_file)        # after the commit: the database decides
    return version


def _save_edit(st: dict, new_text: str, actor: str, action: str, *,
               new_file: Optional[bytes] = None, restore_of: Optional[int] = None) -> dict:
    old = st["body_text"]
    if new_text == old:
        raise HTTPException(status_code=400, detail="Nothing changed")
    summary = docedit.summarize(old, new_text)
    if docedit.is_removal(old, new_text):
        version = _go_live(st, new_text, actor, action, summary,
                           new_file=new_file, restore_of=restore_of)
        return _outcome(st["doc_id"], applied=True, version=version)
    _gate(new_text)
    draft = db.add_draft(st["doc_id"], base_version=st["version"], text=new_text, actor=actor,
                         action=action, summary=summary, restore_of=restore_of)
    if new_file is not None:
        db.attach_draft_file(draft, new_file)
    return _outcome(st["doc_id"], applied=False, draft_id=draft)


class HideBody(BaseModel):
    value: str
    base_version: int
    occurrence: int = 0
    everywhere: bool = False
    dry_run: bool = False


@app.post("/api/admin/decisions/{doc_id}/hide")
def admin_hide(doc_id: str, body: HideBody, user: dict = Depends(require_admin)) -> dict:
    """Hide the selected text -- this occurrence, or every occurrence as a whole word."""
    st = _editable(doc_id, body.base_version)
    text = st["body_text"]
    try:
        if body.everywhere:
            spans = docedit.find_all(text, body.value)
            if body.dry_run:
                return {"count": len(spans), "snippets": docedit.snippets(text, spans)}
            if not spans:
                raise HTTPException(status_code=400, detail="Not found in this ruling")
            new_text, _ = docedit.hide_everywhere(text, body.value)
            action = "hide_all"
        else:
            new_text, action = docedit.hide_occurrence(text, body.value, body.occurrence), "hide"
    except docedit.EditError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _save_edit(st, new_text, user["email"], action)


class TextBody(BaseModel):
    text: str
    base_version: int
    dry_run: bool = False


@app.post("/api/admin/decisions/{doc_id}/text")
def admin_edit_text(doc_id: str, body: TextBody, user: dict = Depends(require_admin)) -> dict:
    """Save the whole text as edited. dry_run shows the change and where it would go."""
    st = _editable(doc_id, body.base_version)
    new_text = body.text.replace("\r\n", "\n").replace("\r", "\n")
    if body.dry_run:
        return {"removal": docedit.is_removal(st["body_text"], new_text),
                "summary": docedit.summarize(st["body_text"], new_text),
                "diff": docedit.diff(st["body_text"], new_text),
                "gate": [f"{f.type}: {f.value}" for f in piigate.scan(new_text)[:5]]}
    return _save_edit(st, new_text, user["email"], "edit")


class RestoreBody(BaseModel):
    version: int
    base_version: int


@app.post("/api/admin/decisions/{doc_id}/restore")
def admin_restore(doc_id: str, body: RestoreBody, user: dict = Depends(require_admin)) -> dict:
    """Go back to an earlier version. If that brings back hidden text, it is a draft."""
    st = _editable(doc_id, body.base_version)
    target = db.version_by_number(doc_id, body.version)
    if not target or target["file_data"] is None:
        raise HTTPException(status_code=404, detail="No such version")
    return _save_edit(st, target["body_text"], user["email"], "restore",
                      new_file=target["file_data"], restore_of=body.version)


@app.get("/api/admin/decisions/{doc_id}/history")
def admin_history(doc_id: str, _: dict = Depends(require_admin)) -> dict:
    if not db.get_decision(doc_id):
        raise HTTPException(status_code=404, detail="Not found")
    return dict(db.history(doc_id), reports=db.list_reports(status="open", doc_id=doc_id))


@app.get("/api/admin/decisions/{doc_id}/versions/{version}")
def admin_version_diff(doc_id: str, version: int, _: dict = Depends(require_admin)) -> dict:
    """What restoring this version would change, against the live text."""
    st = _editable(doc_id, None)
    target = db.version_by_number(doc_id, version)
    if not target:
        raise HTTPException(status_code=404, detail="No such version")
    return {"removal": docedit.is_removal(st["body_text"], target["body_text"]),
            "diff": docedit.diff(st["body_text"], target["body_text"])}


@app.post("/api/admin/decisions/{doc_id}/purge-history")
def admin_purge_history(doc_id: str, user: dict = Depends(require_admin)) -> dict:
    return _outcome(doc_id, deleted=db.purge_history(doc_id, user["email"]))


@app.get("/api/admin/drafts")
def admin_drafts(_: dict = Depends(require_admin)) -> list:
    return db.pending_drafts()


def _draft(draft_id: int) -> dict:
    v = db.get_version_row(draft_id)
    if not v or v["status"] != "draft":
        raise HTTPException(status_code=404, detail="No such draft")
    return v


@app.get("/api/admin/drafts/{draft_id}")
def admin_draft(draft_id: int, _: dict = Depends(require_admin)) -> dict:
    v = _draft(draft_id)
    st = _editable(v["doc_id"], None)
    stale = v["base_version"] != st["version"]
    v.pop("file_data")
    text = v.pop("body_text")
    return dict(v, stale=stale, diff=docedit.diff(st["body_text"], text),
                gate=[f"{f.type}: {f.value}" for f in piigate.scan(text)[:5]])


@app.post("/api/admin/drafts/{draft_id}/approve")
def admin_approve_draft(draft_id: int, user: dict = Depends(require_admin)) -> dict:
    v = _draft(draft_id)
    st = _editable(v["doc_id"], v["base_version"])      # 409 if the ruling moved on
    version = _go_live(st, v["body_text"], user["email"], v["action"], v["summary"],
                       new_file=v["file_data"], restore_of=v["restore_of"], draft_id=draft_id)
    return _outcome(v["doc_id"], applied=True, version=version)


@app.post("/api/admin/drafts/{draft_id}/discard")
def admin_discard_draft(draft_id: int, user: dict = Depends(require_admin)) -> dict:
    v = _draft(draft_id)
    db.discard_draft(draft_id, user["email"])
    return _outcome(v["doc_id"], applied=False)


class ReportStatus(BaseModel):
    status: str


@app.get("/api/admin/reports")
def admin_reports(status: str = "open", _: dict = Depends(require_admin)) -> list:
    return db.list_reports(status=status)


@app.post("/api/admin/reports/{report_id}")
def admin_resolve_report(report_id: int, body: ReportStatus,
                         user: dict = Depends(require_admin)) -> dict:
    if not db.resolve_report(report_id, body.status, user["email"]):
        raise HTTPException(status_code=400, detail="Unknown report or status")
    return {"ok": True}


@app.get("/api/admin/edits/export")
def admin_export_edits(authorization: Optional[str] = Header(None),
                       token: str = "") -> StreamingResponse:
    """Every hand-edited ruling as a zip -- edits.json plus the edited Word files --
    for the pipeline to fold into results/ (python -m anonymizer.assemble --edits)."""
    user = _flex_user(authorization, token)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    buf = io.BytesIO()
    rows = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for d in db.edited_decisions():
            if not d["file_name"] or not STORE.exists(d["file_name"]):
                continue
            z.writestr(f"files/{d['file_name']}", STORE.get(d["file_name"]))
            rows.append({k: d[k] for k in (
                "doc_id", "file_name", "version", "edited_at", "edited_by", "court", "category",
                "decision_no", "file_no", "date", "city", "year")})
        z.writestr("edits.json", json.dumps(rows, ensure_ascii=False, indent=2))
    db.add_audit(user["email"], "export_edits", "batch", "edits", new=f"{len(rows)} ruling(s)")
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={
        "Content-Disposition": 'attachment; filename="edits.zip"'})


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


# ---------------- client: browse (court > chamber > year > ruling) ----------------
@app.get("/api/browse/courts")
def browse_courts(_: dict = Depends(current_user)) -> list:
    """Every court with its chambers and their counts -- the menu page."""
    return db.browse_tree()


@app.get("/api/browse/years")
def browse_years(chamber: str = "", _: dict = Depends(current_user)) -> list:
    return db.browse_years(chamber)


@app.get("/api/browse/cities")
def browse_cities(chamber: str = "", _: dict = Depends(current_user)) -> list:
    return db.browse_cities(chamber)


@app.get("/api/browse/rulings")
def browse_rulings(chamber: str = "", year: str = "", city: str = "",
                   q: str = Query(""), limit: int = 50, offset: int = 0,
                   user: dict = Depends(current_user)) -> dict:
    """One page of the listing: number, date, city, chamber -- and the total."""
    if q.strip():
        db.log_activity(user["email"], "search", q[:80])
    return db.browse_rulings(chamber=chamber, year=year, city=city, q=q,
                             limit=min(limit, 200), offset=offset)


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


class ReportBody(BaseModel):
    quote: str = ""
    note: str = ""


@app.post("/api/decisions/{doc_id}/reports")
def client_report(doc_id: str, body: ReportBody, user: dict = Depends(current_user)) -> dict:
    """A reader flags a problem -- typically a name left visible -- for an admin."""
    d = db.get_decision(doc_id)
    if not d or d["state"] != "published":
        raise HTTPException(status_code=404, detail="Not found")
    if not (body.quote.strip() or body.note.strip()):
        raise HTTPException(status_code=400, detail="Select the text or describe the problem")
    rid = db.add_report(doc_id, user["email"], body.quote.strip(), body.note.strip())
    if rid is None:
        raise HTTPException(status_code=429, detail="Too many open reports; wait for them to be handled")
    return {"id": rid}


@app.get("/api/decisions/{doc_id}/file")
def client_file(doc_id: str, authorization: Optional[str] = Header(None),
                token: str = "") -> StreamingResponse:
    user = _flex_user(authorization, token)
    d = db.get_decision(doc_id)
    if not d or d["state"] != "published":            # clients get published files only
        raise HTTPException(status_code=404, detail="Not found")
    db.log_activity(user["email"], "download", doc_id)
    return _serve_file(doc_id)
