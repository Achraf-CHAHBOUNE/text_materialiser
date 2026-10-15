"""The sales side, deeper: quotes, email from the CRM, revenue reports, forecast, and
getting lists in and out.

A sale to a firm or an institution in Morocco usually goes through a quote (devis)
before anything is paid. A quote has lines, a validity date and its own numbering
(D-2026-00001); accepting it starts the subscription at the quoted price, issues the
invoice and marks the opportunity won -- one click, nothing typed twice.

The reports read what is already recorded -- subscriptions, invoices, payments, leads
-- so they cannot disagree with the screens they summarize:

    MRR        what active customers pay a month, before VAT (negotiated price if any)
    revenue    payments received, month by month, over twelve months
    new        organizations whose first paid subscription began that month
    churned    organizations whose last subscription ended that month, not renewed
    conversion leads received in the period that became customers
    forecast   open opportunities weighted by how likely their stage is to close
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Date, DateTime, Integer, String, Text, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

import accounts
import billing
import crm
import db
import mailer
from deps import current_user, require_sales

# How likely an opportunity at each stage is to close: the weights of the forecast.
STAGE_ODDS = {"new": 0.10, "contacted": 0.20, "demo": 0.40, "trial": 0.60, "won": 1.0, "lost": 0.0}


class Quote(db.Base):
    __tablename__ = "quotes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    number: Mapped[str] = mapped_column(String, unique=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    lines: Mapped[str] = mapped_column(Text, default="[]")    # [{label, qty, unit_price}] centimes
    plan_code: Mapped[str] = mapped_column(String, default="")
    months: Mapped[int] = mapped_column(Integer, default=12)
    seats: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    vat_rate: Mapped[int] = mapped_column(Integer, default=2000)
    amount_ht: Mapped[int] = mapped_column(Integer, default=0)
    vat: Mapped[int] = mapped_column(Integer, default=0)
    amount_ttc: Mapped[int] = mapped_column(Integer, default=0)
    issued_on: Mapped[dt.date] = mapped_column(Date)
    valid_until: Mapped[dt.date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, default="draft", index=True)  # draft|sent|accepted|refused|expired
    notes: Mapped[str] = mapped_column(Text, default="")
    invoice_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_by: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


def _quote_dict(q: Quote, org_name: str = "") -> dict:
    status = q.status
    if status in ("draft", "sent") and q.valid_until < dt.date.today():
        status = "expired"
    return {"id": q.id, "number": q.number, "org_id": q.org_id, "org_name": org_name,
            "lines": json.loads(q.lines or "[]"), "plan_code": q.plan_code, "months": q.months,
            "seats": q.seats, "vat_rate": q.vat_rate, "amount_ht": q.amount_ht, "vat": q.vat,
            "amount_ttc": q.amount_ttc, "issued_on": q.issued_on.isoformat(),
            "valid_until": q.valid_until.isoformat(), "status": status, "notes": q.notes,
            "invoice_id": q.invoice_id, "created_by": q.created_by}


def _totals(lines: List[dict], vat_rate: int) -> tuple:
    ht = 0
    for ln in lines:
        qty = float(ln.get("qty") or 0)
        unit = int(ln.get("unit_price") or 0)
        if qty < 0 or unit < 0:
            raise HTTPException(status_code=400, detail="Quantities and prices cannot be negative")
        ht += round(qty * unit)
    vat = round(ht * vat_rate / 10000)
    return ht, vat, ht + vat


# ---------------- routes ----------------
router = APIRouter()


class QuoteLine(BaseModel):
    label: str
    qty: float = 1
    unit_price: int = 0           # centimes, before VAT


class QuoteBody(BaseModel):
    lines: List[QuoteLine] = []
    plan_code: str = ""
    months: int = 12
    seats: Optional[int] = None
    vat_rate: int = 2000
    valid_days: int = 30
    notes: str = ""


@router.post("/api/crm/orgs/{org_id}/quotes")
def quote_create(org_id: int, body: QuoteBody, user: dict = Depends(require_sales)) -> dict:
    if not accounts.get_org(org_id):
        raise HTTPException(status_code=404, detail="Organization not found")
    lines = [ln.model_dump() for ln in body.lines if ln.label.strip()]
    if not lines and body.plan_code:
        # a quote for a plan, priced from the plan: one line the customer can read
        plan = billing.get_plan(body.plan_code) or {}
        monthly = plan.get("price", 0) // (12 if plan.get("period") == "year" else 1)
        lines = [{"label": f"{plan.get('name_fr', body.plan_code)} — {body.months} mois",
                  "qty": body.months, "unit_price": monthly}]
    if not lines:
        raise HTTPException(status_code=400, detail="A quote needs at least one line")
    if body.months < 1:
        raise HTTPException(status_code=400, detail="At least one month")
    ht, vat, ttc = _totals(lines, body.vat_rate)
    today = dt.date.today()
    for _ in range(5):                      # the number is unique: retry a clash
        with db.session() as s:
            prefix = f"D-{today.year}-"
            last = s.scalar(select(func.max(Quote.number)).where(Quote.number.like(prefix + "%")))
            n = int(last.rsplit("-", 1)[1]) + 1 if last else 1
            q = Quote(number=f"{prefix}{n:05d}", org_id=org_id, lines=json.dumps(lines, ensure_ascii=False),
                      plan_code=body.plan_code, months=body.months, seats=body.seats,
                      vat_rate=body.vat_rate, amount_ht=ht, vat=vat, amount_ttc=ttc, issued_on=today,
                      valid_until=today + dt.timedelta(days=body.valid_days), notes=body.notes,
                      created_by=user["email"])
            s.add(q)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                continue
            out = _quote_dict(q)
        db.add_audit(user["email"], "quote", "organization", str(org_id), new=out["number"])
        return out
    raise HTTPException(status_code=409, detail="Could not number the quote; try again")


@router.get("/api/crm/quotes")
def quotes(status: str = "", org_id: Optional[int] = None, _: dict = Depends(require_sales)) -> list:
    with db.session() as s:
        q = select(Quote, accounts.Organization.name).join(
            accounts.Organization, accounts.Organization.id == Quote.org_id).order_by(Quote.id.desc())
        if org_id:
            q = q.where(Quote.org_id == org_id)
        rows = [_quote_dict(x, name) for x, name in s.execute(q.limit(1000)).all()]
    return [r for r in rows if not status or r["status"] == status]


@router.get("/api/quotes/{quote_id}")
def quote_detail(quote_id: int, user: dict = Depends(current_user)) -> dict:
    """One quote, for printing: staff see any, a customer's account holder theirs."""
    with db.session() as s:
        q = s.get(Quote, quote_id)
        if not q or (user["role"] not in ("admin", "sales") and not (
                user["role"] == "client_admin" and user.get("org_id") == q.org_id and q.status != "draft")):
            raise HTTPException(status_code=404, detail="Not found")
        out = _quote_dict(q)
    out["org"] = accounts.get_org(out["org_id"])
    out["seller"] = {k: os.getenv(f"SELLER_{k.upper()}", "") for k in ("name", "address", "ice", "rib")}
    return out


