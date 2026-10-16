"""A ruling's hand edits: every applied change is a version that can be restored, a
change that adds text waits as a draft until approved, and readers' reports of a
problem wait for an admin. The tables are in db.py; the rules are in docedit.py.
"""
from __future__ import annotations

import datetime as dt
from typing import List, Optional

from sqlalchemy import func, or_, select, update

import db
import textnorm


class Conflict(Exception):
    """The ruling changed since the edit was prepared."""


def editing_state(doc_id: str) -> Optional[dict]:
    with db.session() as s:
        d = s.get(db.Decision, doc_id)
        if not d:
            return None
        return {"doc_id": d.doc_id, "version": d.version or 0, "body_text": d.body_text,
                "file_name": d.file_name, "court": d.court, "category": d.category}


def apply_version(doc_id: str, *, base_version: int, current_file: bytes, new_file: bytes,
                  new_text: str, actor: str, action: str, summary: str,
                  restore_of: Optional[int] = None, draft_id: Optional[int] = None) -> int:
    """Make new_text/new_file the live ruling, in one transaction. Returns the new version.

    The first edit also records the ruling as imported (version 1), so it can always be
    restored. The decision row is only updated while it is still at base_version, and a
    version number can be taken once: of two admins saving at the same moment, the
    second gets Conflict instead of silently replacing the first.
    """
    from sqlalchemy.exc import IntegrityError

    now = dt.datetime.utcnow()
    with db.session() as s:
        d = s.get(db.Decision, doc_id)
        if d is None:
            raise LookupError(doc_id)
        if (d.version or 0) != base_version:
            raise Conflict(doc_id)
        if base_version == 0:
            s.add(db.DecisionVersion(doc_id=doc_id, version=1, status="applied", action="import",
                                  summary="as imported", actor="pipeline", base_version=0,
                                  body_text=d.body_text, file_data=current_file,
                                  created_at=d.created_at or now))
        new_version = max(base_version, 1) + 1
        if draft_id is not None:
            v = s.get(db.DecisionVersion, draft_id)
            if v is None or v.doc_id != doc_id or v.status != "draft":
                raise LookupError(draft_id)
            v.version, v.status, v.decided_by, v.decided_at = new_version, "applied", actor, now
            v.body_text, v.file_data = new_text, new_file
        else:
            s.add(db.DecisionVersion(doc_id=doc_id, version=new_version, status="applied",
                                  action=action, summary=summary, actor=actor,
                                  base_version=base_version, restore_of=restore_of,
                                  body_text=new_text, file_data=new_file, decided_by=actor,
                                  decided_at=now))
        done = s.execute(
            update(db.Decision)
            .where(db.Decision.doc_id == doc_id, db.Decision.version == d.version)
            .values(version=new_version, body_text=new_text,
                    search_text=textnorm.normalize(new_text),
                    edited_at=now, edited_by=actor, updated_at=now)
            .execution_options(synchronize_session=False))
        if done.rowcount != 1:
            s.rollback()
            raise Conflict(doc_id)
        s.add(db.AuditLog(actor=actor, action=action, entity="decision", entity_id=doc_id,
                       field="text", old_value=f"v{max(base_version, 1)}",
                       new_value=f"v{new_version}: {summary}"))
        try:
            s.commit()
        except IntegrityError:
            s.rollback()
            raise Conflict(doc_id)
        return new_version


def add_draft(doc_id: str, *, base_version: int, text: str, actor: str, action: str,
              summary: str, restore_of: Optional[int] = None) -> int:
    with db.session() as s:
        v = db.DecisionVersion(doc_id=doc_id, version=None, status="draft", action=action,
                            summary=summary, actor=actor, base_version=base_version,
                            restore_of=restore_of, body_text=text)
        s.add(v)
        s.add(db.AuditLog(actor=actor, action="draft", entity="decision", entity_id=doc_id,
                       field="text", old_value=f"v{base_version}", new_value=summary))
        s.commit()
        return v.id


def _version_dict(v: db.DecisionVersion, *, full: bool = False) -> dict:
    r = {"id": v.id, "doc_id": v.doc_id, "version": v.version, "status": v.status,
         "action": v.action, "summary": v.summary, "actor": v.actor,
         "created_at": v.created_at.isoformat() if v.created_at else "",
         "base_version": v.base_version, "restore_of": v.restore_of,
         "decided_by": v.decided_by,
         "decided_at": v.decided_at.isoformat() if v.decided_at else ""}
    if full:
        r["body_text"], r["file_data"] = v.body_text, v.file_data
    return r


def get_version_row(row_id: int) -> Optional[dict]:
    with db.session() as s:
        v = s.get(db.DecisionVersion, row_id)
        return _version_dict(v, full=True) if v else None


def version_by_number(doc_id: str, version: int) -> Optional[dict]:
    with db.session() as s:
        v = s.scalar(select(db.DecisionVersion).where(db.DecisionVersion.doc_id == doc_id,
                                                   db.DecisionVersion.version == version,
                                                   db.DecisionVersion.status == "applied"))
        return _version_dict(v, full=True) if v else None


