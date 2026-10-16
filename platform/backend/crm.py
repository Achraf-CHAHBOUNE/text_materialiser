"""The CRM, as the admin uses it: the clients (organizations) and the requests that
come in through the public page.

A client in Morocco comes the same way every time: they pay by bank transfer, a
contract is signed, and their accounts are created. That path lives in contracts.py;
this module holds the clients themselves and the inbox of requests.

    lead          someone who wrote through the public page; a request to answer
    organization  a client: one lawyer or a firm, with its people and its contracts

The health of a client is read from what its people actually do on the platform
(client_activity): busy, quiet, or nobody has opened anything in 30 days.
"""
from __future__ import annotations

import datetime as dt
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import DateTime, Integer, String, Text, func, or_, select
from sqlalchemy.orm import Mapped, mapped_column

import accounts
import billing
import db
import mailer
from deps import require_sales

LEAD_STATUSES = ("new", "contacted", "converted", "rejected")


class Lead(db.Base):
    __tablename__ = "leads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String, default="website")
    full_name: Mapped[str] = mapped_column(String, default="")
    email: Mapped[str] = mapped_column(String, default="", index=True)
    phone: Mapped[str] = mapped_column(String, default="")
    company: Mapped[str] = mapped_column(String, default="")
    city: Mapped[str] = mapped_column(String, default="")
    message: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String, default="ar")
    status: Mapped[str] = mapped_column(String, default="new", index=True)
    assigned_to: Mapped[str] = mapped_column(String, default="")
    org_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    deleted_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)


def _row(obj, fields) -> dict:
    out = {}
    for f in fields:
        v = getattr(obj, f)
        out[f] = v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v
    return out


LEAD_F = ("id", "source", "full_name", "email", "phone", "company", "city", "message",
          "language", "status", "assigned_to", "org_id", "created_at")


# ---------------- health ----------------
def health(org_ids: list) -> dict:
    """{org_id: (actions in 30 days, 'active'|'quiet'|'at_risk')} from what its people did."""
    if not org_ids:
        return {}
    since = dt.datetime.utcnow() - dt.timedelta(days=30)
    with db.session() as s:
        rows = s.execute(
            select(db.User.org_id, func.count(db.ClientActivity.id))
            .join(db.User, db.User.email == db.ClientActivity.actor)
            .where(db.User.org_id.in_(org_ids), db.ClientActivity.ts >= since)
            .group_by(db.User.org_id)).all()
        young = set(s.scalars(select(accounts.Organization.id).where(
            accounts.Organization.id.in_(org_ids), accounts.Organization.created_at >= since)))
    counts = {k: int(v) for k, v in rows}
    out = {}
    for o in org_ids:
        n = counts.get(o, 0)
        # silence from a client of a few days is not yet a warning sign
        out[o] = (n, "active" if n >= 20 else "quiet" if n > 0 or o in young else "at_risk")
    return out


# ---------------- routes ----------------
router = APIRouter()

# -- the public contact form: no account, so a rate limit and a honeypot guard it --
_demo_hits: dict = {}
DEMO_PER_HOUR = 5


class DemoBody(BaseModel):
    full_name: str
    email: str
    phone: str = ""
    company: str = ""
    city: str = ""
    message: str = ""
    language: str = "ar"
    website: str = ""          # hidden in the form: only a robot fills it


@router.post("/api/public/demo")
def demo_request(body: DemoBody, request: Request) -> dict:
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or \
        (request.client.host if request.client else "?")
    now = time.time()
    hits = [t for t in _demo_hits.get(ip, []) if now - t < 3600]
    if len(hits) >= DEMO_PER_HOUR:
        raise HTTPException(status_code=429, detail="Too many requests; try again later")
    _demo_hits[ip] = hits + [now]
    if body.website:                       # a robot: say thank you and keep nothing
        return {"ok": True}
    if "@" not in body.email or not body.full_name.strip():
        raise HTTPException(status_code=400, detail="Name and email required")
    lang = body.language if body.language in ("ar", "fr") else "ar"
    with db.session() as s:
        lead = Lead(source="website", full_name=body.full_name.strip()[:120],
                    email=body.email.strip().lower()[:160], phone=body.phone.strip()[:40],
                    company=body.company.strip()[:160], city=body.city.strip()[:80],
                    message=body.message.strip()[:2000], language=lang)
        s.add(lead)
        s.commit()
        lead_id = lead.id
    mailer.queue(body.email.strip(), "demo_received", lang, name=body.full_name.strip())
    for staff in mailer.staff_addresses(("admin",)):
        mailer.queue(staff, "new_lead", "fr", name=body.full_name, company=body.company or "—",
                     email=body.email, phone=body.phone, message=body.message,
                     link=f"{mailer.site_url()}/fr/crm")
    return {"ok": True, "id": lead_id}