@router.post("/api/crm/quotes/{quote_id}/send")
def quote_send(quote_id: int, user: dict = Depends(require_sales)) -> dict:
    with db.session() as s:
        q = s.get(Quote, quote_id)
        if not q or q.status not in ("draft", "sent"):
            raise HTTPException(status_code=409, detail="Only a draft or sent quote can be sent")
        q.status = "sent"
        s.commit()
        out = _quote_dict(q)
    org = accounts.get_org(out["org_id"]) or {}
    if not org.get("email"):
        raise HTTPException(status_code=400, detail="The organization has no email address")
    lang = org.get("language") or "fr"
    mailer.queue(org["email"], "quote", lang, number=out["number"],
                 amount=billing._money(out["amount_ttc"]), valid=out["valid_until"],
                 link=f"{mailer.site_url()}/{lang}/quote/{quote_id}")
    with db.session() as s:
        s.add(crm.Activity(org_id=out["org_id"], kind="email", by_user=user["email"],
                           body=f"Devis {out['number']} envoyé à {org['email']}"))
        s.commit()
    return out


@router.post("/api/crm/quotes/{quote_id}/accept")
def quote_accept(quote_id: int, user: dict = Depends(require_sales)) -> dict:
    """The customer said yes: subscription at the quoted price, the invoice, the
    opportunity won, and the organization a customer."""
    with db.session() as s:
        q = s.get(Quote, quote_id)
        if not q or q.status not in ("draft", "sent"):
            raise HTTPException(status_code=409, detail="This quote cannot be accepted")
        out = _quote_dict(q)
    if out["status"] == "expired":
        raise HTTPException(status_code=409, detail="This quote has expired")
    org_id = out["org_id"]
    sub_id = None
    if out["plan_code"]:
        cur = billing.current_subscription(org_id)
        start = None
        if cur and billing.access_state(org_id) == "ok" and cur["status"] == "active":
            start = dt.date.fromisoformat(cur["ends_on"]) + dt.timedelta(days=1)
        sub_id = billing.start_subscription(
            org_id, out["plan_code"], status="active", days=out["months"] * 30 + out["months"] // 2,
            starts_on=start, seats=out["seats"], actor=user["email"],
            monthly=out["amount_ht"] // max(out["months"], 1))["id"]
    desc = "; ".join(f"{ln['label']}" for ln in out["lines"])[:240]
    inv = billing.create_invoice(org_id, out["amount_ht"], f"{out['number']} — {desc}", user["email"],
                                 vat_rate=out["vat_rate"], subscription_id=sub_id)
    with db.session() as s:
        q = s.get(Quote, quote_id)
        q.status, q.invoice_id = "accepted", inv["id"]
        o = s.get(accounts.Organization, org_id)
        if o:
            o.status = "customer"
        for opp in s.scalars(select(crm.Opportunity).where(
                crm.Opportunity.org_id == org_id, crm.Opportunity.stage.not_in(("won", "lost")),
                crm.Opportunity.deleted_at.is_(None))):
            opp.stage, opp.closed_at = "won", dt.datetime.utcnow()
            opp.value = opp.value or out["amount_ht"] * 12 // max(out["months"], 1)
        s.commit()
    db.add_audit(user["email"], "accept", "quote", out["number"], new=inv["number"])
    return {"quote": quote_detail(quote_id, user), "invoice": inv, "subscription_id": sub_id}


@router.post("/api/crm/quotes/{quote_id}/refuse")
def quote_refuse(quote_id: int, user: dict = Depends(require_sales)) -> dict:
    with db.session() as s:
        q = s.get(Quote, quote_id)
        if not q or q.status not in ("draft", "sent"):
            raise HTTPException(status_code=409, detail="This quote cannot be refused")
        q.status = "refused"
        s.commit()
        out = _quote_dict(q)
    db.add_audit(user["email"], "refuse", "quote", out["number"])
    return out


@router.get("/api/account/quotes")
def my_quotes(user: dict = Depends(current_user)) -> list:
    if user["role"] != "client_admin" or not user.get("org_id"):
        return []
    with db.session() as s:
        return [_quote_dict(q) for q in s.scalars(select(Quote).where(
            Quote.org_id == user["org_id"], Quote.status != "draft").order_by(Quote.id.desc()))]


# -- email a contact from the CRM, logged as an activity --
class EmailBody(BaseModel):
    to: str
    subject: str
    body: str
    lang: str = "fr"


@router.post("/api/crm/orgs/{org_id}/email")
def email_contact(org_id: int, body: EmailBody, user: dict = Depends(require_sales)) -> dict:
    if "@" not in body.to or not body.subject.strip() or not body.body.strip():
        raise HTTPException(status_code=400, detail="Recipient, subject and message required")
    if not accounts.get_org(org_id):
        raise HTTPException(status_code=404, detail="Organization not found")
    mailer.queue_text(body.to.strip(), body.subject.strip(), body.body.strip(), body.lang)
    with db.session() as s:
        a = crm.Activity(org_id=org_id, kind="email", by_user=user["email"],
                         body=f"→ {body.to}\n{body.subject}\n\n{body.body}"[:5000])
        s.add(a)
        s.commit()
        return crm._row(a, crm.ACT_F)


# -- duplicates --
@router.get("/api/crm/duplicates")
def duplicates(email: str = "", company: str = "", _: dict = Depends(require_sales)) -> dict:
    """Leads and organizations that look like the one being entered."""
    email, company = email.strip().lower(), company.strip()
    out = {"leads": [], "orgs": []}
    if not email and len(company) < 3:
        return out
    with db.session() as s:
        cond = []
        if email:
            cond.append(func.lower(crm.Lead.email) == email)
        if len(company) >= 3:
            cond.append(crm.Lead.company.ilike(f"%{company}%"))
        out["leads"] = [crm._row(x, crm.LEAD_F) for x in s.scalars(
            select(crm.Lead).where(or_(*cond), crm.Lead.deleted_at.is_(None)).limit(10))]
        O = accounts.Organization
        cond = []
        if email:
            cond.append(func.lower(O.email) == email)
            cond.append(O.email.ilike(f"%@{email.split('@')[-1]}") if "@" in email else O.id < 0)
        if len(company) >= 3:
            cond.append(O.name.ilike(f"%{company}%"))
        out["orgs"] = [accounts.org_dict(o) for o in s.scalars(
            select(O).where(or_(*cond), O.deleted_at.is_(None)).limit(10))]
    # an address at a free mail service says nothing about the firm
    free = ("gmail.com", "hotmail.com", "hotmail.fr", "yahoo.fr", "yahoo.com", "outlook.com", "live.fr")
    if email.endswith(free):
        out["orgs"] = [o for o in out["orgs"] if o["email"].lower() == email or
                       (len(company) >= 3 and company.lower() in o["name"].lower())]
    return out


# -- getting lists out (for accounting, for a mailing) and in (a bar association's list) --
def _csv(rows: List[dict], fields: List[str], name: str) -> StreamingResponse:
    buf = io.StringIO()
    buf.write("﻿")                     # Excel reads the Arabic correctly with a BOM
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})
    data = io.BytesIO(buf.getvalue().encode("utf-8"))
    return StreamingResponse(data, media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _centimes_to_mad(rows: List[dict], keys) -> List[dict]:
    for r in rows:
        for k in keys:
            if isinstance(r.get(k), int):
                r[k] = f"{r[k] / 100:.2f}"
    return rows


@router.get("/api/crm/export/{what}")
def export(what: str, user: dict = Depends(require_sales)) -> StreamingResponse:
    today = dt.date.today().isoformat()
    if what == "leads":
        rows = crm.leads(status="", q="", _=user)
        return _csv(rows, list(crm.LEAD_F), f"leads-{today}.csv")
    if what == "orgs":
        rows = crm.orgs(q="", status="", _=user)
        for r in rows:
            sub = r.pop("subscription") or {}
            r["plan"], r["subscription_status"] = sub.get("plan_code", ""), sub.get("status", "")
            r["ends_on"], r["seats"] = sub.get("ends_on", ""), sub.get("seats", "")
            r["monthly_price"] = sub.get("monthly_price", "")
        _centimes_to_mad(rows, ["monthly_price"])
        return _csv(rows, ["id", "name", "kind", "city", "ice", "email", "phone", "status",
                           "account_manager", "plan", "subscription_status", "ends_on", "seats",
                           "seats_used", "monthly_price", "health", "activity_30d", "created_at"],
                    f"organisations-{today}.csv")
    if what == "invoices":
        rows = _centimes_to_mad(billing.invoices(status="", _=user),
                                ["amount_ht", "vat", "amount_ttc", "paid", "balance"])
        return _csv(rows, ["number", "org_name", "description", "issued_on", "due_on", "amount_ht",
                           "vat", "amount_ttc", "paid", "balance", "status"], f"factures-{today}.csv")
    if what == "payments":
        with db.session() as s:
            rows = [{"number": n, "org": o, "amount": p.amount, "method": p.method,
                     "reference": p.reference, "paid_on": p.paid_on.isoformat(),
                     "recorded_by": p.recorded_by}
                    for p, n, o in s.execute(
                        select(billing.Payment, billing.Invoice.number, accounts.Organization.name)
                        .join(billing.Invoice, billing.Invoice.id == billing.Payment.invoice_id)
                        .join(accounts.Organization, accounts.Organization.id == billing.Invoice.org_id)
                        .order_by(billing.Payment.paid_on)).all()]
        return _csv(_centimes_to_mad(rows, ["amount"]),
                    ["paid_on", "number", "org", "amount", "method", "reference", "recorded_by"],
                    f"paiements-{today}.csv")
    raise HTTPException(status_code=404, detail="Unknown export")


@router.post("/api/crm/import/leads")
async def import_leads(file: UploadFile = File(...), user: dict = Depends(require_sales)) -> dict:
    """A CSV of prospects (full_name, email, phone, company, city, source). Rows whose
    email is already a lead or a contact are skipped, so importing twice is harmless."""
    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(status_code=413, detail="2 MB at most")
    text_ = raw.decode("utf-8-sig", errors="replace")
    sample = text_[:2000]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text_), delimiter=delim)
    fields = {f.strip().lower(): f for f in (reader.fieldnames or [])}
    if "email" not in fields and "full_name" not in fields:
        raise HTTPException(status_code=400, detail="Columns needed: full_name, email (and phone, company, city, source)")
    created = skipped = 0
    with db.session() as s:
        known = {e.lower() for e in s.scalars(select(crm.Lead.email)) if e} | \
                {e.lower() for e in s.scalars(select(crm.Contact.email)) if e}
        for row in reader:
            get = lambda k: (row.get(fields.get(k, ""), "") or "").strip()  # noqa: E731
            email, name = get("email").lower(), get("full_name")
            if not name and not email:
                continue
            if email and email in known:
                skipped += 1
                continue
            s.add(crm.Lead(full_name=name[:120], email=email[:160], phone=get("phone")[:40],
                           company=get("company")[:160], city=get("city")[:80],
                           source=get("source") if get("source") in ("website", "phone", "event", "referral", "other") else "other",
                           assigned_to=user["email"]))
            known.add(email)
            created += 1
        s.commit()
    db.add_audit(user["email"], "import", "lead", "csv", new=f"{created} created, {skipped} skipped")
    return {"created": created, "skipped": skipped}