def history(doc_id: str) -> dict:
    """Versions newest first, and the drafts still waiting -- no text, no files."""
    with db.session() as s:
        rows = list(s.scalars(select(db.DecisionVersion)
                              .where(db.DecisionVersion.doc_id == doc_id,
                                     db.DecisionVersion.status.in_(("applied", "draft")))
                              .order_by(db.DecisionVersion.id.desc())))
        versions = sorted((v for v in rows if v.status == "applied"),
                          key=lambda v: v.version or 0, reverse=True)
        return {"versions": [_version_dict(v) for v in versions],
                "drafts": [_version_dict(v) for v in rows if v.status == "draft"]}


def discard_draft(row_id: int, actor: str) -> bool:
    with db.session() as s:
        v = s.get(db.DecisionVersion, row_id)
        if v is None or v.status != "draft":
            return False
        v.status, v.decided_by, v.decided_at = "discarded", actor, dt.datetime.utcnow()
        v.body_text = ""                     # a refused edit may carry a name: keep nothing
        s.add(db.AuditLog(actor=actor, action="discard", entity="decision", entity_id=v.doc_id,
                       field="text", new_value=v.summary))
        s.commit()
        return True


def purge_history(doc_id: str, actor: str) -> int:
    """Delete every earlier version of a ruling, keeping the live one.

    Undo needs the old text, and the old text still holds whatever was hidden since.
    Once an admin is sure of a hide, this removes the last copy of the name.
    """
    with db.session() as s:
        d = s.get(db.Decision, doc_id)
        if d is None:
            return 0
        old = list(s.scalars(select(db.DecisionVersion).where(
            db.DecisionVersion.doc_id == doc_id,
            or_(db.DecisionVersion.status == "discarded",
                (db.DecisionVersion.status == "applied")
                & (db.DecisionVersion.version < (d.version or 0))))))
        for v in old:
            s.delete(v)
        s.add(db.AuditLog(actor=actor, action="purge_history", entity="decision", entity_id=doc_id,
                       field="text", new_value=f"{len(old)} earlier version(s) deleted"))
        s.commit()
        return len(old)


def pending_drafts(limit: int = 200) -> List[dict]:
    with db.session() as s:
        rows = s.execute(select(db.DecisionVersion, db.Decision.decision_no, db.Decision.category)
                         .join(db.Decision, db.Decision.doc_id == db.DecisionVersion.doc_id)
                         .where(db.DecisionVersion.status == "draft")
                         .order_by(db.DecisionVersion.created_at).limit(limit))
        return [dict(_version_dict(v), decision_no=no, category=cat) for v, no, cat in rows]


MAX_OPEN_REPORTS_PER_READER = 50


def add_report(doc_id: str, reporter: str, quote: str, note: str) -> Optional[int]:
    with db.session() as s:
        open_mine = s.scalar(select(func.count()).select_from(db.Report).where(
            db.Report.reporter == reporter, db.Report.status == "open")) or 0
        if open_mine >= MAX_OPEN_REPORTS_PER_READER:
            return None
        r = db.Report(doc_id=doc_id, reporter=reporter, quote=quote[:500], note=note[:1000])
        s.add(r)
        s.commit()
        return r.id


def list_reports(status: str = "open", doc_id: str = "", limit: int = 200) -> List[dict]:
    with db.session() as s:
        q = (select(db.Report, db.Decision.decision_no, db.Decision.category)
             .join(db.Decision, db.Decision.doc_id == db.Report.doc_id))
        if status:
            q = q.where(db.Report.status == status)
        if doc_id:
            q = q.where(db.Report.doc_id == doc_id)
        q = q.order_by(db.Report.created_at.desc()).limit(limit)
        return [{"id": r.id, "doc_id": r.doc_id, "decision_no": no, "category": cat,
                 "reporter": r.reporter, "quote": r.quote, "note": r.note, "status": r.status,
                 "created_at": r.created_at.isoformat() if r.created_at else "",
                 "resolved_by": r.resolved_by,
                 "resolved_at": r.resolved_at.isoformat() if r.resolved_at else ""}
                for r, no, cat in s.execute(q)]


def resolve_report(report_id: int, status: str, actor: str) -> bool:
    if status not in ("resolved", "dismissed"):
        return False
    with db.session() as s:
        r = s.get(db.Report, report_id)
        if r is None:
            return False
        r.status, r.resolved_by, r.resolved_at = status, actor, dt.datetime.utcnow()
        r.quote = ""                          # the quoted text is usually the name itself
        s.add(db.AuditLog(actor=actor, action=f"report_{status}", entity="decision",
                       entity_id=r.doc_id, field="report", new_value=str(report_id)))
        s.commit()
        return True


def edited_decisions() -> List[dict]:
    with db.session() as s:
        return [db._dec_dict(d) for d in s.scalars(
            select(db.Decision).where(db.Decision.edited_at.is_not(None)).order_by(db.Decision.doc_id))]


def attach_draft_file(row_id: int, data: bytes) -> None:
    """A draft that is a whole uploaded file keeps the file, to apply it as given."""
    with db.session() as s:
        v = s.get(db.DecisionVersion, row_id)
        if v is not None and v.status == "draft":
            v.file_data = data
            s.commit()


