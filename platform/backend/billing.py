"""Plans, subscriptions, invoices and payments.

Money is held in centimes, as whole numbers: 499.00 MAD is 49900. Nothing is ever
rounded twice.

An organization reads while it has a subscription that is trial or active and has
not ended. The worker (worker.py) marks ended ones expired and sends the reminders;
this module only answers questions and records what staff do.

Invoices are numbered F-2026-00001, F-2026-00002 ... per calendar year, with no gap
and no repeat -- the number is unique in the database, so two invoices made at the
same instant cannot share one. VAT is 20% unless the plan says otherwise.

Card payment online is not here: it needs a merchant contract with a Moroccan bank
(CMI). Payments are recorded by staff -- transfer, cheque, cash or card at the desk.
"""
from __future__ import annotations

import datetime as dt
import os
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

import db
import mailer
from deps import current_user, require_admin, require_sales


class Plan(db.Base):
    __tablename__ = "plans"
    code: Mapped[str] = mapped_column(String, primary_key=True)
    name_ar: Mapped[str] = mapped_column(String, default="")
    name_fr: Mapped[str] = mapped_column(String, default="")
    blurb_ar: Mapped[str] = mapped_column(String, default="")
    blurb_fr: Mapped[str] = mapped_column(String, default="")
    price: Mapped[int] = mapped_column(Integer, default=0)          # centimes per period, before VAT
    period: Mapped[str] = mapped_column(String, default="month")    # month | year | quote
    seats: Mapped[int] = mapped_column(Integer, default=1)
    daily_downloads: Mapped[int] = mapped_column(Integer, default=30)
    vat_rate: Mapped[int] = mapped_column(Integer, default=2000)    # basis points: 2000 = 20%
    public: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)


