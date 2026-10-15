"""The CRM: who might buy, who has bought, and what the team is doing about each.

    lead          a demo request or a prospect; becomes an organization when converted
    contact       a person at an organization (who may or may not have an account)
    opportunity   a sale in progress: new -> contacted -> demo -> trial -> won | lost
    activity      a call, email, meeting or note, against an organization
    task          something to do by a date, assigned to someone

Records are never deleted, only marked (deleted_at), so the history and the figures
stay true. Every change goes to the audit log with who made it.

The health of a customer is read from what its people actually do on the platform
(client_activity): busy, quiet, or nobody has opened anything in 30 days.
"""
from __future__ import annotations

import datetime as dt
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import Date, DateTime, Integer, String, Text, func, or_, select
from sqlalchemy.orm import Mapped, mapped_column

import accounts
import billing
import db
import mailer
from deps import require_sales

STAGES = ("new", "contacted", "demo", "trial", "won", "lost")
LEAD_STATUSES = ("new", "contacted", "qualified", "converted", "rejected")


class Lead(db.Base):
    __tablename__ = "leads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String, default="website")   # website|phone|event|referral|other
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


class Contact(db.Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    full_name: Mapped[str] = mapped_column(String, default="")
    job_title: Mapped[str] = mapped_column(String, default="")
    email: Mapped[str] = mapped_column(String, default="")
    phone: Mapped[str] = mapped_column(String, default="")
    language: Mapped[str] = mapped_column(String, default="ar")
    is_primary: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    deleted_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)


class Opportunity(db.Base):
    __tablename__ = "opportunities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String, default="")
    stage: Mapped[str] = mapped_column(String, default="new", index=True)
    value: Mapped[int] = mapped_column(Integer, default=0)            # centimes, per year
    plan_code: Mapped[str] = mapped_column(String, default="")
    expected_close: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    owner: Mapped[str] = mapped_column(String, default="")
    lost_reason: Mapped[str] = mapped_column(String, default="")
    closed_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    deleted_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)


class Activity(db.Base):
    __tablename__ = "activities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    contact_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    opportunity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String, default="note")         # call|email|meeting|note
    body: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    by_user: Mapped[str] = mapped_column(String, default="")


class Task(db.Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String, default="")
    due_on: Mapped[dt.date] = mapped_column(Date, index=True)
    assigned_to: Mapped[str] = mapped_column(String, default="", index=True)
    org_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    opportunity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    done_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


def _row(obj, fields) -> dict:
    out = {}
    for f in fields:
        v = getattr(obj, f)
        out[f] = v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v
    return out


LEAD_F = ("id", "source", "full_name", "email", "phone", "company", "city", "message",
          "language", "status", "assigned_to", "org_id", "created_at")
CONTACT_F = ("id", "org_id", "full_name", "job_title", "email", "phone", "language",
             "is_primary", "created_at")
OPP_F = ("id", "org_id", "title", "stage", "value", "plan_code", "expected_close", "owner",
         "lost_reason", "closed_at", "created_at")
ACT_F = ("id", "org_id", "contact_id", "opportunity_id", "kind", "body", "at", "by_user")
TASK_F = ("id", "title", "due_on", "assigned_to", "org_id", "opportunity_id", "done_at",
          "created_by", "created_at")


def _audit(actor: str, action: str, entity: str, entity_id, new: str = "") -> None:
    db.add_audit(actor, action, entity, str(entity_id), new=new)


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
        # silence from a customer of a few days is not yet a warning sign
        out[o] = (n, "active" if n >= 20 else "quiet" if n > 0 or o in young else "at_risk")
    return out


# ---------------- routes ----------------
router = APIRouter()

# -- the public demo form: no account, so it is guarded by a rate limit and a honeypot --
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
    for staff in mailer.staff_addresses(("admin", "sales")):
        mailer.queue(staff, "new_lead", "fr", name=body.full_name, company=body.company or "—",
                     email=body.email, phone=body.phone, message=body.message,
                     link=f"{mailer.site_url()}/fr/crm/leads")
    return {"ok": True, "id": lead_id}