# -- reports --
def _month(d: dt.date) -> str:
    return f"{d.year}-{d.month:02d}"


def _last_months(n: int) -> List[str]:
    today = dt.date.today()
    out, y, m = [], today.year, today.month
    for _ in range(n):
        out.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


@router.get("/api/crm/reports")
def reports(user: dict = Depends(require_sales)) -> dict:
    today = dt.date.today()
    months = _last_months(12)
    revenue = {m: 0 for m in months}
    new_customers = {m: 0 for m in months}
    churned = {m: 0 for m in months}
    with db.session() as s:
        for amount, paid_on in s.execute(select(billing.Payment.amount, billing.Payment.paid_on)):
            k = _month(paid_on)
            if k in revenue:
                revenue[k] += int(amount)
        subs = list(s.scalars(select(billing.Subscription)))
        leads = list(s.execute(select(crm.Lead.created_at, crm.Lead.status)).all())
        opps = list(s.scalars(select(crm.Opportunity).where(crm.Opportunity.deleted_at.is_(None))))
    by_org: dict = {}
    for x in subs:
        by_org.setdefault(x.org_id, []).append(x)
    mrr = 0
    paying = 0
    plans: dict = {}
    for org_id, rows in by_org.items():
        paid = [x for x in rows if x.status in ("active", "expired", "cancelled") and x.plan_code != "trial"]
        if paid:
            first = min(x.starts_on for x in paid)
            if _month(first) in new_customers:
                new_customers[_month(first)] += 1
            last_end = max(x.ends_on for x in paid)
            renewed = any(x.status in ("active", "trial") and x.ends_on >= today for x in rows)
            if last_end < today and not renewed and _month(last_end) in churned:
                churned[_month(last_end)] += 1
        live = [x for x in rows if x.status == "active" and x.starts_on <= today <= x.ends_on]
        if live:
            paying += 1
            x = max(live, key=lambda r: r.ends_on)
            mrr += billing.monthly_price(x)
            plans[x.plan_code] = plans.get(x.plan_code, 0) + 1
    since = dt.datetime.utcnow() - dt.timedelta(days=365)
    recent = [st for created, st in leads if created and created >= since]
    open_opps = [o for o in opps if o.stage not in ("won", "lost")]
    forecast = sum(o.value * STAGE_ODDS.get(o.stage, 0) for o in open_opps)
    won = sum(1 for o in opps if o.stage == "won")
    lost = sum(1 for o in opps if o.stage == "lost")
    return {
        "mrr": mrr, "arr": mrr * 12, "paying_customers": paying,
        "arpa": mrr // paying if paying else 0,
        "revenue": [{"month": m, "amount": revenue[m]} for m in months],
        "new_customers": [{"month": m, "count": new_customers[m]} for m in months],
        "churned": [{"month": m, "count": churned[m]} for m in months],
        "leads_12m": len(recent), "converted_12m": sum(1 for st in recent if st == "converted"),
        "conversion_rate": round(100 * sum(1 for st in recent if st == "converted") / len(recent), 1) if recent else 0,
        "win_rate": round(100 * won / (won + lost), 1) if won + lost else 0,
        "pipeline_open": sum(o.value for o in open_opps), "forecast": int(forecast),
        "stage_odds": STAGE_ODDS, "plans": plans,
    }
