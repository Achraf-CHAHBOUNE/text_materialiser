"""The admin's side of a ruling: the review queue, publishing, correcting the text and
the Word file together, drafts, readers' reports, and the export of every correction."""
from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import db
import versions
import docedit
import piigate
import storage
from deps import flex_user, require_editor, require_staff

router = APIRouter()


@router.get("/api/admin/decisions")
def admin_decisions(state: str = "", category: str = "", level: str = "",
                    limit: int = 200, offset: int = 0,
                    _: dict = Depends(require_editor)) -> list:
    states = (state,) if state else None
    return db.list_decisions(states=states, category=category, level=level,
                             limit=limit, offset=offset)


@router.get("/api/admin/queue")
def admin_queue(_: dict = Depends(require_editor)) -> list:
    return db.work_queue()


@router.get("/api/admin/stats")
def admin_stats(_: dict = Depends(require_staff)) -> dict:
    return db.counts()


@router.get("/api/admin/decisions/{doc_id}")
def admin_decision(doc_id: str, _: dict = Depends(require_editor)) -> dict:
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
    if "category" in changes and changes["category"] not in (*db.CATEGORIES, "غير محدد"):
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


@router.patch("/api/admin/decisions/{doc_id}")
def admin_correct(doc_id: str, body: FieldPatch, user: dict = Depends(require_editor)) -> dict:
    _check_fields(body.changes)
    d = db.update_decision_fields(doc_id, body.changes, user["email"])
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    old_court, old_chamber = d.pop("_old_title_parts")
    old_title = docedit.title_for(old_court, old_chamber)
    new_title = docedit.title_for(d["court"], d["category"])
    if old_title != new_title:
        st = versions.editing_state(doc_id)
        if st and st["file_name"].lower().endswith(".docx"):
            current = storage.STORE.get(st["file_name"])
            done = docedit.retitle(current, old_title, new_title)
            if done:
                new_file, text = done
                try:
                    versions.apply_version(doc_id, base_version=st["version"], current_file=current,
                                     new_file=new_file, new_text=text, actor=user["email"],
                                     action="title", summary=new_title)
                    storage.STORE.put(st["file_name"], new_file)
                except versions.Conflict:
                    raise HTTPException(status_code=409, detail=CONFLICT)
    return db.get_decision(doc_id, body=True) or d


class StateBody(BaseModel):
    state: str


@router.post("/api/admin/decisions/{doc_id}/state")
def admin_set_state(doc_id: str, body: StateBody, user: dict = Depends(require_editor)) -> dict:
    d = db.set_decision_state(doc_id, body.state, user["email"])
    if not d:
        raise HTTPException(status_code=400, detail="Unknown decision or state")
    return d


@router.post("/api/admin/decisions/{doc_id}/file")
async def admin_replace_file(doc_id: str, file: UploadFile = File(...),
                             user: dict = Depends(require_editor)) -> dict:
    """Correct/replace the anonymized file itself (§I-4), re-checked by the gate."""
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Upload a Word (.docx) file")
    st = versions.editing_state(doc_id)
    if not st:
        raise HTTPException(status_code=404, detail="Not found")
    data = await file.read()
    text = docedit.read_text(data)
    _gate(text)
    return _save_edit(st, text, user["email"], "replace_file", new_file=data)


@router.get("/api/admin/decisions/{doc_id}/file")
def admin_file(doc_id: str, request: Request, authorization: Optional[str] = Header(None),
               token: str = "") -> StreamingResponse:
    user = flex_user(request, authorization, token)
    if user["role"] not in ("admin", "editor"):
        raise HTTPException(status_code=403, detail="Editors only")
    return storage.serve(doc_id)


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
    st = versions.editing_state(doc_id)
    if not st:
        raise HTTPException(status_code=404, detail="Not found")
    if base_version is not None and st["version"] != base_version:
        raise HTTPException(status_code=409, detail=CONFLICT)
    if not st["file_name"].lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only Word (.docx) rulings can be edited here")
    return st


def _outcome(doc_id: str, **extra) -> dict:
    return dict(extra, decision=db.get_decision(doc_id, body=True), history=versions.history(doc_id))


def _go_live(st: dict, new_text: str, actor: str, action: str, summary: str, *,
             new_file: Optional[bytes] = None, restore_of: Optional[int] = None,
             draft_id: Optional[int] = None) -> int:
    current = storage.STORE.get(st["file_name"])
    if new_file is None:
        new_file, new_text = docedit.apply_to_docx(current, new_text)
    else:
        new_text = docedit.read_text(new_file)
    _gate(new_text)
    try:
        version = versions.apply_version(st["doc_id"], base_version=st["version"], current_file=current,
                                   new_file=new_file, new_text=new_text, actor=actor,
                                   action=action, summary=summary, restore_of=restore_of,
                                   draft_id=draft_id)
    except versions.Conflict:
        raise HTTPException(status_code=409, detail=CONFLICT)
    storage.STORE.put(st["file_name"], new_file)        # after the commit: the database decides
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
    draft = versions.add_draft(st["doc_id"], base_version=st["version"], text=new_text, actor=actor,
                         action=action, summary=summary, restore_of=restore_of)
    if new_file is not None:
        versions.attach_draft_file(draft, new_file)
    return _outcome(st["doc_id"], applied=False, draft_id=draft)


class HideBody(BaseModel):
    value: str
    base_version: int
    occurrence: int = 0
    everywhere: bool = False
    dry_run: bool = False