# -- leads --
class LeadBody(BaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    company: str = ""
    city: str = ""
    message: str = ""
    language: str = "ar"
    source: str = "phone"
    status: Optional[str] = None
    assigned_to: Optional[str] = None


@router.get("/api/crm/leads")
def leads(status: str = "", q: str = "", _: dict = Depends(require_sales)) -> list:
    with db.session() as s:
        query = select(Lead).where(Lead.deleted_at.is_(None)).order_by(Lead.created_at.desc())
        if status:
            query = query.where(Lead.status == status)
        if q.strip():
            like = f"%{q.strip()}%"
            query = query.where(or_(Lead.full_name.like(like), Lead.company.like(like),
                                    Lead.email.like(like)))
        return [_row(x, LEAD_F) for x in s.scalars(query.limit(500))]


@router.post("/api/crm/leads")
def lead_create(body: LeadBody, user: dict = Depends(require_sales)) -> dict:
    with db.session() as s:
        x = Lead(**{k: v for k, v in body.model_dump().items() if v is not None})
        x.assigned_to = x.assigned_to or user["email"]
        s.add(x)
        s.commit()
        out = _row(x, LEAD_F)
    _audit(user["email"], "create", "lead", out["id"], out["company"] or out["full_name"])
    return out


@router.patch("/api/crm/leads/{lead_id}")
def lead_update(lead_id: int, body: LeadBody, user: dict = Depends(require_sales)) -> dict:
    with db.session() as s:
        x = s.get(Lead, lead_id)
        if not x or x.deleted_at:
            raise HTTPException(status_code=404, detail="Not found")
        for k, v in body.model_dump(exclude_unset=True).items():
            if k == "status" and v not in LEAD_STATUSES:
                raise HTTPException(status_code=400, detail="Unknown status")
            setattr(x, k, v)
        s.commit()
        out = _row(x, LEAD_F)
    _audit(user["email"], "update", "lead", lead_id, out["status"])
    return out


class ConvertBody(BaseModel):
    org_name: str = ""
    kind: str = "firm"
    trial: bool = True
    invite: bool = True


@router.post("/api/crm/leads/{lead_id}/convert")
def lead_convert(lead_id: int, body: ConvertBody, user: dict = Depends(require_sales)) -> dict:
    """A lead becomes an organization with its contact, an opportunity at the trial
    stage, a 14-day trial, and -- unless told otherwise -- an invitation in its inbox."""
    with db.session() as s:
        x = s.get(Lead, lead_id)
        if not x or x.deleted_at:
            raise HTTPException(status_code=404, detail="Not found")
        if x.org_id:
            raise HTTPException(status_code=409, detail="Already converted")
        lead = _row(x, LEAD_F)
    org = accounts.create_org({"name": body.org_name or lead["company"] or lead["full_name"],
                               "kind": body.kind, "city": lead["city"], "email": lead["email"],
                               "phone": lead["phone"], "language": lead["language"],
                               "account_manager": lead["assigned_to"] or user["email"],
                               "status": "prospect"}, user["email"])
    with db.session() as s:
        s.add(Contact(org_id=org["id"], full_name=lead["full_name"], email=lead["email"],
                      phone=lead["phone"], language=lead["language"], is_primary=1))
        s.add(Opportunity(org_id=org["id"], title=f"{org['name']}", owner=user["email"],
                          stage="trial" if body.trial else "contacted"))
        if lead["message"]:
            s.add(Activity(org_id=org["id"], kind="note", by_user=user["email"],
                           body=f"[{lead['source']}] {lead['message']}"))
        x = s.get(Lead, lead_id)
        x.status, x.org_id = "converted", org["id"]
        s.commit()
    if body.trial:
        billing.start_subscription(org["id"], "trial", status="trial", actor=user["email"])
    invited = None
    if body.invite and lead["email"]:
        invited = accounts.invite(org["id"], lead["email"], "client_admin", user, lead["language"])
    _audit(user["email"], "convert", "lead", lead_id, f"org {org['id']}")
    return {"org": org, "invitation": invited}


# -- organizations --
class OrgBody(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    city: Optional[str] = None
    ice: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    language: Optional[str] = None
    account_manager: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


@router.get("/api/crm/orgs")
def orgs(q: str = "", status: str = "", _: dict = Depends(require_sales)) -> list:
    with db.session() as s:
        query = select(accounts.Organization).where(accounts.Organization.deleted_at.is_(None))
        if status:
            query = query.where(accounts.Organization.status == status)
        if q.strip():
            like = f"%{q.strip()}%"
            query = query.where(or_(accounts.Organization.name.like(like),
                                    accounts.Organization.city.like(like),
                                    accounts.Organization.email.like(like)))
        rows = [accounts.org_dict(o) for o in s.scalars(query.order_by(accounts.Organization.name).limit(1000))]
    h = health([o["id"] for o in rows])
    for o in rows:
        sub = billing.current_subscription(o["id"])
        o["subscription"] = sub
        o["access"] = billing.access_state(o["id"])
        o["seats_used"] = accounts.seats_used(o["id"])
        o["activity_30d"], o["health"] = h.get(o["id"], (0, "at_risk"))
    return rows


@router.post("/api/crm/orgs")
def org_create(body: OrgBody, user: dict = Depends(require_sales)) -> dict:
    return accounts.create_org(body.model_dump(exclude_none=True), user["email"])


@router.get("/api/crm/orgs/{org_id}")
def org_detail(org_id: int, _: dict = Depends(require_sales)) -> dict:
    org = accounts.get_org(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Not found")
    with db.session() as s:
        org["contacts"] = [_row(c, CONTACT_F) for c in s.scalars(
            select(Contact).where(Contact.org_id == org_id, Contact.deleted_at.is_(None))
            .order_by(Contact.is_primary.desc(), Contact.full_name))]
        org["opportunities"] = [_row(o, OPP_F) for o in s.scalars(
            select(Opportunity).where(Opportunity.org_id == org_id, Opportunity.deleted_at.is_(None))
            .order_by(Opportunity.created_at.desc()))]
        org["activities"] = [_row(a, ACT_F) for a in s.scalars(
            select(Activity).where(Activity.org_id == org_id).order_by(Activity.at.desc()).limit(200))]
        org["tasks"] = [_row(t, TASK_F) for t in s.scalars(
            select(Task).where(Task.org_id == org_id).order_by(Task.done_at.is_not(None), Task.due_on))]
    org["members"] = accounts.org_members(org_id)
    org["invitations"] = accounts.pending_invitations(org_id)
    org["subscription"] = billing.current_subscription(org_id)
    org["access"] = billing.access_state(org_id)
    org["seats"] = {"total": billing.seats_for(org_id), "used": accounts.seats_used(org_id)}
    org["activity_30d"], org["health"] = health([org_id]).get(org_id, (0, "at_risk"))
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


# -- contacts --
class ContactBody(BaseModel):
    full_name: Optional[str] = None
    job_title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    language: Optional[str] = None
    is_primary: Optional[int] = None


@router.post("/api/crm/orgs/{org_id}/contacts")
def contact_create(org_id: int, body: ContactBody, user: dict = Depends(require_sales)) -> dict:
    with db.session() as s:
        c = Contact(org_id=org_id, **body.model_dump(exclude_none=True))
        s.add(c)
        s.commit()
        out = _row(c, CONTACT_F)
    _audit(user["email"], "create", "contact", out["id"], out["full_name"])
    return out


@router.patch("/api/crm/contacts/{contact_id}")
def contact_update(contact_id: int, body: ContactBody, user: dict = Depends(require_sales)) -> dict:
    with db.session() as s:
        c = s.get(Contact, contact_id)
        if not c or c.deleted_at:
            raise HTTPException(status_code=404, detail="Not found")
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(c, k, v)
        s.commit()
        return _row(c, CONTACT_F)


@router.delete("/api/crm/contacts/{contact_id}")
def contact_delete(contact_id: int, user: dict = Depends(require_sales)) -> dict:
    with db.session() as s:
        c = s.get(Contact, contact_id)
        if c:
            c.deleted_at = dt.datetime.utcnow()
            s.commit()
    _audit(user["email"], "delete", "contact", contact_id)
    return {"ok": True}


# -- opportunities --
class OppBody(BaseModel):
    title: Optional[str] = None
    stage: Optional[str] = None
    value: Optional[int] = None
    plan_code: Optional[str] = None
    expected_close: Optional[str] = None
    owner: Optional[str] = None
    lost_reason: Optional[str] = None


def _apply_opp(o: Opportunity, body: OppBody) -> None:
    for k, v in body.model_dump(exclude_none=True).items():
        if k == "stage":
            if v not in STAGES:
                raise HTTPException(status_code=400, detail="Unknown stage")
            o.closed_at = dt.datetime.utcnow() if v in ("won", "lost") else None
        if k == "expected_close":
            v = dt.date.fromisoformat(v) if v else None
        setattr(o, k, v)


@router.post("/api/crm/orgs/{org_id}/opportunities")
def opp_create(org_id: int, body: OppBody, user: dict = Depends(require_sales)) -> dict:
    with db.session() as s:
        o = Opportunity(org_id=org_id, owner=user["email"])
        _apply_opp(o, body)
        s.add(o)
        s.commit()
        out = _row(o, OPP_F)
    _audit(user["email"], "create", "opportunity", out["id"], out["stage"])
    return out


@router.patch("/api/crm/opportunities/{opp_id}")
def opp_update(opp_id: int, body: OppBody, user: dict = Depends(require_sales)) -> dict:
    with db.session() as s:
        o = s.get(Opportunity, opp_id)
        if not o or o.deleted_at:
            raise HTTPException(status_code=404, detail="Not found")
        before = o.stage
        _apply_opp(o, body)
        s.commit()
        out = _row(o, OPP_F)
    if out["stage"] != before:
        _audit(user["email"], "stage", "opportunity", opp_id, f"{before} → {out['stage']}")
    return out


@router.get("/api/crm/pipeline")
def pipeline(_: dict = Depends(require_sales)) -> list:
    with db.session() as s:
        rows = s.execute(select(Opportunity, accounts.Organization.name)
                         .join(accounts.Organization, accounts.Organization.id == Opportunity.org_id)
                         .where(Opportunity.deleted_at.is_(None))
                         .order_by(Opportunity.created_at.desc()).limit(1000)).all()
        return [{**_row(o, OPP_F), "org_name": name} for o, name in rows]


# -- activities and tasks --
class ActivityBody(BaseModel):
    kind: str = "note"
    body: str
    contact_id: Optional[int] = None
    opportunity_id: Optional[int] = None


@router.post("/api/crm/orgs/{org_id}/activities")
def activity_create(org_id: int, body: ActivityBody, user: dict = Depends(require_sales)) -> dict:
    if body.kind not in ("call", "email", "meeting", "note"):
        raise HTTPException(status_code=400, detail="Unknown kind")
    with db.session() as s:
        a = Activity(org_id=org_id, by_user=user["email"], **body.model_dump())
        s.add(a)
        s.commit()
        return _row(a, ACT_F)


class TaskBody(BaseModel):
    title: Optional[str] = None
    due_on: Optional[str] = None
    assigned_to: Optional[str] = None
    org_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    done: Optional[bool] = None


@router.get("/api/crm/tasks")
def tasks(mine: bool = True, open_only: bool = True, user: dict = Depends(require_sales)) -> list:
    with db.session() as s:
        q = select(Task, accounts.Organization.name).outerjoin(
            accounts.Organization, accounts.Organization.id == Task.org_id)
        if mine:
            q = q.where(Task.assigned_to == user["email"])
        if open_only:
            q = q.where(Task.done_at.is_(None))
        return [{**_row(t, TASK_F), "org_name": name or ""}
                for t, name in s.execute(q.order_by(Task.due_on).limit(500)).all()]


@router.post("/api/crm/tasks")
def task_create(body: TaskBody, user: dict = Depends(require_sales)) -> dict:
    if not (body.title or "").strip() or not body.due_on:
        raise HTTPException(status_code=400, detail="Title and date required")
    with db.session() as s:
        t = Task(title=body.title.strip(), due_on=dt.date.fromisoformat(body.due_on),
                 assigned_to=body.assigned_to or user["email"], org_id=body.org_id,
                 opportunity_id=body.opportunity_id, created_by=user["email"])
        s.add(t)
        s.commit()
        return _row(t, TASK_F)


@router.patch("/api/crm/tasks/{task_id}")
def task_update(task_id: int, body: TaskBody, user: dict = Depends(require_sales)) -> dict:
    with db.session() as s:
        t = s.get(Task, task_id)
        if not t:
            raise HTTPException(status_code=404, detail="Not found")
        if body.title:
            t.title = body.title
        if body.due_on:
            t.due_on = dt.date.fromisoformat(body.due_on)
        if body.assigned_to:
            t.assigned_to = body.assigned_to
        if body.done is not None:
            t.done_at = dt.datetime.utcnow() if body.done else None
        s.commit()
        return _row(t, TASK_F)


# -- the sales dashboard --
@router.get("/api/crm/dashboard")
def dashboard(user: dict = Depends(require_sales)) -> dict:
    today = dt.date.today()
    month_start = today.replace(day=1)
    with db.session() as s:
        stages = dict(s.execute(select(Opportunity.stage, func.count())
                                .where(Opportunity.deleted_at.is_(None))
                                .group_by(Opportunity.stage)).all())
        values = dict(s.execute(select(Opportunity.stage, func.sum(Opportunity.value))
                                .where(Opportunity.deleted_at.is_(None))
                                .group_by(Opportunity.stage)).all())
        new_leads = s.scalar(select(func.count()).select_from(Lead).where(
            Lead.status == "new", Lead.deleted_at.is_(None))) or 0
        revenue_month = s.scalar(select(func.sum(billing.Payment.amount)).where(
            billing.Payment.paid_on >= month_start)) or 0
        renewing = list(s.scalars(select(billing.Subscription).where(
            billing.Subscription.status.in_(("trial", "active")),
            billing.Subscription.ends_on >= today,
            billing.Subscription.ends_on <= today + dt.timedelta(days=30))
            .order_by(billing.Subscription.ends_on)))
        my_tasks = s.scalar(select(func.count()).select_from(Task).where(
            Task.assigned_to == user["email"], Task.done_at.is_(None), Task.due_on <= today)) or 0
        customer_ids = list(s.scalars(select(accounts.Organization.id).where(
            accounts.Organization.status == "customer", accounts.Organization.deleted_at.is_(None))))
    outstanding = sum(i["balance"] for i in billing.list_invoices()
                      if i["status"] in ("sent", "overdue"))
    overdue = sum(1 for i in billing.list_invoices() if i["status"] == "overdue")
    h = health(customer_ids)
    at_risk = []
    for oid, (n, state) in h.items():
        if state == "at_risk" and billing.access_state(oid) == "ok":
            o = accounts.get_org(oid)
            if o:
                at_risk.append({"id": oid, "name": o["name"], "activity_30d": n})
    renewals = []
    for x in renewing:
        o = accounts.get_org(x.org_id)
        if o:
            renewals.append({"org_id": x.org_id, "name": o["name"], "ends_on": x.ends_on.isoformat(),
                             "status": x.status, "plan_code": x.plan_code,
                             "days_left": (x.ends_on - today).days})
    return {"pipeline": [{"stage": st, "count": int(stages.get(st, 0) or 0),
                          "value": int(values.get(st, 0) or 0)} for st in STAGES],
            "new_leads": new_leads, "revenue_month": int(revenue_month),
            "outstanding": int(outstanding), "overdue_invoices": overdue,
            "renewals": renewals, "at_risk": at_risk, "my_tasks_due": my_tasks,
            "customers": len(customer_ids)}
