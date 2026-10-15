"""The firm module (cabinet): a law firm's own clients, cases, hearings, deadlines,
documents, time, expenses and fee notes -- and each case tied to the rulings it rests on.

This is the one part of the platform that holds real personal data: a firm's clients
are people with names, ID numbers and addresses. Everything here is therefore built
around four rules:

  1. A firm sees only its own records. The firm is always the signed-in person's
     organization -- never a value from the request -- and every query filters on it.
  2. Our own staff cannot read it. Not the admin, not sales, not the editors: a firm's
     case files are the firm's, and we only process them on its behalf (law 09-08:
     the firm is the data controller, we are its processor).
  3. A firm can erase. Deleting a client deletes its cases and everything under them,
     files included, for real -- the right to erasure is not a "deleted" flag.
  4. What happened is logged without what it was about: the audit trail records that
     a case was opened or a client erased, by whom and when, with ids -- never names.

Deadlines are computed from a date and a number of days, and moved to the next working
day when they fall on a weekend. The presets are the usual ones, but a deadline is a
lawyer's responsibility: each is marked to be verified until someone confirms it.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import re
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Date, DateTime, Integer, String, Text, UniqueConstraint, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

import billing
import db
from deps import CLIENTS, current_user

# Usual delays, in days, pre-filled when a deadline is added -- to be verified each time.
DEADLINE_PRESETS = {
    "opposition": 10,        # التعرض
    "appeal": 30,            # الاستئناف (civil)
    "appeal_criminal": 10,   # الاستئناف (pénal)
    "cassation": 30,         # النقض
    "other": 0,
}
LEVELS = ("ابتدائي", "استئناف", "نقض")


# ---------------- tables ----------------
class PClient(db.Base):
    __tablename__ = "practice_clients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String, default="person")      # person | company
    full_name: Mapped[str] = mapped_column(String, default="")
    cin: Mapped[str] = mapped_column(String, default="")             # national ID / RC for a company
    ice: Mapped[str] = mapped_column(String, default="")
    phone: Mapped[str] = mapped_column(String, default="")
    email: Mapped[str] = mapped_column(String, default="")
    address: Mapped[str] = mapped_column(String, default="")
    city: Mapped[str] = mapped_column(String, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class Matter(db.Base):
    __tablename__ = "matters"
    __table_args__ = (UniqueConstraint("org_id", "reference", name="uq_matter_ref"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    reference: Mapped[str] = mapped_column(String)                   # the firm's own: 2026/0001
    title: Mapped[str] = mapped_column(String, default="")
    client_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    client_role: Mapped[str] = mapped_column(String, default="")     # plaintiff | defendant | other
    opposing_party: Mapped[str] = mapped_column(String, default="")
    opposing_lawyer: Mapped[str] = mapped_column(String, default="")
    court: Mapped[str] = mapped_column(String, default="")
    chamber: Mapped[str] = mapped_column(String, default="")
    city: Mapped[str] = mapped_column(String, default="")
    level: Mapped[str] = mapped_column(String, default="")           # ابتدائي | استئناف | نقض
    case_number: Mapped[str] = mapped_column(String, default="")     # رقم الملف at the court
    kind: Mapped[str] = mapped_column(String, default="")            # civil, commercial, ...
    status: Mapped[str] = mapped_column(String, default="open", index=True)   # open|closed|archived
    responsible: Mapped[str] = mapped_column(String, default="")     # a member's email
    opened_on: Mapped[dt.date] = mapped_column(Date)
    closed_on: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    fee_agreement: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class Hearing(db.Base):
    __tablename__ = "hearings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    matter_id: Mapped[int] = mapped_column(Integer, index=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    time: Mapped[str] = mapped_column(String, default="")
    court: Mapped[str] = mapped_column(String, default="")
    room: Mapped[str] = mapped_column(String, default="")
    purpose: Mapped[str] = mapped_column(String, default="")
    outcome: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String, default="")


class Deadline(db.Base):
    __tablename__ = "deadlines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    matter_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String, default="other")
    start_on: Mapped[dt.date] = mapped_column(Date)          # the notification, usually
    days: Mapped[int] = mapped_column(Integer, default=0)
    due_on: Mapped[dt.date] = mapped_column(Date, index=True)
    note: Mapped[str] = mapped_column(String, default="")
    verified_by: Mapped[str] = mapped_column(String, default="")
    done_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(String, default="")


class PTask(db.Base):
    __tablename__ = "practice_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    matter_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String, default="")
    due_on: Mapped[dt.date] = mapped_column(Date, index=True)
    assigned_to: Mapped[str] = mapped_column(String, default="")
    done_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(String, default="")


class MatterDocument(db.Base):
    __tablename__ = "matter_documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    matter_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String, default="")
    file_key: Mapped[str] = mapped_column(String, unique=True)
    size: Mapped[int] = mapped_column(Integer, default=0)
    mime: Mapped[str] = mapped_column(String, default="")
    uploaded_by: Mapped[str] = mapped_column(String, default="")
    uploaded_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class TimeEntry(db.Base):
    __tablename__ = "time_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    matter_id: Mapped[int] = mapped_column(Integer, index=True)
    date: Mapped[dt.date] = mapped_column(Date)
    minutes: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(String, default="")
    rate: Mapped[int] = mapped_column(Integer, default=0)             # centimes an hour
    user: Mapped[str] = mapped_column(String, default="")
    fee_invoice_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class Expense(db.Base):
    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    matter_id: Mapped[int] = mapped_column(Integer, index=True)
    date: Mapped[dt.date] = mapped_column(Date)
    label: Mapped[str] = mapped_column(String, default="")           # court fees, bailiff, expert...
    amount: Mapped[int] = mapped_column(Integer, default=0)           # centimes
    user: Mapped[str] = mapped_column(String, default="")
    fee_invoice_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class FeeInvoice(db.Base):
    """A firm's note of fees (مذكرة الأتعاب) to its own client -- not our invoice."""
    __tablename__ = "fee_invoices"
    __table_args__ = (UniqueConstraint("org_id", "number", name="uq_fee_number"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    number: Mapped[str] = mapped_column(String)
    client_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    matter_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    lines: Mapped[str] = mapped_column(Text, default="[]")
    amount_ht: Mapped[int] = mapped_column(Integer, default=0)
    vat_rate: Mapped[int] = mapped_column(Integer, default=1000)     # lawyers' fees: 10% VAT
    vat: Mapped[int] = mapped_column(Integer, default=0)
    amount_ttc: Mapped[int] = mapped_column(Integer, default=0)
    issued_on: Mapped[dt.date] = mapped_column(Date)
    due_on: Mapped[dt.date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, default="sent", index=True)   # sent|paid|cancelled
    created_by: Mapped[str] = mapped_column(String, default="")


class FeePayment(db.Base):
    __tablename__ = "fee_payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    fee_invoice_id: Mapped[int] = mapped_column(Integer, index=True)
    amount: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String, default="transfer")
    reference: Mapped[str] = mapped_column(String, default="")
    paid_on: Mapped[dt.date] = mapped_column(Date)
    recorded_by: Mapped[str] = mapped_column(String, default="")


class MatterRuling(db.Base):
    __tablename__ = "matter_rulings"
    __table_args__ = (UniqueConstraint("matter_id", "doc_id", name="uq_matter_ruling"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    matter_id: Mapped[int] = mapped_column(Integer, index=True)
    doc_id: Mapped[str] = mapped_column(String)
    note: Mapped[str] = mapped_column(Text, default="")
    added_by: Mapped[str] = mapped_column(String, default="")
    added_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


# ---------------- who may enter ----------------
def firm(user: dict = Depends(current_user)) -> dict:
    """A member of a firm whose plan includes the module. Our staff are kept out."""
    if user["role"] not in CLIENTS or not user.get("org_id"):
        raise HTTPException(status_code=403, detail={"practice": "members only"})
    if not billing.has_practice(user["org_id"]):
        raise HTTPException(status_code=403, detail={"practice": "not in plan"})
    return user


def holder(user: dict = Depends(firm)) -> dict:
    """The firm's account holder: erasing a client or a case is theirs to decide."""
    if user["role"] != "client_admin":
        raise HTTPException(status_code=403, detail="Account holder only")
    return user


def _audit(user: dict, action: str, entity: str, entity_id) -> None:
    # ids only: a firm's audit trail must not become a second copy of its clients' names
    db.add_audit(user["email"], action, entity, f"{user['org_id']}:{entity_id}")


def _own(s, model, obj_id: int, user: dict):
    obj = s.get(model, obj_id)
    if obj is None or obj.org_id != user["org_id"]:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


def _row(obj, fields) -> dict:
    out = {}
    for f in fields:
        v = getattr(obj, f)
        out[f] = v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v
    return out


CLIENT_F = ("id", "kind", "full_name", "cin", "ice", "phone", "email", "address", "city", "notes",
            "created_by", "created_at")
MATTER_F = ("id", "reference", "title", "client_id", "client_role", "opposing_party", "opposing_lawyer",
            "court", "chamber", "city", "level", "case_number", "kind", "status", "responsible",
            "opened_on", "closed_on", "fee_agreement", "notes", "created_by", "created_at")
HEARING_F = ("id", "matter_id", "date", "time", "court", "room", "purpose", "outcome", "created_by")
DEADLINE_F = ("id", "matter_id", "kind", "start_on", "days", "due_on", "note", "verified_by", "done_at", "created_by")
TASK_F = ("id", "matter_id", "title", "due_on", "assigned_to", "done_at", "created_by")
DOC_F = ("id", "matter_id", "name", "size", "mime", "uploaded_by", "uploaded_at")
TIME_F = ("id", "matter_id", "date", "minutes", "description", "rate", "user", "fee_invoice_id")
EXP_F = ("id", "matter_id", "date", "label", "amount", "user", "fee_invoice_id")
FEE_F = ("id", "number", "client_id", "matter_id", "amount_ht", "vat_rate", "vat", "amount_ttc",
         "issued_on", "due_on", "status", "created_by")


def due_date(start: dt.date, days: int) -> dt.date:
    """start + days, moved to the Monday when it lands on a weekend."""
    d = start + dt.timedelta(days=days)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


# ---------------- routes ----------------
router = APIRouter(prefix="/api/practice")


def _date(v: Optional[str], name: str = "date") -> Optional[dt.date]:
    if not v:
        return None
    try:
        return dt.date.fromisoformat(v)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Bad {name}")


# -- clients --
class ClientBody(BaseModel):
    kind: Optional[str] = None
    full_name: Optional[str] = None
    cin: Optional[str] = None
    ice: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    notes: Optional[str] = None


@router.get("/clients")
def clients(q: str = "", user: dict = Depends(firm)) -> list:
    with db.session() as s:
        query = select(PClient).where(PClient.org_id == user["org_id"])
        if q.strip():
            like = f"%{q.strip()}%"
            query = query.where(or_(PClient.full_name.ilike(like), PClient.cin.ilike(like),
                                    PClient.phone.ilike(like), PClient.email.ilike(like)))
        rows = list(s.scalars(query.order_by(PClient.full_name).limit(1000)))
        counts = dict(s.execute(select(Matter.client_id, func.count()).where(
            Matter.org_id == user["org_id"], Matter.status == "open").group_by(Matter.client_id)).all())
        return [{**_row(c, CLIENT_F), "open_matters": counts.get(c.id, 0)} for c in rows]


@router.post("/clients")
def client_create(body: ClientBody, user: dict = Depends(firm)) -> dict:
    if not (body.full_name or "").strip():
        raise HTTPException(status_code=400, detail="Name required")
    with db.session() as s:
        c = PClient(org_id=user["org_id"], created_by=user["email"],
                    **{k: (v or "").strip() for k, v in body.model_dump(exclude_none=True).items()})
        if c.kind not in ("person", "company"):
            c.kind = "person"
        s.add(c)
        s.commit()
        out = _row(c, CLIENT_F)
    _audit(user, "create", "practice_client", out["id"])
    return out


@router.get("/clients/{client_id}")
def client_detail(client_id: int, user: dict = Depends(firm)) -> dict:
    with db.session() as s:
        c = _own(s, PClient, client_id, user)
        out = _row(c, CLIENT_F)
        out["matters"] = [_row(m, MATTER_F) for m in s.scalars(
            select(Matter).where(Matter.org_id == user["org_id"], Matter.client_id == client_id)
            .order_by(Matter.opened_on.desc()))]
        out["fee_invoices"] = _fee_rows(s, user, client_id=client_id)
    return out


@router.patch("/clients/{client_id}")
def client_update(client_id: int, body: ClientBody, user: dict = Depends(firm)) -> dict:
    with db.session() as s:
        c = _own(s, PClient, client_id, user)
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(c, k, v.strip() if isinstance(v, str) else v)
        s.commit()
        out = _row(c, CLIENT_F)
    _audit(user, "update", "practice_client", client_id)
    return out


@router.delete("/clients/{client_id}")
def client_erase(client_id: int, user: dict = Depends(holder)) -> dict:
    """Erase a client and everything under it, files included. Not undoable."""
    from server import STORE
    with db.session() as s:
        _own(s, PClient, client_id, user)
        matter_ids = list(s.scalars(select(Matter.id).where(Matter.org_id == user["org_id"],
                                                            Matter.client_id == client_id)))
        keys = _erase_matters(s, user, matter_ids)
        for f in s.scalars(select(FeeInvoice).where(FeeInvoice.org_id == user["org_id"],
                                                    FeeInvoice.client_id == client_id)):
            for p in s.scalars(select(FeePayment).where(FeePayment.fee_invoice_id == f.id)):
                s.delete(p)
            s.delete(f)
        s.delete(s.get(PClient, client_id))
        s.commit()
    for k in keys:
        try:
            STORE.delete(k)
        except Exception:
            pass
    _audit(user, "erase", "practice_client", client_id)
    return {"ok": True, "matters": len(matter_ids), "files": len(keys)}


def _erase_matters(s, user: dict, matter_ids: List[int]) -> List[str]:
    keys = []
    for model in (Hearing, Deadline, PTask, TimeEntry, Expense, MatterRuling):
        for row in s.scalars(select(model).where(model.org_id == user["org_id"],
                                                 model.matter_id.in_(matter_ids))):
            s.delete(row)
    for d in s.scalars(select(MatterDocument).where(MatterDocument.org_id == user["org_id"],
                                                    MatterDocument.matter_id.in_(matter_ids))):
        keys.append(d.file_key)
        s.delete(d)
    for m in s.scalars(select(Matter).where(Matter.org_id == user["org_id"], Matter.id.in_(matter_ids))):
        s.delete(m)
    return keys


# -- matters --
class MatterBody(BaseModel):
    title: Optional[str] = None
    client_id: Optional[int] = None
    client_role: Optional[str] = None
    opposing_party: Optional[str] = None
    opposing_lawyer: Optional[str] = None
    court: Optional[str] = None
    chamber: Optional[str] = None
    city: Optional[str] = None
    level: Optional[str] = None
    case_number: Optional[str] = None
    kind: Optional[str] = None
    status: Optional[str] = None
    responsible: Optional[str] = None
    opened_on: Optional[str] = None
    fee_agreement: Optional[str] = None
    notes: Optional[str] = None


def _check_member(user: dict, email: Optional[str]) -> None:
    if email:
        u = db.get_user(email)
        if not u or u.get("org_id") != user["org_id"]:
            raise HTTPException(status_code=400, detail="Not a member of the firm")


def _apply_matter(s, m: Matter, body: MatterBody, user: dict) -> None:
    data = body.model_dump(exclude_none=True)
    if "client_id" in data and data["client_id"]:
        _own(s, PClient, data["client_id"], user)
    if "level" in data and data["level"] and data["level"] not in LEVELS:
        raise HTTPException(status_code=400, detail="Level: ابتدائي, استئناف or نقض")
    if "status" in data and data["status"] not in ("open", "closed", "archived"):
        raise HTTPException(status_code=400, detail="Unknown status")
    _check_member(user, data.get("responsible"))
    for k, v in data.items():
        if k == "opened_on":
            v = _date(v, "opened_on") or m.opened_on
        if k == "status":
            m.closed_on = dt.date.today() if v != "open" else None
        setattr(m, k, v.strip() if isinstance(v, str) else v)


@router.get("/matters")
def matters(q: str = "", status: str = "open", client_id: Optional[int] = None,
            responsible: str = "", user: dict = Depends(firm)) -> list:
    today = dt.date.today()
    with db.session() as s:
        query = select(Matter, PClient.full_name).outerjoin(PClient, PClient.id == Matter.client_id) \
            .where(Matter.org_id == user["org_id"])
        if status:
            query = query.where(Matter.status == status)
        if client_id:
            query = query.where(Matter.client_id == client_id)
        if responsible:
            query = query.where(Matter.responsible == responsible)
        if q.strip():
            like = f"%{q.strip()}%"
            query = query.where(or_(Matter.title.ilike(like), Matter.reference.ilike(like),
                                    Matter.case_number.ilike(like), Matter.opposing_party.ilike(like),
                                    PClient.full_name.ilike(like)))
        rows = s.execute(query.order_by(Matter.opened_on.desc()).limit(1000)).all()
        ids = [m.id for m, _ in rows]
        nxt = dict(s.execute(select(Hearing.matter_id, func.min(Hearing.date)).where(
            Hearing.org_id == user["org_id"], Hearing.matter_id.in_(ids), Hearing.date >= today)
            .group_by(Hearing.matter_id)).all()) if ids else {}
        dl = dict(s.execute(select(Deadline.matter_id, func.min(Deadline.due_on)).where(
            Deadline.org_id == user["org_id"], Deadline.matter_id.in_(ids), Deadline.done_at.is_(None))
            .group_by(Deadline.matter_id)).all()) if ids else {}
    return [{**_row(m, MATTER_F), "client_name": name or "",
             "next_hearing": nxt[m.id].isoformat() if m.id in nxt else "",
             "next_deadline": dl[m.id].isoformat() if m.id in dl else ""} for m, name in rows]


@router.post("/matters")
def matter_create(body: MatterBody, user: dict = Depends(firm)) -> dict:
    if not (body.title or "").strip():
        raise HTTPException(status_code=400, detail="Title required")
    year = dt.date.today().year
    for _ in range(5):
        with db.session() as s:
            last = s.scalar(select(func.max(Matter.reference)).where(
                Matter.org_id == user["org_id"], Matter.reference.like(f"{year}/%")))
            n = int(last.split("/")[1]) + 1 if last else 1
            m = Matter(org_id=user["org_id"], reference=f"{year}/{n:04d}", opened_on=dt.date.today(),
                       responsible=user["email"], created_by=user["email"])
            _apply_matter(s, m, body, user)
            s.add(m)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                continue
            out = _row(m, MATTER_F)
        _audit(user, "create", "matter", out["id"])
        return out
    raise HTTPException(status_code=409, detail="Could not number the case; try again")


@router.get("/matters/{matter_id}")
def matter_detail(matter_id: int, lang: str = "ar", user: dict = Depends(firm)) -> dict:
    org = user["org_id"]
    with db.session() as s:
        m = _own(s, Matter, matter_id, user)
        out = _row(m, MATTER_F)
        c = s.get(PClient, m.client_id) if m.client_id else None
        out["client"] = _row(c, CLIENT_F) if c and c.org_id == org else None
        w = lambda model: select(model).where(model.org_id == org, model.matter_id == matter_id)  # noqa: E731
        out["hearings"] = [_row(x, HEARING_F) for x in s.scalars(w(Hearing).order_by(Hearing.date.desc()))]
        out["deadlines"] = [_row(x, DEADLINE_F) for x in s.scalars(w(Deadline).order_by(Deadline.due_on))]
        out["tasks"] = [_row(x, TASK_F) for x in s.scalars(w(PTask).order_by(PTask.done_at.is_not(None), PTask.due_on))]
        out["documents"] = [_row(x, DOC_F) for x in s.scalars(w(MatterDocument).order_by(MatterDocument.uploaded_at.desc()))]
        out["time"] = [_row(x, TIME_F) for x in s.scalars(w(TimeEntry).order_by(TimeEntry.date.desc()))]
        out["expenses"] = [_row(x, EXP_F) for x in s.scalars(w(Expense).order_by(Expense.date.desc()))]
        links = list(s.scalars(w(MatterRuling).order_by(MatterRuling.added_at.desc())))
        ids = [x.doc_id for x in links]
        decs = {d.doc_id: d for d in s.scalars(select(db.Decision).where(db.Decision.doc_id.in_(ids)))} if ids else {}
        extra = db.i18n_for(ids, lang) if lang != "ar" else {}
        out["rulings"] = []
        for x in links:
            d = decs.get(x.doc_id)
            if not d or d.state != "published":
                continue
            out["rulings"].append({"id": x.id, "doc_id": x.doc_id, "note": x.note, "added_by": x.added_by,
                                   "decision_no": d.decision_no, "date": d.decision_date, "chamber": d.category,
                                   "abstract": (d.rule if len(d.rule or "") > 80 else d.abstract) or "",
                                   "abstract_fr": (extra.get(x.doc_id) or {}).get("abstract", "")})
        out["fee_invoices"] = _fee_rows(s, user, matter_id=matter_id)
    unbilled = sum(round(t["minutes"] * t["rate"] / 60) for t in out["time"] if not t["fee_invoice_id"]) + \
        sum(e["amount"] for e in out["expenses"] if not e["fee_invoice_id"])
    out["unbilled"] = unbilled
    return out


@router.patch("/matters/{matter_id}")
def matter_update(matter_id: int, body: MatterBody, user: dict = Depends(firm)) -> dict:
    with db.session() as s:
        m = _own(s, Matter, matter_id, user)
        _apply_matter(s, m, body, user)
        s.commit()
        out = _row(m, MATTER_F)
    _audit(user, "update", "matter", matter_id)
    return out


@router.delete("/matters/{matter_id}")
def matter_erase(matter_id: int, user: dict = Depends(holder)) -> dict:
    from server import STORE
    with db.session() as s:
        _own(s, Matter, matter_id, user)
        keys = _erase_matters(s, user, [matter_id])
        s.commit()
    for k in keys:
        try:
            STORE.delete(k)
        except Exception:
            pass
    _audit(user, "erase", "matter", matter_id)
    return {"ok": True, "files": len(keys)}


# -- hearings, deadlines, tasks --
class HearingBody(BaseModel):
    date: Optional[str] = None
    time: Optional[str] = None
    court: Optional[str] = None
    room: Optional[str] = None
    purpose: Optional[str] = None
    outcome: Optional[str] = None
    next_date: Optional[str] = None       # the court set the next hearing: create it too


@router.post("/matters/{matter_id}/hearings")
def hearing_add(matter_id: int, body: HearingBody, user: dict = Depends(firm)) -> dict:
    with db.session() as s:
        m = _own(s, Matter, matter_id, user)
        day = _date(body.date)
        if not day:
            raise HTTPException(status_code=400, detail="Date required")
        h = Hearing(org_id=user["org_id"], matter_id=matter_id, date=day, time=body.time or "",
                    court=body.court or m.court, room=body.room or "", purpose=body.purpose or "",
                    outcome=body.outcome or "", created_by=user["email"])
        s.add(h)
        s.commit()
        return _row(h, HEARING_F)


@router.patch("/hearings/{hearing_id}")
def hearing_update(hearing_id: int, body: HearingBody, user: dict = Depends(firm)) -> dict:
    """Record what happened -- and, if the court set the next date, schedule it."""
    with db.session() as s:
        h = _own(s, Hearing, hearing_id, user)
        for k in ("time", "court", "room", "purpose", "outcome"):
            v = getattr(body, k)
            if v is not None:
                setattr(h, k, v)
        if body.date:
            h.date = _date(body.date)
        nxt = None
        if body.next_date:
            nxt = Hearing(org_id=h.org_id, matter_id=h.matter_id, date=_date(body.next_date, "next_date"),
                          court=h.court, room=h.room, purpose=body.purpose or "", created_by=user["email"])
            s.add(nxt)
        s.commit()
        out = _row(h, HEARING_F)
        if nxt:
            out["next"] = _row(nxt, HEARING_F)
        return out


@router.delete("/hearings/{hearing_id}")
def hearing_delete(hearing_id: int, user: dict = Depends(firm)) -> dict:
    with db.session() as s:
        s.delete(_own(s, Hearing, hearing_id, user))
        s.commit()
    return {"ok": True}


class DeadlineBody(BaseModel):
    kind: str = "other"
    start_on: Optional[str] = None
    days: Optional[int] = None
    due_on: Optional[str] = None
    note: str = ""


@router.get("/deadline-presets")
def deadline_presets(_: dict = Depends(firm)) -> dict:
    return DEADLINE_PRESETS


@router.post("/matters/{matter_id}/deadlines")
def deadline_add(matter_id: int, body: DeadlineBody, user: dict = Depends(firm)) -> dict:
    with db.session() as s:
        _own(s, Matter, matter_id, user)
        start = _date(body.start_on, "start_on") or dt.date.today()
        days = body.days if body.days is not None else DEADLINE_PRESETS.get(body.kind, 0)
        due = _date(body.due_on, "due_on") or due_date(start, days)
        if days < 0:
            raise HTTPException(status_code=400, detail="Days cannot be negative")
        d = Deadline(org_id=user["org_id"], matter_id=matter_id, kind=body.kind, start_on=start, days=days,
                     due_on=due, note=body.note, created_by=user["email"])
        s.add(d)
        s.commit()
        return _row(d, DEADLINE_F)


class DonePatch(BaseModel):
    done: Optional[bool] = None
    verified: Optional[bool] = None
    due_on: Optional[str] = None
    title: Optional[str] = None
    assigned_to: Optional[str] = None


@router.patch("/deadlines/{deadline_id}")
def deadline_update(deadline_id: int, body: DonePatch, user: dict = Depends(firm)) -> dict:
    with db.session() as s:
        d = _own(s, Deadline, deadline_id, user)
        if body.done is not None:
            d.done_at = dt.datetime.utcnow() if body.done else None
        if body.verified is not None:
            d.verified_by = user["email"] if body.verified else ""
        if body.due_on:
            d.due_on = _date(body.due_on, "due_on")
        s.commit()
        return _row(d, DEADLINE_F)


class TaskBody(BaseModel):
    title: str
    due_on: str
    matter_id: Optional[int] = None
    assigned_to: str = ""


@router.post("/tasks")
def task_add(body: TaskBody, user: dict = Depends(firm)) -> dict:
    with db.session() as s:
        if body.matter_id:
            _own(s, Matter, body.matter_id, user)
        _check_member(user, body.assigned_to)
        t = PTask(org_id=user["org_id"], matter_id=body.matter_id, title=body.title.strip()[:300],
                  due_on=_date(body.due_on, "due_on"), assigned_to=body.assigned_to or user["email"],
                  created_by=user["email"])
        s.add(t)
        s.commit()
        return _row(t, TASK_F)


@router.patch("/tasks/{task_id}")
def task_update(task_id: int, body: DonePatch, user: dict = Depends(firm)) -> dict:
    with db.session() as s:
        t = _own(s, PTask, task_id, user)
        if body.done is not None:
            t.done_at = dt.datetime.utcnow() if body.done else None
        if body.due_on:
            t.due_on = _date(body.due_on, "due_on")
        if body.title:
            t.title = body.title[:300]
        if body.assigned_to:
            _check_member(user, body.assigned_to)
            t.assigned_to = body.assigned_to
        s.commit()
        return _row(t, TASK_F)


# -- documents --
MAX_DOC = 20 * 1024 * 1024


@router.post("/matters/{matter_id}/documents")
async def document_upload(matter_id: int, file: UploadFile = File(...), user: dict = Depends(firm)) -> dict:
    from server import STORE
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_DOC:
        raise HTTPException(status_code=413, detail="20 MB at most")
    name = re.sub(r"[^\w.\- ]+", "_", file.filename or "document")[:120] or "document"
    with db.session() as s:
        _own(s, Matter, matter_id, user)
        # flat and ASCII: the store may be a plain folder, and a client's name in a
        # file name should live in the database, not in the storage's listing
        ext = re.sub(r"[^a-z0-9]", "", (name.rsplit(".", 1)[-1] if "." in name else "").lower())[:8]
        key = f"practice-{user['org_id']}-{matter_id}-{uuid.uuid4().hex}" + (f".{ext}" if ext else "")
        STORE.put(key, data)
        d = MatterDocument(org_id=user["org_id"], matter_id=matter_id, name=name, file_key=key,
                           size=len(data), mime=file.content_type or "", uploaded_by=user["email"])
        s.add(d)
        s.commit()
        out = _row(d, DOC_F)
    _audit(user, "upload", "matter_document", out["id"])
    return out


@router.get("/documents/{doc_id}")
def document_download(doc_id: int, user: dict = Depends(firm)) -> StreamingResponse:
    from server import STORE
    with db.session() as s:
        d = _own(s, MatterDocument, doc_id, user)
        key, name, mime = d.file_key, d.name, d.mime
    # an Arabic or accented name travels as RFC 5987, with a plain one for old browsers
    from urllib.parse import quote
    plain = name.encode("ascii", "replace").decode().replace("?", "_").replace('"', "")
    return StreamingResponse(io.BytesIO(STORE.get(key)), media_type=mime or "application/octet-stream",
                             headers={"Content-Disposition":
                                      f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(name)}"})


@router.delete("/documents/{doc_id}")
def document_delete(doc_id: int, user: dict = Depends(firm)) -> dict:
    from server import STORE
    with db.session() as s:
        d = _own(s, MatterDocument, doc_id, user)
        key = d.file_key
        s.delete(d)
        s.commit()
    try:
        STORE.delete(key)
    except Exception:
        pass
    _audit(user, "delete", "matter_document", doc_id)
    return {"ok": True}


# -- rulings tied to a case --
class LinkBody(BaseModel):
    doc_id: str
    note: str = ""


@router.post("/matters/{matter_id}/rulings")
def ruling_link(matter_id: int, body: LinkBody, user: dict = Depends(firm)) -> dict:
    d = db.get_decision(body.doc_id)
    if not d or d["state"] != "published":
        raise HTTPException(status_code=404, detail="Ruling not found")
    with db.session() as s:
        _own(s, Matter, matter_id, user)
        if s.scalar(select(MatterRuling).where(MatterRuling.matter_id == matter_id,
                                                MatterRuling.doc_id == body.doc_id)):
            return {"ok": True, "already": True}
        s.add(MatterRuling(org_id=user["org_id"], matter_id=matter_id, doc_id=body.doc_id,
                           note=body.note[:4000], added_by=user["email"]))
        s.commit()
    return {"ok": True}


@router.delete("/matter-rulings/{link_id}")
def ruling_unlink(link_id: int, user: dict = Depends(firm)) -> dict:
    with db.session() as s:
        s.delete(_own(s, MatterRuling, link_id, user))
        s.commit()
    return {"ok": True}


@router.get("/rulings/{doc_id}/matters")
def ruling_matters(doc_id: str, user: dict = Depends(firm)) -> list:
    """The firm's open cases, and whether this ruling is already tied to each."""
    with db.session() as s:
        linked = set(s.scalars(select(MatterRuling.matter_id).where(
            MatterRuling.org_id == user["org_id"], MatterRuling.doc_id == doc_id)))
        return [{"id": m.id, "reference": m.reference, "title": m.title, "linked": m.id in linked}
                for m in s.scalars(select(Matter).where(Matter.org_id == user["org_id"],
                                                        Matter.status == "open").order_by(Matter.reference.desc()))]


# -- time and expenses --
class TimeBody(BaseModel):
    date: Optional[str] = None
    minutes: int
    description: str = ""
    rate: int = 0


class ExpenseBody(BaseModel):
    date: Optional[str] = None
    label: str
    amount: int


@router.post("/matters/{matter_id}/time")
def time_add(matter_id: int, body: TimeBody, user: dict = Depends(firm)) -> dict:
    if body.minutes <= 0 or body.rate < 0:
        raise HTTPException(status_code=400, detail="Minutes must be positive")
    with db.session() as s:
        _own(s, Matter, matter_id, user)
        t = TimeEntry(org_id=user["org_id"], matter_id=matter_id, date=_date(body.date) or dt.date.today(),
                      minutes=body.minutes, description=body.description[:300], rate=body.rate,
                      user=user["email"])
        s.add(t)
        s.commit()
        return _row(t, TIME_F)


@router.post("/matters/{matter_id}/expenses")
def expense_add(matter_id: int, body: ExpenseBody, user: dict = Depends(firm)) -> dict:
    if body.amount <= 0 or not body.label.strip():
        raise HTTPException(status_code=400, detail="Label and a positive amount required")
    with db.session() as s:
        _own(s, Matter, matter_id, user)
        e = Expense(org_id=user["org_id"], matter_id=matter_id, date=_date(body.date) or dt.date.today(),
                    label=body.label.strip()[:200], amount=body.amount, user=user["email"])
        s.add(e)
        s.commit()
        return _row(e, EXP_F)


@router.delete("/time/{entry_id}")
def time_delete(entry_id: int, user: dict = Depends(firm)) -> dict:
    with db.session() as s:
        t = _own(s, TimeEntry, entry_id, user)
        if t.fee_invoice_id:
            raise HTTPException(status_code=409, detail="Already billed")
        s.delete(t)
        s.commit()
    return {"ok": True}


@router.delete("/expenses/{expense_id}")
def expense_delete(expense_id: int, user: dict = Depends(firm)) -> dict:
    with db.session() as s:
        e = _own(s, Expense, expense_id, user)
        if e.fee_invoice_id:
            raise HTTPException(status_code=409, detail="Already billed")
        s.delete(e)
        s.commit()
    return {"ok": True}


# -- fee notes to the firm's clients --
def _fee_rows(s, user: dict, client_id: Optional[int] = None, matter_id: Optional[int] = None,
              status: str = "") -> list:
    q = select(FeeInvoice).where(FeeInvoice.org_id == user["org_id"])
    if client_id:
        q = q.where(FeeInvoice.client_id == client_id)
    if matter_id:
        q = q.where(FeeInvoice.matter_id == matter_id)
    rows = list(s.scalars(q.order_by(FeeInvoice.issued_on.desc(), FeeInvoice.id.desc()).limit(1000)))
    paid = dict(s.execute(select(FeePayment.fee_invoice_id, func.sum(FeePayment.amount)).where(
        FeePayment.org_id == user["org_id"], FeePayment.fee_invoice_id.in_([r.id for r in rows]))
        .group_by(FeePayment.fee_invoice_id)).all()) if rows else {}
    names = dict(s.execute(select(PClient.id, PClient.full_name).where(
        PClient.org_id == user["org_id"], PClient.id.in_([r.client_id for r in rows if r.client_id]))).all()) if rows else {}
    out = []
    for r in rows:
        d = _row(r, FEE_F)
        d["lines"] = json.loads(r.lines or "[]")
        d["paid"] = int(paid.get(r.id, 0) or 0)
        d["balance"] = r.amount_ttc - d["paid"]
        d["client_name"] = names.get(r.client_id, "")
        if d["status"] == "sent" and r.due_on < dt.date.today():
            d["status"] = "overdue"
        if not status or d["status"] == status:
            out.append(d)
    return out


class FeeLine(BaseModel):
    label: str
    amount: int                      # centimes, before VAT


class FeeBody(BaseModel):
    matter_id: Optional[int] = None
    client_id: Optional[int] = None
    lines: List[FeeLine] = []
    include_unbilled: bool = True    # add the case's unbilled time and expenses
    vat_rate: int = 1000
    due_days: int = 30


@router.get("/fees")
def fees(status: str = "", user: dict = Depends(firm)) -> list:
    with db.session() as s:
        return _fee_rows(s, user, status=status)


@router.post("/fees")
def fee_create(body: FeeBody, user: dict = Depends(firm)) -> dict:
    lines = [ln.model_dump() for ln in body.lines if ln.label.strip() and ln.amount > 0]
    with db.session() as s:
        client_id = body.client_id
        if body.matter_id:
            m = _own(s, Matter, body.matter_id, user)
            client_id = client_id or m.client_id
        if client_id:
            _own(s, PClient, client_id, user)
        billed_time, billed_exp = [], []
        if body.matter_id and body.include_unbilled:
            for t in s.scalars(select(TimeEntry).where(TimeEntry.org_id == user["org_id"],
                                                       TimeEntry.matter_id == body.matter_id,
                                                       TimeEntry.fee_invoice_id.is_(None))):
                amount = round(t.minutes * t.rate / 60)
                if amount > 0:
                    lines.append({"label": f"{t.date.isoformat()} — {t.description or 'Diligences'} "
                                           f"({t.minutes // 60}h{t.minutes % 60:02d})", "amount": amount})
                billed_time.append(t)
            for e in s.scalars(select(Expense).where(Expense.org_id == user["org_id"],
                                                     Expense.matter_id == body.matter_id,
                                                     Expense.fee_invoice_id.is_(None))):
                lines.append({"label": f"{e.date.isoformat()} — {e.label}", "amount": e.amount})
                billed_exp.append(e)
        if not lines:
            raise HTTPException(status_code=400, detail="Nothing to bill")
        ht = sum(int(ln["amount"]) for ln in lines)
        vat = round(ht * body.vat_rate / 10000)
        year = dt.date.today().year
        last = s.scalar(select(func.max(FeeInvoice.number)).where(
            FeeInvoice.org_id == user["org_id"], FeeInvoice.number.like(f"{year}-%")))
        n = int(last.split("-")[1]) + 1 if last else 1
        f = FeeInvoice(org_id=user["org_id"], number=f"{year}-{n:04d}", client_id=client_id,
                       matter_id=body.matter_id, lines=json.dumps(lines, ensure_ascii=False),
                       amount_ht=ht, vat_rate=body.vat_rate, vat=vat, amount_ttc=ht + vat,
                       issued_on=dt.date.today(), due_on=dt.date.today() + dt.timedelta(days=body.due_days),
                       created_by=user["email"])
        s.add(f)
        try:
            s.flush()
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Could not number the fee note; try again")
        for row in billed_time + billed_exp:
            row.fee_invoice_id = f.id
        s.commit()
        fid = f.id
    _audit(user, "create", "fee_invoice", fid)
    return fee_detail(fid, user)


@router.get("/fees/{fee_id}")
def fee_detail(fee_id: int, user: dict = Depends(firm)) -> dict:
    with db.session() as s:
        f = _own(s, FeeInvoice, fee_id, user)
        out = next(r for r in _fee_rows(s, user, matter_id=f.matter_id, client_id=f.client_id) if r["id"] == fee_id)
        c = s.get(PClient, f.client_id) if f.client_id else None
        out["client"] = _row(c, CLIENT_F) if c and c.org_id == user["org_id"] else None
        m = s.get(Matter, f.matter_id) if f.matter_id else None
        out["matter"] = {"reference": m.reference, "title": m.title, "case_number": m.case_number} if m else None
        out["payments"] = [{"amount": p.amount, "method": p.method, "reference": p.reference,
                            "paid_on": p.paid_on.isoformat()} for p in s.scalars(
            select(FeePayment).where(FeePayment.fee_invoice_id == fee_id).order_by(FeePayment.paid_on))]
    import accounts
    out["firm"] = accounts.get_org(user["org_id"])
    return out


class FeePaymentBody(BaseModel):
    amount: int
    method: str = "transfer"
    reference: str = ""
    paid_on: Optional[str] = None


@router.post("/fees/{fee_id}/payments")
def fee_pay(fee_id: int, body: FeePaymentBody, user: dict = Depends(firm)) -> dict:
    if body.amount <= 0 or body.method not in ("transfer", "cheque", "cash", "card"):
        raise HTTPException(status_code=400, detail="Check the amount and the method")
    with db.session() as s:
        f = _own(s, FeeInvoice, fee_id, user)
        if f.status == "cancelled":
            raise HTTPException(status_code=409, detail="Cancelled")
        s.add(FeePayment(org_id=user["org_id"], fee_invoice_id=fee_id, amount=body.amount,
                         method=body.method, reference=body.reference,
                         paid_on=_date(body.paid_on, "paid_on") or dt.date.today(), recorded_by=user["email"]))
        s.flush()
        paid = s.scalar(select(func.sum(FeePayment.amount)).where(FeePayment.fee_invoice_id == fee_id)) or 0
        if paid >= f.amount_ttc:
            f.status = "paid"
        s.commit()
    return fee_detail(fee_id, user)


@router.post("/fees/{fee_id}/cancel")
def fee_cancel(fee_id: int, user: dict = Depends(firm)) -> dict:
    """Cancelled, never deleted; its time and expenses become billable again."""
    with db.session() as s:
        f = _own(s, FeeInvoice, fee_id, user)
        if s.scalar(select(func.count()).select_from(FeePayment).where(FeePayment.fee_invoice_id == fee_id)):
            raise HTTPException(status_code=409, detail="A fee note with payments cannot be cancelled")
        f.status = "cancelled"
        for model in (TimeEntry, Expense):
            for row in s.scalars(select(model).where(model.fee_invoice_id == fee_id)):
                row.fee_invoice_id = None
        s.commit()
    return fee_detail(fee_id, user)


# -- the agenda and the firm's dashboard --
@router.get("/agenda")
def agenda(start: Optional[str] = None, days: int = 14, mine: bool = False,
           user: dict = Depends(firm)) -> dict:
    """Hearings, deadlines and tasks between two dates, for the firm or for me."""
    first = _date(start, "start") or dt.date.today()
    last = first + dt.timedelta(days=max(1, min(days, 92)))
    org = user["org_id"]
    with db.session() as s:
        mq = select(Matter.id, Matter.reference, Matter.title, Matter.responsible).where(Matter.org_id == org)
        if mine:
            mq = mq.where(Matter.responsible == user["email"])
        info = {i: (ref, title, resp) for i, ref, title, resp in s.execute(mq).all()}
        ids = list(info)
        hearings = [_row(h, HEARING_F) for h in s.scalars(select(Hearing).where(
            Hearing.org_id == org, Hearing.matter_id.in_(ids), Hearing.date >= first, Hearing.date < last)
            .order_by(Hearing.date, Hearing.time))] if ids else []
        deadlines = [_row(d, DEADLINE_F) for d in s.scalars(select(Deadline).where(
            Deadline.org_id == org, Deadline.matter_id.in_(ids), Deadline.done_at.is_(None),
            Deadline.due_on < last).order_by(Deadline.due_on))] if ids else []
        tq = select(PTask).where(PTask.org_id == org, PTask.done_at.is_(None), PTask.due_on < last)
        if mine:
            tq = tq.where(PTask.assigned_to == user["email"])
        tasks = [_row(t, TASK_F) for t in s.scalars(tq.order_by(PTask.due_on))]
    for x in hearings + deadlines + tasks:
        ref = info.get(x.get("matter_id"))
        x["matter_reference"], x["matter_title"] = (ref[0], ref[1]) if ref else ("", "")
    return {"from": first.isoformat(), "to": last.isoformat(), "hearings": hearings,
            "deadlines": deadlines, "tasks": tasks}


@router.get("/dashboard")
def dashboard(user: dict = Depends(firm)) -> dict:
    today = dt.date.today()
    org = user["org_id"]
    with db.session() as s:
        open_matters = s.scalar(select(func.count()).select_from(Matter).where(
            Matter.org_id == org, Matter.status == "open")) or 0
        clients_n = s.scalar(select(func.count()).select_from(PClient).where(PClient.org_id == org)) or 0
        today_h = s.scalar(select(func.count()).select_from(Hearing).where(
            Hearing.org_id == org, Hearing.date == today)) or 0
        week_h = s.scalar(select(func.count()).select_from(Hearing).where(
            Hearing.org_id == org, Hearing.date >= today, Hearing.date < today + dt.timedelta(days=7))) or 0
        late = s.scalar(select(func.count()).select_from(Deadline).where(
            Deadline.org_id == org, Deadline.done_at.is_(None), Deadline.due_on < today)) or 0
        soon = s.scalar(select(func.count()).select_from(Deadline).where(
            Deadline.org_id == org, Deadline.done_at.is_(None), Deadline.due_on >= today,
            Deadline.due_on < today + dt.timedelta(days=14))) or 0
        unverified = s.scalar(select(func.count()).select_from(Deadline).where(
            Deadline.org_id == org, Deadline.done_at.is_(None), Deadline.verified_by == "")) or 0
        tasks_due = s.scalar(select(func.count()).select_from(PTask).where(
            PTask.org_id == org, PTask.done_at.is_(None), PTask.due_on <= today,
            PTask.assigned_to == user["email"])) or 0
        fees_ = _fee_rows(s, user)
    unpaid = sum(f["balance"] for f in fees_ if f["status"] in ("sent", "overdue"))
    month = today.replace(day=1)
    with db.session() as s:
        collected = s.scalar(select(func.sum(FeePayment.amount)).where(
            FeePayment.org_id == org, FeePayment.paid_on >= month)) or 0
    return {"open_matters": open_matters, "clients": clients_n, "hearings_today": today_h,
            "hearings_week": week_h, "deadlines_late": late, "deadlines_soon": soon,
            "deadlines_unverified": unverified, "my_tasks_due": tasks_due,
            "fees_unpaid": int(unpaid), "fees_overdue": sum(1 for f in fees_ if f["status"] == "overdue"),
            "collected_month": int(collected),
            "agenda": agenda(start=today.isoformat(), days=7, mine=False, user=user)}


@router.get("/members")
def members(user: dict = Depends(firm)) -> list:
    import accounts
    return [{"email": m["email"], "full_name": m["full_name"]} for m in accounts.org_members(user["org_id"])
            if m["status"] == "active"]


@router.get("/search")
def search(q: str, user: dict = Depends(firm)) -> dict:
    """One box over the firm's clients and cases."""
    if len(q.strip()) < 2:
        return {"clients": [], "matters": []}
    return {"clients": clients(q=q, user=user)[:10], "matters": matters(q=q, status="", user=user)[:10]}


# -- for the worker: each member's coming hearings and deadlines --
def digests(today: dt.date) -> List[tuple]:
    """(email, lang, body) for every member with a hearing in two days or a deadline
    within seven. Sent once a day by worker.py."""
    out = []
    with db.session() as s:
        rows = s.execute(select(Matter.id, Matter.org_id, Matter.reference, Matter.title, Matter.responsible)
                         .where(Matter.status == "open", Matter.responsible != "")).all()
        by_person: dict = {}
        info = {r[0]: r for r in rows}
        ids = list(info)
        if not ids:
            return []
        for h in s.scalars(select(Hearing).where(Hearing.matter_id.in_(ids), Hearing.date >= today,
                                                 Hearing.date <= today + dt.timedelta(days=2))):
            m = info[h.matter_id]
            by_person.setdefault(m[4], []).append(
                (h.date, f"• {h.date.isoformat()} {h.time} — {m[2]} {m[3]} — {h.court} {h.room} {h.purpose}".strip()))
        for d in s.scalars(select(Deadline).where(Deadline.matter_id.in_(ids), Deadline.done_at.is_(None),
                                                  Deadline.due_on <= today + dt.timedelta(days=7))):
            m = info[d.matter_id]
            late = " (!)" if d.due_on < today else ""
            check = "" if d.verified_by else " [à vérifier / للتحقق]"
            by_person.setdefault(m[4], []).append(
                (d.due_on, f"• {d.due_on.isoformat()}{late} — {m[2]} {m[3]} — {d.kind}{check}"))
    for email, items in by_person.items():
        u = db.get_user(email)
        if not u or u["status"] != "active" or not billing.has_practice(u.get("org_id")):
            continue
        out.append((email, u.get("language", "ar"), "\n".join(t for _, t in sorted(items))))
    return out
