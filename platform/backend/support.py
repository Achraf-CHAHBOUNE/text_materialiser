"""Support tickets: a customer asks, the team answers, both see the same thread.

A customer sees the tickets of their own organization; staff see all. A reply from
the team is emailed to whoever opened the ticket; a new ticket is emailed to the team.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

import accounts
import db
import mailer
from deps import STAFF, current_user


class Ticket(db.Base):
    __tablename__ = "tickets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    user_email: Mapped[str] = mapped_column(String, index=True)
    subject: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="open", index=True)   # open|pending|closed
    priority: Mapped[str] = mapped_column(String, default="normal")           # normal|high
    assigned_to: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class TicketMessage(db.Base):
    __tablename__ = "ticket_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(Integer, index=True)
    author: Mapped[str] = mapped_column(String, default="")
    staff: Mapped[int] = mapped_column(Integer, default=0)
    body: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


def _t(x: Ticket, org_name: str = "") -> dict:
    return {"id": x.id, "org_id": x.org_id, "org_name": org_name, "user_email": x.user_email,
            "subject": x.subject, "status": x.status, "priority": x.priority,
            "assigned_to": x.assigned_to, "created_at": x.created_at.isoformat(),
            "updated_at": x.updated_at.isoformat()}


def _can_see(user: dict, x: Ticket) -> bool:
    return user["role"] in STAFF or (x.org_id and x.org_id == user.get("org_id")) \
        or x.user_email == user["email"]


router = APIRouter()


class TicketBody(BaseModel):
    subject: str
    body: str
    priority: str = "normal"


class ReplyBody(BaseModel):
    body: str


class TicketPatch(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_to: Optional[str] = None


@router.get("/api/support")
def tickets(status: str = "", user: dict = Depends(current_user)) -> list:
    with db.session() as s:
        q = select(Ticket).order_by(Ticket.updated_at.desc())
        if user["role"] not in STAFF:
            q = q.where((Ticket.org_id == user.get("org_id")) if user.get("org_id")
                        else (Ticket.user_email == user["email"]))
        if status:
            q = q.where(Ticket.status == status)
        rows = list(s.scalars(q.limit(500)))
    names = {}
    out = []
    for x in rows:
        if x.org_id and x.org_id not in names:
            names[x.org_id] = (accounts.get_org(x.org_id) or {}).get("name", "")
        out.append(_t(x, names.get(x.org_id, "")))
    return out


@router.post("/api/support")
def open_ticket(body: TicketBody, user: dict = Depends(current_user)) -> dict:
    if not body.subject.strip() or not body.body.strip():
        raise HTTPException(status_code=400, detail="Subject and message required")
    with db.session() as s:
        x = Ticket(org_id=user.get("org_id"), user_email=user["email"],
                   subject=body.subject.strip()[:200],
                   priority=body.priority if body.priority in ("normal", "high") else "normal")
        s.add(x)
        s.flush()
        s.add(TicketMessage(ticket_id=x.id, author=user["email"], body=body.body.strip()[:5000],
                            staff=1 if user["role"] in STAFF else 0))
        s.commit()
        out = _t(x)
    org = accounts.get_org(user.get("org_id")) or {}
    for staff in mailer.staff_addresses(("admin", "sales")):
        mailer.queue(staff, "ticket_new", "fr", subject=out["subject"], author=user["email"],
                     org=org.get("name", "—"), body=body.body.strip()[:1500],
                     link=f"{mailer.site_url()}/fr/support/{out['id']}")
    return out


@router.get("/api/support/{ticket_id}")
def ticket(ticket_id: int, user: dict = Depends(current_user)) -> dict:
    with db.session() as s:
        x = s.get(Ticket, ticket_id)
        if not x or not _can_see(user, x):
            raise HTTPException(status_code=404, detail="Not found")
        out = _t(x, (accounts.get_org(x.org_id) or {}).get("name", ""))
        out["messages"] = [{"id": m.id, "author": m.author, "staff": bool(m.staff), "body": m.body,
                            "created_at": m.created_at.isoformat()}
                           for m in s.scalars(select(TicketMessage).where(
                               TicketMessage.ticket_id == ticket_id).order_by(TicketMessage.id))]
    return out


@router.post("/api/support/{ticket_id}/reply")
def reply(ticket_id: int, body: ReplyBody, user: dict = Depends(current_user)) -> dict:
    if not body.body.strip():
        raise HTTPException(status_code=400, detail="Message required")
    staff = user["role"] in STAFF
    with db.session() as s:
        x = s.get(Ticket, ticket_id)
        if not x or not _can_see(user, x):
            raise HTTPException(status_code=404, detail="Not found")
        s.add(TicketMessage(ticket_id=ticket_id, author=user["email"], staff=int(staff),
                            body=body.body.strip()[:5000]))
        x.updated_at = dt.datetime.utcnow()
        # the team answered: the customer's turn; the customer answered: open again
        x.status = "pending" if staff else "open"
        if staff and not x.assigned_to:
            x.assigned_to = user["email"]
        opener, subject = x.user_email, x.subject
        s.commit()
    if staff and opener != user["email"]:
        lang = (db.get_user(opener) or {}).get("language", "ar")
        mailer.queue(opener, "ticket_reply", lang, subject=subject, body=body.body.strip()[:1500],
                     link=f"{mailer.site_url()}/{lang}/support/{ticket_id}")
    return ticket(ticket_id, user)


@router.patch("/api/support/{ticket_id}")
def update_ticket(ticket_id: int, body: TicketPatch, user: dict = Depends(current_user)) -> dict:
    with db.session() as s:
        x = s.get(Ticket, ticket_id)
        if not x or not _can_see(user, x):
            raise HTTPException(status_code=404, detail="Not found")
        staff = user["role"] in STAFF
        if body.status in ("open", "pending", "closed"):
            if not staff and body.status != "closed":
                raise HTTPException(status_code=403, detail="Not allowed")
            x.status = body.status
        if staff and body.priority in ("normal", "high"):
            x.priority = body.priority
        if staff and body.assigned_to is not None:
            x.assigned_to = body.assigned_to
        x.updated_at = dt.datetime.utcnow()
        s.commit()
    return ticket(ticket_id, user)
