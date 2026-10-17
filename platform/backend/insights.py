"""The admin's view of the readers: who they are, what they pay, what they read.

Every view, search, download, translation and sign-in is already written to
client_activity as it happens; sessions keep the address and device of each sign-in;
downloads keep the reference printed in the file. This module only reads them back,
for the people allowed to see them (admin and sales):

    /api/crm/users            every reader, with their subscription, money and use
    /api/crm/users/{email}    one reader: timeline, downloads, devices, invoices
    /api/crm/usage            the whole platform: who is active, what is read,
                              what is searched -- and what is searched and not found
    /api/crm/alerts           what deserves a look: shared accounts, limits hit, quiet payers
    /api/crm/downloads/{ref}  who downloaded the file a reference was printed in
    /api/crm/overview         the first screen: readers, money, contracts, alerts

Readers never see any of this about each other; it is ours, to run the service.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import DateTime, Integer, String, Text, case, func, select, text
from sqlalchemy.orm import Mapped, mapped_column

import clock
import accounts
import billing
import db
import library
import mailer
from deps import CLIENTS, require_sales

ACTIONS = ("view", "download", "search", "search_empty", "translate", "login")


def ensure_indexes() -> None:
    """Reading activity by date and by person stays fast as it grows."""
    with db._engine.begin() as c:
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_activity_ts ON client_activity (ts)"))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_activity_actor_ts ON client_activity (actor, ts)"))


def _since(days: int) -> dt.datetime:
    return clock.utcnow() - dt.timedelta(days=days)


def _decisions(ids) -> dict:
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    with db.session() as s:
        return {d.doc_id: {"decision_no": d.decision_no, "date": d.decision_date, "chamber": d.category}
                for d in s.scalars(select(db.Decision).where(db.Decision.doc_id.in_(ids)))}


def _money_by_org() -> dict:
    """{org_id: (paid, still owed)} in centimes -- transfers and contracts (contracts.py)."""
    import contracts
    return contracts.money_by_org()


def _reading(email: Optional[str], since: dt.date) -> dict:
    """{actor: (seconds, seconds in French)} of reading since a date."""
    R = library.ReadingTime
    with db.session() as s:
        q = select(R.actor, R.lang, func.sum(R.seconds)).where(R.day >= since).group_by(R.actor, R.lang)
        if email:
            q = q.where(R.actor == email)
        out: dict = {}
        for actor, lang, secs in s.execute(q):
            total, fr = out.get(actor, (0, 0))
            out[actor] = (total + int(secs or 0), fr + (int(secs or 0) if lang == "fr" else 0))
    return out


class UserNote(db.Base):
    """What the admin wants to remember about a reader: a call, an agreement, a warning."""
    __tablename__ = "user_notes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, index=True)
    body: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str] = mapped_column(String, default="")
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=clock.utcnow)


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
    reading = _reading(None, (clock.utcnow() - dt.timedelta(days=30)).date())
    subs = billing.subscriptions_for(u.org_id for u in people)
    out = []
    for u in people:
        c = counts.get(u.email, {})
        secs, fr = reading.get(u.email, (0, 0))
        sub = subs.get(u.org_id)
        paid, owed = money.get(u.org_id, (0, 0))
        seen = last.get(u.email)
        out.append({
            "email": u.email, "full_name": u.full_name or "", "role": u.role, "status": u.status,
            "org_id": u.org_id, "org_name": orgs.get(u.org_id, ""),
            "plan": sub["plan_code"] if sub else "", "access": billing.access_of(sub),
            "ends_on": sub["ends_on"] if sub else "",
            "last_login": u.last_login.isoformat() if u.last_login else "",
            "last_seen": seen.isoformat() if seen else "",
            "reads_30d": c.get("view", 0), "downloads_30d": c.get("download", 0),
            "searches_30d": c.get("search", 0) + c.get("search_empty", 0),
            "logins_30d": c.get("login", 0), "reads_total": int(totals.get(u.email, 0)),
            "org_paid": paid, "org_owed": owed, "sessions": int(live.get(u.id, 0)),
            "reading_minutes_30d": secs // 60, "french_share": round(100 * fr / secs) if secs else 0,
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
    import contracts
    org = accounts.get_org(u.get("org_id"))
    paid, owed = _money_by_org().get(u.get("org_id"), (0, 0))
    R = library.ReadingTime
    with db.session() as s:
        per_doc = list(s.execute(select(R.doc_id, func.sum(R.seconds)).where(R.actor == email, R.day >= since.date())
                                 .group_by(R.doc_id).order_by(func.sum(R.seconds).desc()).limit(10)).all())
        notes = [{"id": n.id, "body": n.body, "author": n.author, "at": n.at.isoformat()}
                 for n in s.scalars(select(UserNote).where(UserNote.email == email).order_by(UserNote.at.desc()))]
    secs, fr = _reading(email, since.date()).get(email, (0, 0))
    long_reads = _decisions([d for d, _ in per_doc])
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
        "reading": {"minutes": secs // 60, "french_share": round(100 * fr / secs) if secs else 0,
                    "longest": [{"doc_id": d, "minutes": int(n) // 60, **long_reads.get(d, {})} for d, n in per_doc]},
        "contracts": contracts.contracts_for(u["org_id"]) if u.get("org_id") else [],
        "notes": notes,
    }


class NoteBody(BaseModel):
    body: str


@router.post("/api/crm/users/{email}/notes")
def add_note(email: str, body: NoteBody, user: dict = Depends(require_sales)) -> dict:
    if not db.get_user(email) or not body.body.strip():
        raise HTTPException(status_code=400, detail="A note needs a reader and a text")
    with db.session() as s:
        n = UserNote(email=email, body=body.body.strip()[:4000], author=user["email"])
        s.add(n)
        s.commit()
        return {"id": n.id, "body": n.body, "author": n.author, "at": n.at.isoformat()}


class MailBody(BaseModel):
    subject: str
    body: str


@router.post("/api/crm/users/{email}/email")
def email_reader(email: str, body: MailBody, user: dict = Depends(require_sales)) -> dict:
    """Write to a reader from their page; the message is kept as a note too."""
    u = db.get_user(email)
    if not u or not body.subject.strip() or not body.body.strip():
        raise HTTPException(status_code=400, detail="Subject and message required")
    mailer.queue_text(email, body.subject.strip(), body.body.strip(), u.get("language", "ar"))
    with db.session() as s:
        s.add(UserNote(email=email, author=user["email"],
                       body=f"✉ {body.subject.strip()}\n\n{body.body.strip()}"[:4000]))
        s.commit()
    return {"ok": True}


@router.get("/api/crm/downloads/{ref}")
def find_download(ref: str, _: dict = Depends(require_sales)) -> dict:
    """A Word file found circulating: the reference at the foot of its pages says who
    downloaded it, when, and which ruling it is."""
    with db.session() as s:
        d = s.scalar(select(library.Download).where(func.upper(library.Download.ref) == ref.strip().upper()))
        if not d:
            raise HTTPException(status_code=404, detail="No download with this reference")
        out = {"ref": d.ref, "email": d.user_email, "org_id": d.org_id, "doc_id": d.doc_id, "at": d.at.isoformat()}
    out.update(_decisions([out["doc_id"]]).get(out["doc_id"], {}))
    out["org"] = (accounts.get_org(out["org_id"]) or {}).get("name", "")
    return out


@router.get("/api/crm/alerts")
def alerts(_: dict = Depends(require_sales)) -> list:
    return _alerts()


def _alerts(all_c: Optional[list] = None, money: Optional[dict] = None) -> list:
    """What deserves a look: an account used like a shared one, a reader at the download
    limit day after day, reading too fast to be a person, a paying reader gone quiet,
    contracts unpaid or ending. Newest and most serious first."""
    import contracts
    today = dt.date.today()
    week = _since(7)
    out = []
    with db.session() as s:
        readers = {u.id: u for u in s.scalars(select(db.User).where(db.User.role.in_(CLIENTS), db.User.status == "active"))}
        ips: dict = {}
        devices: dict = {}
        for x in s.scalars(select(accounts.UserSession).where(accounts.UserSession.created_at >= week,
                                                               accounts.UserSession.user_id.in_(list(readers)))):
            day_ = x.created_at.date()
            ips.setdefault((x.user_id, day_), set()).add(x.ip)
            devices.setdefault(x.user_id, set()).add(x.device)
        dl_days = list(s.execute(select(library.Download.user_email, func.date(library.Download.at), func.count())
                                 .where(library.Download.at >= _since(30))
                                 .group_by(library.Download.user_email, func.date(library.Download.at))).all())
        throttled = list(s.execute(select(db.AuditLog.actor, func.count(), func.max(db.AuditLog.ts))
                                   .where(db.AuditLog.action == "throttled", db.AuditLog.ts >= _since(30))
                                   .group_by(db.AuditLog.actor)).all())
        last = dict(s.execute(select(db.ClientActivity.actor, func.max(db.ClientActivity.ts))
                              .group_by(db.ClientActivity.actor)).all())
    by_email = {u.email: u for u in readers.values()}
    subs = billing.subscriptions_for(u.org_id for u in readers.values())
    for (uid, day_), seen in ips.items():
        if len(seen) >= 3:
            u = readers[uid]
            out.append({"kind": "shared_ips", "level": "high", "email": u.email, "count": len(seen),
                        "at": day_.isoformat(), "detail": ", ".join(sorted(seen))[:200]})
    for uid, seen in devices.items():
        if len(seen) >= 3:
            out.append({"kind": "many_devices", "level": "medium", "email": readers[uid].email,
                        "count": len(seen), "at": today.isoformat(), "detail": ""})
    hits: dict = {}
    for email, day_, n in dl_days:
        u = by_email.get(email)
        if u and n >= max(1, billing.quota_of(subs.get(u.org_id))):
            hits.setdefault(email, []).append(str(day_))
    for email, days_ in hits.items():
        out.append({"kind": "quota_hit", "level": "high" if len(days_) >= 3 else "medium", "email": email,
                    "count": len(days_), "at": max(days_), "detail": ""})
    for email, n, at in throttled:
        out.append({"kind": "too_fast", "level": "high", "email": email, "count": int(n),
                    "at": at.isoformat() if at else "", "detail": ""})
    now = clock.utcnow()
    for u in readers.values():
        if billing.access_of(subs.get(u.org_id)) != "ok":
            continue
        seen = last.get(u.email)
        quiet = (now - (seen or u.created_at or now)).days     # silent since last read, or since the account was made
        if quiet >= 15:
            out.append({"kind": "inactive", "level": "low", "email": u.email, "count": quiet or 0,
                        "at": seen.isoformat() if seen else "", "detail": ""})
    if all_c is None:
        all_c = contracts.all_contracts(status="", _={})
    waiting: dict = {}
    for c in all_c:
        if c["status"] == "awaiting_payment":
            waiting[c["org_id"]] = waiting.get(c["org_id"], 0) + c["balance"]
            out.append({"kind": "awaiting_payment", "level": "medium", "org_id": c["org_id"], "org": c["org_name"],
                        "count": c["amount_ttc"], "at": c["created_at"], "detail": c["number"]})
        elif c["status"] == "active" and c["days_left"] <= 30:
            out.append({"kind": "ending", "level": "medium" if c["days_left"] > 7 else "high", "org_id": c["org_id"],
                        "org": c["org_name"], "count": c["days_left"], "at": c["ends_on"], "detail": c["number"]})
    # money still owed, the same figure the dashboard and the client page show -- older
    # unpaid invoices included -- minus the contracts already flagged as awaiting payment
    names = {c["org_id"]: c["org_name"] for c in all_c}
    if money is None:
        money = _money_by_org()
    late = [o for o, (_, owed) in money.items() if owed - waiting.get(o, 0) > 0]
    if late:
        with db.session() as s:
            names.update(dict(s.execute(select(accounts.Organization.id, accounts.Organization.name)
                                        .where(accounts.Organization.id.in_(late))).all()))
    for o in late:
        rest = money[o][1] - waiting.get(o, 0)
        if rest:
            out.append({"kind": "balance", "level": "medium", "org_id": o, "org": names.get(o, ""),
                        "count": rest, "at": "", "detail": ""})
    rank = {"high": 0, "medium": 1, "low": 2}
    out.sort(key=lambda a: a["at"] or "", reverse=True)          # newest first...
    return sorted(out, key=lambda a: rank[a["level"]])            # ...within each level


@router.get("/api/crm/overview")
def overview(_: dict = Depends(require_sales)) -> dict:
    """The admin's first screen: readers, money, contracts, what needs a look."""
    import contracts
    import crm
    today = dt.date.today()
    month = today.replace(day=1)
    A = db.ClientActivity
    readers = select(db.User.email).where(db.User.role.in_(CLIENTS))

    with db.session() as s:
        # readers active today, this week, this month: one pass over the month
        d1, d7, d30 = s.execute(select(*(func.count(func.distinct(case((A.ts >= _since(n), A.actor))))
                                          for n in (1, 7, 30)))
                                .where(A.ts >= _since(30), A.actor.in_(readers))).one()
        n_readers = s.scalar(select(func.count()).select_from(db.User).where(db.User.role.in_(CLIENTS))) or 0
        new_readers = s.scalar(select(func.count()).select_from(db.User).where(
            db.User.role.in_(CLIENTS), db.User.created_at >= _since(30))) or 0
        leads_new = s.scalar(select(func.count()).select_from(crm.Lead).where(
            crm.Lead.status == "new", crm.Lead.deleted_at.is_(None))) or 0
        org_ids = list(s.scalars(select(accounts.Organization.id).where(accounts.Organization.deleted_at.is_(None))))
    received, received_year = contracts.received_since(month), contracts.received_since(today.replace(month=1, day=1))
    money = _money_by_org()
    all_c = contracts.all_contracts(status="", _={})
    al = _alerts(all_c, money)
    open_ = sum(1 for sub in billing.subscriptions_for(org_ids).values() if billing.access_of(sub) == "ok")
    return {
        "readers": n_readers, "active_today": int(d1 or 0), "active_7d": int(d7 or 0), "active_30d": int(d30 or 0),
        "clients_open": open_,
        "new_readers_30d": new_readers, "received_month": int(received), "received_year": int(received_year),
        "owed": sum(o for _, o in money.values()),
        "contracts_active": sum(1 for c in all_c if c["status"] == "active"),
        "contracts_ending": sum(1 for c in all_c if c["status"] == "active" and c["days_left"] <= 30),
        "awaiting_payment": sum(1 for c in all_c if c["status"] == "awaiting_payment"),
        "alerts_high": sum(1 for a in al if a["level"] == "high"), "alerts": len(al),
        "new_requests": leads_new,
        "usage": usage(days=30, _={}),
    }


@router.get("/api/crm/money")
def money_totals(_: dict = Depends(require_sales)) -> dict:
    """Received this month and this year, and still owed: the dashboard's figures, alone."""
    import contracts
    today = dt.date.today()
    return {"received_month": contracts.received_since(today.replace(day=1)),
            "received_year": contracts.received_since(today.replace(month=1, day=1)),
            "owed": sum(o for _, o in _money_by_org().values())}


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