@router.post("/api/admin/decisions/{doc_id}/hide")
def admin_hide(doc_id: str, body: HideBody, user: dict = Depends(require_editor)) -> dict:
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


@router.post("/api/admin/decisions/{doc_id}/text")
def admin_edit_text(doc_id: str, body: TextBody, user: dict = Depends(require_editor)) -> dict:
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


@router.post("/api/admin/decisions/{doc_id}/restore")
def admin_restore(doc_id: str, body: RestoreBody, user: dict = Depends(require_editor)) -> dict:
    """Go back to an earlier version. If that brings back hidden text, it is a draft."""
    st = _editable(doc_id, body.base_version)
    target = versions.version_by_number(doc_id, body.version)
    if not target or target["file_data"] is None:
        raise HTTPException(status_code=404, detail="No such version")
    return _save_edit(st, target["body_text"], user["email"], "restore",
                      new_file=target["file_data"], restore_of=body.version)


@router.get("/api/admin/decisions/{doc_id}/history")
def admin_history(doc_id: str, _: dict = Depends(require_editor)) -> dict:
    if not db.get_decision(doc_id):
        raise HTTPException(status_code=404, detail="Not found")
    return dict(versions.history(doc_id), reports=versions.list_reports(status="open", doc_id=doc_id))


@router.get("/api/admin/decisions/{doc_id}/versions/{version}")
def admin_version_diff(doc_id: str, version: int, _: dict = Depends(require_editor)) -> dict:
    """What restoring this version would change, against the live text."""
    st = _editable(doc_id, None)
    target = versions.version_by_number(doc_id, version)
    if not target:
        raise HTTPException(status_code=404, detail="No such version")
    return {"removal": docedit.is_removal(st["body_text"], target["body_text"]),
            "diff": docedit.diff(st["body_text"], target["body_text"])}


@router.post("/api/admin/decisions/{doc_id}/purge-history")
def admin_purge_history(doc_id: str, user: dict = Depends(require_editor)) -> dict:
    return _outcome(doc_id, deleted=versions.purge_history(doc_id, user["email"]))


@router.get("/api/admin/drafts")
def admin_drafts(_: dict = Depends(require_editor)) -> list:
    return versions.pending_drafts()


def _draft(draft_id: int) -> dict:
    v = versions.get_version_row(draft_id)
    if not v or v["status"] != "draft":
        raise HTTPException(status_code=404, detail="No such draft")
    return v


@router.get("/api/admin/drafts/{draft_id}")
def admin_draft(draft_id: int, _: dict = Depends(require_editor)) -> dict:
    v = _draft(draft_id)
    st = _editable(v["doc_id"], None)
    stale = v["base_version"] != st["version"]
    v.pop("file_data")
    text = v.pop("body_text")
    return dict(v, stale=stale, diff=docedit.diff(st["body_text"], text),
                gate=[f"{f.type}: {f.value}" for f in piigate.scan(text)[:5]])


@router.post("/api/admin/drafts/{draft_id}/approve")
def admin_approve_draft(draft_id: int, user: dict = Depends(require_editor)) -> dict:
    v = _draft(draft_id)
    st = _editable(v["doc_id"], v["base_version"])      # 409 if the ruling moved on
    version = _go_live(st, v["body_text"], user["email"], v["action"], v["summary"],
                       new_file=v["file_data"], restore_of=v["restore_of"], draft_id=draft_id)
    return _outcome(v["doc_id"], applied=True, version=version)


@router.post("/api/admin/drafts/{draft_id}/discard")
def admin_discard_draft(draft_id: int, user: dict = Depends(require_editor)) -> dict:
    v = _draft(draft_id)
    versions.discard_draft(draft_id, user["email"])
    return _outcome(v["doc_id"], applied=False)


class ReportStatus(BaseModel):
    status: str


@router.get("/api/admin/reports")
def admin_reports(status: str = "open", _: dict = Depends(require_editor)) -> list:
    return versions.list_reports(status=status)


@router.post("/api/admin/reports/{report_id}")
def admin_resolve_report(report_id: int, body: ReportStatus,
                         user: dict = Depends(require_editor)) -> dict:
    if not versions.resolve_report(report_id, body.status, user["email"]):
        raise HTTPException(status_code=400, detail="Unknown report or status")
    return {"ok": True}


@router.get("/api/admin/edits/export")
def admin_export_edits(request: Request, authorization: Optional[str] = Header(None),
                       token: str = "") -> StreamingResponse:
    """Every hand-edited ruling as a zip -- edits.json plus the edited Word files --
    for the pipeline to fold into results/ (python -m anonymizer.assemble --edits)."""
    user = flex_user(request, authorization, token)
    if user["role"] not in ("admin", "editor"):
        raise HTTPException(status_code=403, detail="Editors only")
    buf = io.BytesIO()
    rows = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for d in versions.edited_decisions():
            if not d["file_name"] or not storage.STORE.exists(d["file_name"]):
                continue
            z.writestr(f"files/{d['file_name']}", storage.STORE.get(d["file_name"]))
            rows.append({k: d[k] for k in (
                "doc_id", "file_name", "version", "edited_at", "edited_by", "court", "category",
                "decision_no", "file_no", "date", "city", "year")})
        z.writestr("edits.json", json.dumps(rows, ensure_ascii=False, indent=2))
    db.add_audit(user["email"], "export_edits", "batch", "edits", new=f"{len(rows)} ruling(s)")
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={
        "Content-Disposition": 'attachment; filename="edits.zip"'})
