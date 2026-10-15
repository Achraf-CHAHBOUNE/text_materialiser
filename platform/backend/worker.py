"""The background worker: what happens without anyone asking.

Every minute
    send the emails waiting in the outbox (when SMTP is set)
Once a day
    end the subscriptions whose last day has passed
    mark unpaid invoices past their date as overdue
    remind customers 30, 15 and 7 days before their subscription ends -- and their
      account manager -- once each, however often this runs
    email each reader's alerts: rulings published since their last one

Runs beside the API, never inside a request:

    python worker.py           # forever
    python worker.py --once    # one pass of everything, then exit (cron, tests)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time

from sqlalchemy import DateTime, String, select
from sqlalchemy.orm import Mapped, mapped_column

import accounts
import billing
import crm  # noqa: F401  -- its tables must exist
import db
import library
import mailer
import support  # noqa: F401

REMIND_DAYS = (30, 15, 7)


class WorkerState(db.Base):
    __tablename__ = "worker_state"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, default="")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


def _get(key: str) -> str:
    with db.session() as s:
        row = s.get(WorkerState, key)
        return row.value if row else ""


def _set(key: str, value: str) -> None:
    with db.session() as s:
        row = s.get(WorkerState, key) or WorkerState(key=key)
        row.value, row.updated_at = value, dt.datetime.utcnow()
        s.add(row)
        s.commit()


def expire_subscriptions(today: dt.date) -> int:
    n = 0
    with db.session() as s:
        for x in s.scalars(select(billing.Subscription).where(
                billing.Subscription.status.in_(("trial", "active")),
                billing.Subscription.ends_on < today)):
            x.status = "expired"
            s.add(db.AuditLog(actor="worker", action="expire", entity="organization",
                              entity_id=str(x.org_id), new_value=f"subscription #{x.id}"))
            n += 1
        s.commit()
    return n


def mark_overdue(today: dt.date) -> int:
    n = 0
    with db.session() as s:
        for inv in s.scalars(select(billing.Invoice).where(billing.Invoice.status == "sent",
                                                            billing.Invoice.due_on < today)):
            inv.status = "overdue"
            n += 1
        s.commit()
    return n


def renewal_reminders(today: dt.date) -> int:
    sent = 0
    with db.session() as s:
        subs = list(s.scalars(select(billing.Subscription).where(
            billing.Subscription.status.in_(("trial", "active")),
            billing.Subscription.ends_on.in_([today + dt.timedelta(days=d) for d in REMIND_DAYS]))))
    for x in subs:
        days = (x.ends_on - today).days
        org = accounts.get_org(x.org_id)
        if not org:
            continue
        lang = org.get("language") or "ar"
        people = {m["email"] for m in accounts.org_members(x.org_id)
                  if m["role"] == "client_admin" and m["status"] == "active"}
        if org.get("email"):
            people.add(org["email"])
        for email in people:
            sent += mailer.queue(email, "renewal", lang, dedupe=f"renewal:{x.id}:{days}:{email}",
                                 org=org["name"], days=days, end=x.ends_on.isoformat(),
                                 link=f"{mailer.site_url()}/{lang}/support")
        manager = org.get("account_manager") or ""
        for email in ([manager] if manager else mailer.staff_addresses(("admin", "sales"))):
            sent += mailer.queue(email, "renewal_staff", "fr", dedupe=f"renewal_staff:{x.id}:{days}:{email}",
                                 org=org["name"], days=days, end=x.ends_on.isoformat(),
                                 link=f"{mailer.site_url()}/fr/crm/orgs/{x.org_id}")
    return sent


def run_alerts(now: dt.datetime) -> int:
    """Each alert due today gets one email listing what was published since its last."""
    sent = 0
    with db.session() as s:
        alerts = list(s.scalars(select(library.Alert).where(library.Alert.active == 1)))
    for a in alerts:
        every = dt.timedelta(days=1 if a.frequency == "daily" else 7)
        since = a.last_sent_at or (now - every)
        if now - since < every - dt.timedelta(minutes=30):
            continue
        user = db.get_user(a.user_email)
        if not user or user["status"] != "active":
            continue
        if user["role"] in ("client", "client_admin") and billing.access_state(user.get("org_id")) != "ok":
            continue
        f = json.loads(a.filters or "{}")
        found = db.browse_rulings(chamber=f.get("chamber", ""), year=f.get("year", ""),
                                  city=f.get("city", ""), theme=f.get("theme", ""), q=a.query,
                                  limit=2000, lang=a.lang)
        ids = [r["doc_id"] for r in found["items"]]
        with db.session() as s:
            fresh = set(s.scalars(select(db.Decision.doc_id).where(
                db.Decision.doc_id.in_(ids), db.Decision.created_at > since))) if ids else set()
        rows = [r for r in found["items"] if r["doc_id"] in fresh][:20]
        if rows:
            lines = []
            for r in rows:
                summary = (r.get("abstract_fr") if a.lang == "fr" else "") or r.get("rule") or r.get("abstract") or ""
                lines.append(f"• {r['decision_no']} — {r['date']}\n  {summary[:220]}\n  "
                             f"{mailer.site_url()}/{a.lang}/ruling/{r['doc_id']}")
            q = "&".join(f"{k}={v}" for k, v in (("q", a.query), ("theme", f.get("theme", "")),
                                                  ("year", f.get("year", "")), ("city", f.get("city", ""))) if v)
            chamber = f.get("chamber") or "الكل"
            sent += mailer.queue(a.user_email, "alert", a.lang, name=a.name, count=len(fresh),
                                 items="\n\n".join(lines),
                                 link=f"{mailer.site_url()}/{a.lang}/browse/{chamber}?{q}")
        with db.session() as s:
            row = s.get(library.Alert, a.id)
            row.last_sent_at = now
            s.commit()
    return sent


def daily(force: bool = False) -> dict:
    today = dt.date.today()
    if not force and _get("daily") == today.isoformat():
        return {}
    out = {"expired": expire_subscriptions(today), "overdue": mark_overdue(today),
           "reminders": renewal_reminders(today), "alerts": run_alerts(dt.datetime.utcnow())}
    _set("daily", today.isoformat())
    return out


def once(force_daily: bool = False) -> dict:
    out = daily(force_daily)
    out["mail"] = mailer.send_pending()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Background jobs: email, expiries, reminders, alerts")
    ap.add_argument("--once", action="store_true", help="one pass, then exit")
    ap.add_argument("--interval", type=int, default=int(os.getenv("WORKER_INTERVAL", "60")))
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    db.init_db()
    billing.seed_plans()
    if args.once:
        print(once(force_daily=True))
        return 0
    while True:
        try:
            out = once()
            if any(v for k, v in out.items() if k != "mail") or (out.get("mail") or {}).get("sent"):
                print(dt.datetime.now().isoformat(timespec="seconds"), out, flush=True)
        except Exception as e:                       # one bad pass must not stop the worker
            print("worker error:", type(e).__name__, e, flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
