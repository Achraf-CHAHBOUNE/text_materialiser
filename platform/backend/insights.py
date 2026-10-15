"""The admin's view of the readers: who they are, what they pay, what they read.

Every view, search, download, translation and sign-in is already written to
client_activity as it happens; sessions keep the address and device of each sign-in;
downloads keep the reference printed in the file. This module only reads them back,
for the people allowed to see them (admin and sales), three ways:

    /api/crm/users            every reader, with their subscription, money and use
    /api/crm/users/{email}    one reader: timeline, downloads, devices, invoices
    /api/crm/usage            the whole platform: who is active, what is read,
                              what is searched -- and what is searched and not found

Readers never see any of this about each other; it is ours, to run the service.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, text

import accounts
import billing
import db
import library
from deps import CLIENTS, require_sales

ACTIONS = ("view", "download", "search", "search_empty", "translate", "login")


def ensure_indexes() -> None:
    """Reading activity by date and by person stays fast as it grows."""
    with db._engine.begin() as c:
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_activity_ts ON client_activity (ts)"))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_activity_actor_ts ON client_activity (actor, ts)"))


def _since(days: int) -> dt.datetime:
    return dt.datetime.utcnow() - dt.timedelta(days=days)


def _decisions(ids) -> dict:
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    with db.session() as s:
        return {d.doc_id: {"decision_no": d.decision_no, "date": d.decision_date, "chamber": d.category}
                for d in s.scalars(select(db.Decision).where(db.Decision.doc_id.in_(ids)))}


def _money_by_org() -> dict:
    """{org_id: (paid, still owed)} in centimes."""
    with db.session() as s:
        paid = dict(s.execute(select(billing.Invoice.org_id, func.sum(billing.Payment.amount))
                              .join(billing.Payment, billing.Payment.invoice_id == billing.Invoice.id)
                              .group_by(billing.Invoice.org_id)).all())
    owed: dict = {}
    for i in billing.list_invoices():
        if i["status"] in ("sent", "overdue"):
            owed[i["org_id"]] = owed.get(i["org_id"], 0) + i["balance"]
    return {o: (int(paid.get(o, 0) or 0), int(owed.get(o, 0))) for o in set(paid) | set(owed)}


router = APIRouter()


@router.get("/api/crm/users")
def users(q: str = "", _: dict = Depends(require_sales)) -> list:
    """Every reader with what they pay and what they did in the last 30 days."""
    since = _since(30)
    with db.session() as s:
        query = select(db.User).where(db.User.role.in_(CLIENTS))
        if q.strip():
            query = query.where(db.User.email.ilike(f"%{q.strip()}%") | db.User.full_name.ilike(f"%{q.strip()}%"))
        people = list(s.scalars(query.order_by(db.User.email)))
        counts: dict = {}
        for actor, action, n in s.execute(
                select(db.ClientActivity.actor, db.ClientActivity.action, func.count())
                .where(db.ClientActivity.ts >= since).group_by(db.ClientActivity.actor, db.ClientActivity.action)):
            counts.setdefault(actor, {})[action] = int(n)
        totals = dict(s.execute(select(db.ClientActivity.actor, func.count())
                                .where(db.ClientActivity.action == "view")
                                .group_by(db.ClientActivity.actor)).all())
        last = dict(s.execute(select(db.ClientActivity.actor, func.max(db.ClientActivity.ts))
                              .group_by(db.ClientActivity.actor)).all())
        live = dict(s.execute(select(accounts.UserSession.user_id, func.count())
                              .where(accounts.UserSession.revoked_at.is_(None))
                              .group_by(accounts.UserSession.user_id)).all())
        orgs = {o.id: o.name for o in s.scalars(select(accounts.Organization))}
    money = _money_by_org()
    out = []
    for u in people:
        c = counts.get(u.email, {})
        sub = billing.current_subscription(u.org_id)
        paid, owed = money.get(u.org_id, (0, 0))
        seen = last.get(u.email)
        out.append({
            "email": u.email, "full_name": u.full_name or "", "role": u.role, "status": u.status,
            "org_id": u.org_id, "org_name": orgs.get(u.org_id, ""),
            "plan": sub["plan_code"] if sub else "", "access": billing.access_state(u.org_id),
            "ends_on": sub["ends_on"] if sub else "",
            "last_login": u.last_login.isoformat() if u.last_login else "",
            "last_seen": seen.isoformat() if seen else "",
            "reads_30d": c.get("view", 0), "downloads_30d": c.get("download", 0),
            "searches_30d": c.get("search", 0) + c.get("search_empty", 0),
            "logins_30d": c.get("login", 0), "reads_total": int(totals.get(u.email, 0)),
            "org_paid": paid, "org_owed": owed, "sessions": int(live.get(u.id, 0)),
        })
    return out


@router.get("/api/crm/users/{email}")
def user_detail(email: str, days: int = 30, _: dict = Depends(require_sales)) -> dict:
    """One reader, everything: who, what they pay, what they read, from where."""
    u = db.get_user(email)
    if not u or u["role"] not in CLIENTS:
        raise HTTPException(status_code=404, detail="Not found")
    days = max(1, min(days, 365))
    since = _since(days)
    A = db.ClientActivity
    with db.session() as s:
        by_action = dict(s.execute(select(A.action, func.count()).where(A.actor == email)
                                   .group_by(A.action)).all())
        recent = dict(s.execute(select(A.action, func.count()).where(A.actor == email, A.ts >= since)
                                .group_by(A.action)).all())
        rows = list(s.execute(select(A.ts, A.action, A.decision_id).where(A.actor == email)
                              .order_by(A.ts.desc()).limit(400)).all())
        series_rows = list(s.execute(select(A.ts, A.action).where(A.actor == email, A.ts >= since)).all())
        viewed = [d for d, in s.execute(select(A.decision_id).where(A.actor == email, A.action == "view",
                                                                     A.ts >= since))]
        sessions = [{"ip": x.ip, "device": x.device, "created_at": x.created_at.isoformat(),
                     "last_seen": x.last_seen.isoformat() if x.last_seen else "",
                     "ended": x.revoked_at.isoformat() if x.revoked_at else "", "why": x.revoked_why}
                    for x in s.scalars(select(accounts.UserSession).where(accounts.UserSession.user_id == u["id"])
                                       .order_by(accounts.UserSession.created_at.desc()).limit(50))]
        dls = list(s.scalars(select(library.Download).where(library.Download.user_email == email)
                             .order_by(library.Download.at.desc()).limit(200)))
    decs = _decisions([r[2] for r in rows if r[1] in ("view", "download", "translate")] +
                      [d.doc_id for d in dls] + viewed)
    timeline = []
    for ts, action, ref in rows:
        item = {"ts": ts.isoformat(), "action": action}
        if action in ("search", "search_empty"):
            item["query"] = ref
        elif ref:
            item.update(doc_id=ref, **decs.get(ref, {}))
        timeline.append(item)
    # one row per day, so a chart can show when they use it
    series: dict = {}
    for ts, action in series_rows:
        k = ts.date().isoformat()
        day_ = series.setdefault(k, {"day": k, "view": 0, "download": 0, "search": 0})
        key = "search" if action.startswith("search") else action
        if key in day_:
            day_[key] += 1
    chambers: dict = {}
    for d in viewed:
        ch = decs.get(d, {}).get("chamber")
        if ch:
            chambers[ch] = chambers.get(ch, 0) + 1
    org = accounts.get_org(u.get("org_id"))
    paid, owed = _money_by_org().get(u.get("org_id"), (0, 0))
    profile = {k: u.get(k) for k in ("email", "full_name", "phone", "role", "status", "language",
                                     "org_id", "mfa", "created_at", "last_login")}
    return {
        "user": profile, "org": org,
        "subscription": billing.current_subscription(u.get("org_id")),
        "access": billing.access_state(u.get("org_id")),
        "quota": billing.daily_downloads(u.get("org_id")),
        "downloads_today": library.downloads_today(email),
        "money": {"paid": paid, "owed": owed,
                  "invoices": billing.list_invoices(u["org_id"]) if u.get("org_id") else []},
        "totals": {a: int(by_action.get(a, 0)) for a in ACTIONS},
        "recent": {a: int(recent.get(a, 0)) for a in ACTIONS}, "days": days,
        "series": sorted(series.values(), key=lambda r: r["day"]),
        "chambers": sorted(({"chamber": k, "count": v} for k, v in chambers.items()), key=lambda r: -r["count"]),
        "timeline": timeline,
        "downloads": [{"ref": d.ref, "doc_id": d.doc_id, "at": d.at.isoformat(), **decs.get(d.doc_id, {})} for d in dls],
        "sessions": sessions,
        "audit": db.audit_for(email)[:50],
    }


@router.post("/api/crm/users/{email}/logout")
def force_logout(email: str, user: dict = Depends(require_sales)) -> dict:
    """End every session of a reader, now: they sign in again (shared password, lost phone)."""
    u = db.get_user(email)
    if not u or u["role"] not in CLIENTS:
        raise HTTPException(status_code=404, detail="Not found")
    n = accounts.end_sessions(u["id"], f"signed out by {user['email']}")
    db.add_audit(user["email"], "force_logout", "user", email, new=f"{n} session(s)")
    return {"ended": n}


@router.get("/api/crm/usage")
def usage(days: int = 30, _: dict = Depends(require_sales)) -> dict:
    """The whole platform over a period: activity per day, what is read, downloaded and
    searched, by whom -- and the searches that found nothing."""
    days = max(1, min(days, 365))
    since = _since(days)
    A = db.ClientActivity
    readers = select(db.User.email).where(db.User.role.in_(CLIENTS))
    with db.session() as s:
        rows = list(s.execute(select(A.ts, A.action, A.actor).where(A.ts >= since, A.actor.in_(readers))).all())

        def top(action: str, limit: int = 15):
            return list(s.execute(select(A.decision_id, func.count(), func.count(func.distinct(A.actor)))
                                  .where(A.ts >= since, A.action == action, A.actor.in_(readers), A.decision_id != "")
                                  .group_by(A.decision_id).order_by(func.count().desc()).limit(limit)).all())

        top_read, top_dl = top("view"), top("download")
        searches = list(s.execute(select(func.lower(A.decision_id), func.count())
                                  .where(A.ts >= since, A.action == "search", A.actor.in_(readers))
                                  .group_by(func.lower(A.decision_id)).order_by(func.count().desc()).limit(20)).all())
        empty = list(s.execute(select(func.lower(A.decision_id), func.count(), func.max(A.ts))
                               .where(A.ts >= since, A.action == "search_empty", A.actor.in_(readers))
                               .group_by(func.lower(A.decision_id)).order_by(func.count().desc()).limit(30)).all())
        n_readers = s.scalar(select(func.count()).select_from(db.User).where(db.User.role.in_(CLIENTS),
                                                                               db.User.status == "active")) or 0
    series: dict = {}
    per_user: dict = {}
    active_users = set()
    for ts, action, actor in rows:
        k = ts.date().isoformat()
        d = series.setdefault(k, {"day": k, "users": set(), "view": 0, "download": 0, "search": 0})
        d["users"].add(actor)
        key = "search" if action.startswith("search") else action
        if key in d:
            d[key] += 1
        active_users.add(actor)
        pu = per_user.setdefault(actor, {"email": actor, "view": 0, "download": 0, "search": 0})
        if key in pu:
            pu[key] += 1
    decs = _decisions([r[0] for r in top_read + top_dl])
    totals = {a: sum(1 for _, x, _ in rows if x == a) for a in ACTIONS}
    return {
        "days": days, "readers": n_readers, "active_readers": len(active_users), "totals": totals,
        "series": [{"day": d["day"], "users": len(d["users"]), "view": d["view"], "download": d["download"],
                    "search": d["search"]} for d in sorted(series.values(), key=lambda r: r["day"])],
        "top_read": [{"doc_id": i, "count": int(n), "readers": int(u), **decs.get(i, {})} for i, n, u in top_read],
        "top_downloaded": [{"doc_id": i, "count": int(n), "readers": int(u), **decs.get(i, {})} for i, n, u in top_dl],
        "top_searches": [{"query": q, "count": int(n)} for q, n in searches],
        "empty_searches": [{"query": q, "count": int(n), "last": t.isoformat() if t else ""} for q, n, t in empty],
        "top_users": sorted(per_user.values(), key=lambda r: -(r["view"] + r["download"]))[:15],
    }


@router.get("/api/crm/activity/export")
def export_activity(days: int = 30, email: str = "", _: dict = Depends(require_sales)) -> StreamingResponse:
    """Every action of the period, one line each, for Excel."""
    days = max(1, min(days, 365))
    A = db.ClientActivity
    with db.session() as s:
        q = select(A.ts, A.actor, A.action, A.decision_id).where(A.ts >= _since(days))
        if email:
            q = q.where(A.actor == email)
        rows = list(s.execute(q.order_by(A.ts)).all())
    decs = _decisions([r[3] for r in rows if r[2] in ("view", "download", "translate")])
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf)
    w.writerow(["date", "user", "action", "ruling_or_search", "decision_no", "chamber"])
    for ts, actor, action, ref in rows:
        d = decs.get(ref, {}) if action in ("view", "download", "translate") else {}
        w.writerow([ts.isoformat(timespec="seconds"), actor, action, ref, d.get("decision_no", ""), d.get("chamber", "")])
    name = f"activite-{email or 'tous'}-{dt.date.today().isoformat()}.csv"
    return StreamingResponse(io.BytesIO(buf.getvalue().encode("utf-8")), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})