class Subscription(db.Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    plan_code: Mapped[str] = mapped_column(String)
    seats: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String, default="trial", index=True)  # trial|active|expired|suspended|cancelled
    starts_on: Mapped[dt.date] = mapped_column(Date)
    ends_on: Mapped[dt.date] = mapped_column(Date, index=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    # what this customer pays a month, before VAT, in centimes: the plan's price unless
    # negotiated (an accepted quote, an institution on a custom price). Feeds the MRR.
    monthly_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_by: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class Invoice(db.Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    number: Mapped[str] = mapped_column(String, unique=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    subscription_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(String, default="")
    amount_ht: Mapped[int] = mapped_column(Integer, default=0)       # centimes
    vat_rate: Mapped[int] = mapped_column(Integer, default=2000)
    vat: Mapped[int] = mapped_column(Integer, default=0)
    amount_ttc: Mapped[int] = mapped_column(Integer, default=0)
    issued_on: Mapped[dt.date] = mapped_column(Date)
    due_on: Mapped[dt.date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String, default="sent", index=True)  # draft|sent|paid|overdue|cancelled
    created_by: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class Payment(db.Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(Integer, index=True)
    amount: Mapped[int] = mapped_column(Integer)                      # centimes
    method: Mapped[str] = mapped_column(String, default="transfer")  # transfer|cheque|cash|card
    reference: Mapped[str] = mapped_column(String, default="")
    paid_on: Mapped[dt.date] = mapped_column(Date, index=True)
    recorded_by: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


# Example plans, created once on an empty database. Prices are placeholders to be set
# by an administrator on the Plans page -- nothing here is a commercial decision.
DEFAULT_PLANS = [
    dict(code="trial", name_ar="تجربة مجانية", name_fr="Essai gratuit", price=0, period="month",
         seats=2, daily_downloads=20, public=True, sort=0,
         blurb_ar="14 يوما، كل القرارات، بدون التزام", blurb_fr="14 jours, toutes les décisions, sans engagement"),
    dict(code="individual", name_ar="محام", name_fr="Avocat", price=49900, period="month",
         seats=1, daily_downloads=30, public=True, sort=1,
         blurb_ar="مقعد واحد، بحث بالعربية والفرنسية، ملفات وتنبيهات", blurb_fr="1 accès, recherche arabe et français, dossiers et alertes"),
    dict(code="firm", name_ar="مكتب", name_fr="Cabinet", price=149900, period="month",
         seats=5, daily_downloads=100, public=True, sort=2,
         blurb_ar="5 مقاعد، ملفات مشتركة داخل المكتب", blurb_fr="5 accès, dossiers partagés au sein du cabinet"),
    dict(code="institution", name_ar="مؤسسة", name_fr="Institution", price=0, period="quote",
         seats=20, daily_downloads=300, public=True, sort=3,
         blurb_ar="جامعات ومحاكم وإدارات، على عرض سعر", blurb_fr="Universités, juridictions, administrations, sur devis"),
]

TRIAL_DAYS = 14


def seed_plans() -> None:
    db.add_columns("subscriptions", [("monthly_price", "INTEGER")])
    with db.session() as s:
        if s.scalar(select(func.count()).select_from(Plan)):
            return
        for p in DEFAULT_PLANS:
            s.add(Plan(**p))
        s.commit()
    forget_plans()


def plan_dict(p: Plan) -> dict:
    return {k: getattr(p, k) for k in ("code", "name_ar", "name_fr", "blurb_ar", "blurb_fr",
                                       "price", "period", "seats", "daily_downloads",
                                       "vat_rate", "public", "active", "sort")}


# Plans are read for every subscription and contract shown, and change a few times a
# year: kept 30 seconds, dropped at once when an admin saves one (other API processes
# see the change within the 30 seconds).
_plans: dict = {}
_plans_at = 0.0


def get_plan(code: str) -> Optional[dict]:
    global _plans, _plans_at
    if time.monotonic() - _plans_at > 30:
        with db.session() as s:
            _plans = {p.code: plan_dict(p) for p in s.scalars(select(Plan))}
        _plans_at = time.monotonic()
    p = _plans.get(code)
    return dict(p) if p else None


def forget_plans() -> None:
    global _plans_at
    _plans_at = 0.0


def sub_dict(x: Subscription) -> dict:
    plan = get_plan(x.plan_code) or {}
    return {"id": x.id, "org_id": x.org_id, "plan_code": x.plan_code,
            "plan_name_ar": plan.get("name_ar", x.plan_code), "plan_name_fr": plan.get("name_fr", x.plan_code),
            "seats": x.seats, "status": x.status, "starts_on": x.starts_on.isoformat(),
            "ends_on": x.ends_on.isoformat(), "auto_renew": x.auto_renew, "notes": x.notes,
            "monthly_price": monthly_price(x, plan),
            "days_left": (x.ends_on - dt.date.today()).days,
            "created_by": x.created_by, "created_at": x.created_at.isoformat() if x.created_at else ""}


def monthly_price(x: "Subscription", plan: Optional[dict] = None) -> int:
    """Centimes a month before VAT: negotiated if set, else the plan's."""
    if x.monthly_price is not None:
        return int(x.monthly_price)
    plan = plan if plan is not None else (get_plan(x.plan_code) or {})
    if plan.get("period") == "year":
        return int(plan.get("price", 0)) // 12
    return int(plan.get("price", 0)) if plan.get("period") == "month" else 0


def current_subscription(org_id: Optional[int]) -> Optional[dict]:
    """The subscription that lets the organization read today, else its latest one."""
    if not org_id:
        return None
    today = dt.date.today()
    with db.session() as s:
        live = s.scalar(select(Subscription).where(
            Subscription.org_id == org_id, Subscription.status.in_(("trial", "active")),
            Subscription.starts_on <= today, Subscription.ends_on >= today)
            .order_by(Subscription.ends_on.desc()))
        if live:
            return sub_dict(live)
        last = s.scalar(select(Subscription).where(Subscription.org_id == org_id)
                        .order_by(Subscription.ends_on.desc(), Subscription.id.desc()))
        return sub_dict(last) if last else None


def subscriptions_for(org_ids) -> dict:
    """{org_id: current_subscription(org_id)} for many organizations, in one query --
    for the lists that would otherwise ask once per row."""
    ids = {o for o in org_ids if o}
    if not ids:
        return {}
    today = dt.date.today()
    with db.session() as s:
        rows = list(s.scalars(select(Subscription).where(Subscription.org_id.in_(ids))))
    best: dict = {}
    for x in rows:
        live = x.status in ("trial", "active") and x.starts_on <= today <= x.ends_on
        key = (live, x.ends_on, x.id)          # the running one first, else the latest
        if x.org_id not in best or key > best[x.org_id][0]:
            best[x.org_id] = (key, x)
    return {o: sub_dict(x) for o, (_, x) in best.items()}


def access_of(sub: Optional[dict]) -> str:
    """ok | none (never subscribed) | expired | suspended, from a subscription dict."""
    if not sub:
        return "none"
    if sub["status"] in ("trial", "active") and sub["days_left"] >= 0 and \
            dt.date.fromisoformat(sub["starts_on"]) <= dt.date.today():
        return "ok"
    return "suspended" if sub["status"] == "suspended" else "expired"


def seats_of(sub: Optional[dict]) -> int:
    return sub["seats"] if sub and access_of(sub) == "ok" else 0


def quota_of(sub: Optional[dict]) -> int:
    if not sub:
        return 0
    return int((get_plan(sub["plan_code"]) or {}).get("daily_downloads", 0))


def access_state(org_id: Optional[int]) -> str:
    return access_of(current_subscription(org_id))


def seats_for(org_id: Optional[int]) -> int:
    return seats_of(current_subscription(org_id))


def daily_downloads(org_id: Optional[int]) -> int:
    return quota_of(current_subscription(org_id))


def start_subscription(org_id: int, plan_code: str, *, status: str = "active",
                       days: Optional[int] = None, starts_on: Optional[dt.date] = None,
                       seats: Optional[int] = None, actor: str = "", session=None,
                       monthly: Optional[int] = None) -> dict:
    plan = get_plan(plan_code)
    if not plan:
        raise HTTPException(status_code=400, detail="Unknown plan")
    start = starts_on or dt.date.today()
    if days is None:
        days = TRIAL_DAYS if status == "trial" else (365 if plan["period"] == "year" else 30)
    row = Subscription(org_id=org_id, plan_code=plan_code, status=status, starts_on=start,
                       ends_on=start + dt.timedelta(days=days - 1),
                       seats=seats or plan["seats"], created_by=actor, monthly_price=monthly)
    # Inside a caller's transaction, the audit row joins it: written from a second
    # session it would wait on the first one's lock, forever, on SQLite.
    own = session is None
    s = session or db.session()
    try:
        s.add(row)
        s.add(db.AuditLog(actor=actor or "system", action="subscribe", entity="organization",
                          entity_id=str(org_id), new_value=f"{plan_code} {status} {days}d"))
        s.flush()
        out_id = row.id
        if own:
            s.commit()
    finally:
        if own:
            s.close()
    return {"id": out_id}


# ---------------- invoices ----------------
def _money(c: int) -> str:
    return f"{c / 100:,.2f}".replace(",", " ")


def invoice_dict(i: Invoice, paid: int = 0) -> dict:
    status = i.status
    if status == "sent" and i.due_on < dt.date.today():
        status = "overdue"
    return {"id": i.id, "number": i.number, "org_id": i.org_id,
            "subscription_id": i.subscription_id, "description": i.description,
            "amount_ht": i.amount_ht, "vat_rate": i.vat_rate, "vat": i.vat,
            "amount_ttc": i.amount_ttc, "paid": paid, "balance": i.amount_ttc - paid,
            "issued_on": i.issued_on.isoformat(), "due_on": i.due_on.isoformat(),
            "status": status, "created_by": i.created_by}


def _paid(s, invoice_ids: List[int]) -> dict:
    if not invoice_ids:
        return {}
    rows = s.execute(select(Payment.invoice_id, func.sum(Payment.amount))
                     .where(Payment.invoice_id.in_(invoice_ids)).group_by(Payment.invoice_id)).all()
    return {k: int(v or 0) for k, v in rows}


def create_invoice(org_id: int, amount_ht: int, description: str, actor: str, *,
                   vat_rate: int = 2000, due_days: int = 30,
                   subscription_id: Optional[int] = None) -> dict:
    if amount_ht <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    vat = round(amount_ht * vat_rate / 10000)
    today = dt.date.today()
    for _ in range(5):                              # the number is unique: retry a clash
        with db.session() as s:
            prefix = f"F-{today.year}-"
            last = s.scalar(select(func.max(Invoice.number)).where(Invoice.number.like(prefix + "%")))
            n = int(last.rsplit("-", 1)[1]) + 1 if last else 1
            inv = Invoice(number=f"{prefix}{n:05d}", org_id=org_id, subscription_id=subscription_id,
                          description=description, amount_ht=amount_ht, vat_rate=vat_rate, vat=vat,
                          amount_ttc=amount_ht + vat, issued_on=today,
                          due_on=today + dt.timedelta(days=due_days), created_by=actor)
            s.add(inv)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                continue
            out = invoice_dict(inv)
        db.add_audit(actor, "invoice", "organization", str(org_id), new=out["number"])
        return out
    raise HTTPException(status_code=409, detail="Could not number the invoice; try again")


def list_invoices(org_id: Optional[int] = None, status: str = "") -> List[dict]:
    with db.session() as s:
        q = select(Invoice).order_by(Invoice.issued_on.desc(), Invoice.id.desc())
        if org_id:
            q = q.where(Invoice.org_id == org_id)
        rows = list(s.scalars(q.limit(1000)))
        paid = _paid(s, [r.id for r in rows])
        out = [invoice_dict(r, paid.get(r.id, 0)) for r in rows]
    if status:
        out = [i for i in out if i["status"] == status]
    return out


def record_payment(invoice_id: int, amount: int, method: str, reference: str,
                   paid_on: Optional[dt.date], actor: str) -> dict:
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    if method not in ("transfer", "cheque", "cash", "card"):
        raise HTTPException(status_code=400, detail="Unknown payment method")
    with db.session() as s:
        inv = s.get(Invoice, invoice_id)
        if not inv or inv.status == "cancelled":
            raise HTTPException(status_code=404, detail="Invoice not found")
        s.add(Payment(invoice_id=invoice_id, amount=amount, method=method, reference=reference,
                      paid_on=paid_on or dt.date.today(), recorded_by=actor))
        s.flush()
        paid = _paid(s, [invoice_id]).get(invoice_id, 0)
        if paid >= inv.amount_ttc:
            inv.status = "paid"
        s.commit()
        out = invoice_dict(inv, paid)
    db.add_audit(actor, "payment", "invoice", out["number"], new=f"{_money(amount)} {method}")
    return out


def payments_for(invoice_id: int) -> List[dict]:
    with db.session() as s:
        return [{"id": p.id, "amount": p.amount, "method": p.method, "reference": p.reference,
                 "paid_on": p.paid_on.isoformat(), "recorded_by": p.recorded_by}
                for p in s.scalars(select(Payment).where(Payment.invoice_id == invoice_id)
                                   .order_by(Payment.paid_on))]


# ---------------- routes ----------------
router = APIRouter()


@router.get("/api/public/plans")
def public_plans() -> list:
    with db.session() as s:
        return [plan_dict(p) for p in s.scalars(select(Plan).where(Plan.public.is_(True),
                                                                   Plan.active.is_(True))
                                                .order_by(Plan.sort))]


@router.get("/api/admin/plans")
def all_plans(_: dict = Depends(require_sales)) -> list:
    with db.session() as s:
        return [plan_dict(p) for p in s.scalars(select(Plan).order_by(Plan.sort))]


class PlanBody(BaseModel):
    code: str
    name_ar: str = ""
    name_fr: str = ""
    blurb_ar: str = ""
    blurb_fr: str = ""
    price: int = 0
    period: str = "month"
    seats: int = 1
    daily_downloads: int = 30
    vat_rate: int = 2000
    public: bool = True
    active: bool = True
    sort: int = 0


@router.put("/api/admin/plans/{code}")
def save_plan(code: str, body: PlanBody, user: dict = Depends(require_admin)) -> dict:
    if body.period not in ("month", "year", "quote") or body.price < 0 or body.seats < 1:
        raise HTTPException(status_code=400, detail="Check period, price and seats")
    with db.session() as s:
        p = s.get(Plan, code) or Plan(code=code)
        for k, v in body.model_dump().items():
            if k != "code":
                setattr(p, k, v)
        s.add(p)
        s.commit()
        out = plan_dict(p)
    forget_plans()
    db.add_audit(user["email"], "plan", "plan", code, new=f"{out['price']} / {out['period']}")
    return out


@router.get("/api/invoices/{invoice_id}")
def invoice_detail(invoice_id: int, user: dict = Depends(current_user)) -> dict:
    """One invoice, for printing: staff see any, a customer's account holder theirs."""
    import accounts
    with db.session() as s:
        inv = s.get(Invoice, invoice_id)
        if not inv:
            raise HTTPException(status_code=404, detail="Not found")
        if user["role"] not in ("admin", "sales") and not (
                user["role"] == "client_admin" and user.get("org_id") == inv.org_id):
            raise HTTPException(status_code=404, detail="Not found")
        out = invoice_dict(inv, _paid(s, [invoice_id]).get(invoice_id, 0))
    out["org"] = accounts.get_org(out["org_id"])
    out["payments"] = payments_for(invoice_id)
    out["seller"] = {"name": os.getenv("SELLER_NAME", ""),
                     "address": os.getenv("SELLER_ADDRESS", ""),
                     "ice": os.getenv("SELLER_ICE", ""),
                     "rib": os.getenv("SELLER_RIB", "")}
    return out


@router.get("/api/account/invoices")
def my_invoices(user: dict = Depends(current_user)) -> list:
    if user["role"] != "client_admin" or not user.get("org_id"):
        return []
    return [i for i in list_invoices(user["org_id"]) if i["status"] != "draft"]


@router.get("/api/admin/outbox")
def outbox(_: dict = Depends(require_admin)) -> list:
    return mailer.outbox()