class LeadPatch(BaseModel):
    status: str


@router.get("/api/crm/leads")
def leads(status: str = "", _: dict = Depends(require_sales)) -> list:
    with db.session() as s:
        q = select(Lead).where(Lead.deleted_at.is_(None)).order_by(Lead.created_at.desc())
        if status:
            q = q.where(Lead.status == status)
        return [_row(x, LEAD_F) for x in s.scalars(q.limit(300))]


@router.patch("/api/crm/leads/{lead_id}")
def lead_update(lead_id: int, body: LeadPatch, user: dict = Depends(require_sales)) -> dict:
    if body.status not in LEAD_STATUSES:
        raise HTTPException(status_code=400, detail="Unknown status")
    with db.session() as s:
        x = s.get(Lead, lead_id)
        if not x or x.deleted_at:
            raise HTTPException(status_code=404, detail="Not found")
        x.status = body.status
        s.commit()
        return _row(x, LEAD_F)


# -- clients (organizations) --
class OrgBody(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    city: Optional[str] = None
    ice: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    language: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


@router.get("/api/crm/orgs")
def orgs(q: str = "", _: dict = Depends(require_sales)) -> list:
    import contracts
    O = accounts.Organization
    with db.session() as s:
        query = select(O).where(O.deleted_at.is_(None))
        if q.strip():
            like = f"%{q.strip()}%"
            query = query.where(or_(O.name.ilike(like), O.city.ilike(like), O.email.ilike(like), O.ice.ilike(like)))
        rows = [accounts.org_dict(o) for o in s.scalars(query.order_by(O.name).limit(2000))]
    h = health([o["id"] for o in rows])
    money = contracts.money_by_org()
    current = contracts.current_contracts([o["id"] for o in rows])
    for o in rows:
        o["contract"] = current.get(o["id"])
        o["access"] = billing.access_state(o["id"])
        o["seats"] = {"total": billing.seats_for(o["id"]), "used": accounts.seats_used(o["id"])}
        o["paid"], o["owed"] = money.get(o["id"], (0, 0))
        o["activity_30d"], o["health"] = h.get(o["id"], (0, "at_risk"))
    return rows


@router.get("/api/crm/orgs/{org_id}")
def org_detail(org_id: int, _: dict = Depends(require_sales)) -> dict:
    import contracts
    org = accounts.get_org(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Not found")
    org["members"] = accounts.org_members(org_id)
    org["invitations"] = accounts.pending_invitations(org_id)
    org["subscription"] = billing.current_subscription(org_id)
    org["access"] = billing.access_state(org_id)
    org["seats"] = {"total": billing.seats_for(org_id), "used": accounts.seats_used(org_id)}
    org["activity_30d"], org["health"] = health([org_id]).get(org_id, (0, "at_risk"))
    org["contracts"] = contracts.contracts_for(org_id)
    org["paid"], org["owed"] = contracts.money_by_org().get(org_id, (0, 0))
    org["invoices"] = billing.list_invoices(org_id)
    org["audit"] = db.audit_for(str(org_id))[:100]
    return org


@router.patch("/api/crm/orgs/{org_id}")
def org_update(org_id: int, body: OrgBody, user: dict = Depends(require_sales)) -> dict:
    return accounts.update_org(org_id, body.model_dump(exclude_none=True), user["email"])


class InviteBody(BaseModel):
    email: str
    role: str = "client"
    language: str = ""


@router.post("/api/crm/orgs/{org_id}/invite")
def org_invite(org_id: int, body: InviteBody, user: dict = Depends(require_sales)) -> dict:
    return accounts.invite(org_id, body.email, body.role, user, body.language)
