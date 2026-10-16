"""The background worker: what happens without anyone asking.

Every minute
    import the deliveries uploaded too large to import during the request
    send the emails waiting in the outbox (when SMTP is set)
Once a day
    end the subscriptions whose last day has passed
    mark unpaid invoices past their date as overdue
    remind customers 30, 15 and 7 days before their subscription ends -- and their
      account manager -- once each, however often this runs
    email each reader's alerts: rulings published since their last one
    email the admin their morning: new readers, transfers, contracts to chase, alerts

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

from sqlalchemy import select

import accounts
import billing
import db
import importer
import library
import limits
import logs
import mailer
import settings

REMIND_DAYS = (30, 15, 7)


def admin_digest(today: dt.date) -> int:
    """The admin's morning: new readers, money received, contracts to chase, alerts."""
    import contracts
    import insights
    yesterday = today - dt.timedelta(days=1)
    with db.session() as s:
        new = list(s.scalars(select(db.User.email).where(db.User.role.in_(("client", "client_admin")),
                                                         db.User.created_at >= dt.datetime.combine(yesterday, dt.time.min),
                                                         db.User.created_at < dt.datetime.combine(today, dt.time.min))))
        got = list(s.execute(select(contracts.Transfer.amount, accounts.Organization.name)
                             .join(accounts.Organization, accounts.Organization.id == contracts.Transfer.org_id)
                             .where(contracts.Transfer.paid_on == yesterday)).all())
    every = contracts.all_contracts(status="", _={})
    ending = [c for c in every if c["status"] == "active" and c["days_left"] in (30, 15, 7, 1)]
    waiting = [c for c in every if c["status"] == "awaiting_payment"]
    high = [a for a in insights.alerts(_={}) if a["level"] == "high"]
    if not (new or got or ending or waiting or high):
        return 0
    lines = [f"Nouveaux lecteurs hier : {len(new)}"] + [f"  • {e}" for e in new]
    lines += [f"Virements reçus hier : {len(got)}"] + [f"  • {name} — {a / 100:.2f} MAD" for a, name in got]
    lines += [f"Contrats qui se terminent : {len(ending)}"] + [f"  • {c['org_name']} — {c['ends_on']} ({c['days_left']} j)" for c in ending]
    lines += [f"Contrats en attente de paiement : {len(waiting)}"] + [f"  • {c['org_name']} — {c['number']}" for c in waiting]
    lines += [f"Alertes importantes : {len(high)}"] + [f"  • {a['kind']} — {a.get('email') or a.get('org', '')}" for a in high[:10]]
    sent = 0
    for email in mailer.staff_addresses(("admin",)):
        sent += mailer.queue(email, "digest", "fr", dedupe=f"admin_digest:{today.isoformat()}:{email}",
                             body="\n".join(lines), link=f"{mailer.site_url()}/fr/crm")
    return sent


def _get(key: str) -> str:
    with db.session() as s:
        row = s.get(db.WorkerState, key)
        return row.value if row else ""


def _set(key: str, value: str) -> None:
    with db.session() as s:
        row = s.get(db.WorkerState, key) or db.WorkerState(key=key)
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
    # Several workers may run; the lock lets one of them do the day's jobs, and the
    # date it records tells the others the day is done.
    with db.exclusive("worker:daily") as mine:
        today = dt.date.today()
        if not mine or (not force and _get("daily") == today.isoformat()):
            return {}
        out = {"expired": expire_subscriptions(today), "overdue": mark_overdue(today),
               "reminders": renewal_reminders(today), "alerts": run_alerts(dt.datetime.utcnow()),
               "admin_digest": admin_digest(today), "limits_pruned": limits.prune()}
        _set("daily", today.isoformat())
        return out


def enrich_new() -> dict:
    """With AUTO_ENRICH=1: a subject and a summary from the model for the rulings that
    arrived printing none, each asked once. One worker at a time."""
    if not settings.S.auto_enrich:
        return {}
    import enrich
    with db.exclusive("worker:enrich") as mine:
        if not mine:
            return {}
        got = enrich.run(limit=settings.S.enrich_per_pass, only_new=True, quiet=True)
        return {k: got[k] for k in ("processed", "subject", "abstract", "proposed", "failed", "cost")}             if got.get("processed") else {}


def once(force_daily: bool = False) -> dict:
    out = daily(force_daily)
    # deliveries uploaded too large to import during the request
    out["imports"] = importer.run_queued(publish=settings.S.auto_publish)
    out["enriched"] = enrich_new()
    with db.exclusive("worker:mail") as mine:           # one sender, so no email goes twice
        out["mail"] = mailer.send_pending() if mine else {}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Background jobs: email, expiries, reminders, alerts")
    ap.add_argument("--once", action="store_true", help="one pass, then exit")
    ap.add_argument("--interval", type=int, default=int(os.getenv("WORKER_INTERVAL", "60")))
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    log = logs.setup("worker")
    settings.check()
    db.init_db()
    billing.seed_plans()
    if args.once:
        print(once(force_daily=True))
        return 0
    while True:
        try:
            out = once()
            if any(v for k, v in out.items() if k != "mail") or (out.get("mail") or {}).get("sent"):
                log.info("pass", extra={"done": out})
        except Exception:                            # one bad pass must not stop the worker
            log.exception("pass failed")
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
