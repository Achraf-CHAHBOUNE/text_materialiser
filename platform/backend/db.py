"""Relational model for the consultation platform (website_brief).

The platform stores ONLY anonymized content: decision metadata, the anonymized body
text (for search/preview), users, links, and a full audit trail. Raw documents never
appear here. Uses DATABASE_URL (Postgres in Docker) or a local SQLite file for dev.
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import List, Optional

from sqlalchemy import (
    DateTime, ForeignKey, Integer, String, Text, create_engine, func, or_, select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

import textnorm

# Publication lifecycle (website_brief §I-6).
STATES = ("imported", "under_review", "published", "withdrawn")


def _url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if url:
        return url
    p = Path(os.getenv("DB_DIR", "data"))
    p.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(p / 'app.db').as_posix()}"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String, default="")
    role: Mapped[str] = mapped_column(String, default="client")     # admin | client
    status: Mapped[str] = mapped_column(String, default="active")   # active | suspended
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    last_login: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)


class Decision(Base):
    __tablename__ = "decisions"
    doc_id: Mapped[str] = mapped_column(String, primary_key=True)
    source_file: Mapped[str] = mapped_column(String, default="")
    fmt: Mapped[str] = mapped_column(String, default="")
    read_method: Mapped[str] = mapped_column(String, default="")
    category: Mapped[str] = mapped_column(String, default="غير محدد", index=True)
    level: Mapped[str] = mapped_column(String, default="", index=True)
    court: Mapped[str] = mapped_column(String, default="")
    decision_no: Mapped[str] = mapped_column(String, default="")
    file_no: Mapped[str] = mapped_column(String, default="")
    decision_date: Mapped[str] = mapped_column(String, default="")
    case_id: Mapped[str] = mapped_column(String, default="", index=True)
    outcome: Mapped[str] = mapped_column(String, default="")
    pii_removed: Mapped[int] = mapped_column(Integer, default=0)
    review: Mapped[str] = mapped_column(String, default="ok")          # ok | check
    state: Mapped[str] = mapped_column(String, default="imported", index=True)
    file_name: Mapped[str] = mapped_column(String, default="")         # anonymized file in the store
    body_text: Mapped[str] = mapped_column(Text, default="")           # anonymized text (safe)
    search_text: Mapped[str] = mapped_column(Text, default="")         # normalized, for search
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow,
                                                    onupdate=dt.datetime.utcnow)


class Link(Base):
    __tablename__ = "links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_doc: Mapped[str] = mapped_column(String, index=True)   # higher court
    child_doc: Mapped[str] = mapped_column(String, index=True)    # lower court
    confidence: Mapped[str] = mapped_column(String, default="")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    actor: Mapped[str] = mapped_column(String, default="")
    action: Mapped[str] = mapped_column(String, default="")       # correct | publish | withdraw | import | ...
    entity: Mapped[str] = mapped_column(String, default="")       # decision | user
    entity_id: Mapped[str] = mapped_column(String, default="")
    field: Mapped[str] = mapped_column(String, default="")
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")


class ClientActivity(Base):
    __tablename__ = "client_activity"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    actor: Mapped[str] = mapped_column(String, index=True)
    action: Mapped[str] = mapped_column(String, default="")       # view | search | download
    decision_id: Mapped[str] = mapped_column(String, default="")


_engine = create_engine(_url(), future=True)


def init_db() -> None:
    Base.metadata.create_all(_engine)
    # Scale path (website_brief §S-5): on Postgres, a pg_trgm GIN index makes the
    # normalized `LIKE '%q%'` search fast well beyond 2,000 rows. SQLite (dev) uses a
    # plain scan — fine at dev scale. Best-effort: needs the extension to be creatable.
    if _engine.dialect.name == "postgresql":
        from sqlalchemy import text as _sql
        try:
            with _engine.begin() as c:
                c.execute(_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
                c.execute(_sql(
                    "CREATE INDEX IF NOT EXISTS ix_dec_search_trgm "
                    "ON decisions USING gin (search_text gin_trgm_ops)"))
        except Exception:
            pass  # insufficient privileges: search still works, just unindexed


def session() -> Session:
    return Session(_engine)


# ---------------- users ----------------
def get_user(email: str) -> Optional[dict]:
    with session() as s:
        u = s.scalar(select(User).where(User.email == email))
        return _user_dict(u) if u else None


def _user_dict(u: User) -> dict:
    return {"id": u.id, "email": u.email, "role": u.role, "status": u.status,
            "password_hash": u.password_hash,
            "created_at": u.created_at.isoformat() if u.created_at else "",
            "last_login": u.last_login.isoformat() if u.last_login else ""}


def upsert_user(email: str, password_hash: str, role: str = "client",
                status: str = "active") -> None:
    with session() as s:
        u = s.scalar(select(User).where(User.email == email))
        if u:
            u.password_hash, u.role, u.status = password_hash, role, status
        else:
            s.add(User(email=email, password_hash=password_hash, role=role, status=status))
        s.commit()


def list_clients() -> List[dict]:
    with session() as s:
        return [_user_dict(u) for u in
                s.scalars(select(User).where(User.role == "client").order_by(User.email))]


def set_user_status(email: str, status: str) -> bool:
    with session() as s:
        u = s.scalar(select(User).where(User.email == email))
        if not u:
            return False
        u.status = status
        s.commit()
        return True


def delete_user(email: str) -> bool:
    with session() as s:
        u = s.scalar(select(User).where(User.email == email))
        if not u:
            return False
        s.delete(u)
        s.commit()
        return True


def touch_login(email: str) -> None:
    with session() as s:
        u = s.scalar(select(User).where(User.email == email))
        if u:
            u.last_login = dt.datetime.utcnow()
            s.commit()


# ---------------- decisions ----------------
def upsert_decision(data: dict, body_text: str, file_name: str) -> None:
    """Insert or UPDATE (never duplicate) a decision, keyed by doc_id (§I-8)."""
    with session() as s:
        d = s.get(Decision, data["doc_id"])
        if d is None:
            d = Decision(doc_id=data["doc_id"])
            s.add(d)
        for k in ("source_file", "fmt", "read_method", "category", "level", "court",
                  "decision_no", "file_no", "decision_date", "case_id", "outcome",
                  "pii_removed", "review"):
            if k in data:
                setattr(d, k, data[k])
        d.file_name = file_name
        d.body_text = body_text
        d.search_text = textnorm.normalize(body_text)
        # A re-import returns a decision to review rather than silently republishing.
        if d.state in ("", "withdrawn") or d.state not in STATES:
            d.state = "imported"
        elif d.state == "published":
            d.state = "under_review"
        s.commit()


def set_links(doc_id: str, links: List[dict]) -> None:
    with session() as s:
        for row in s.scalars(select(Link).where(or_(Link.parent_doc == doc_id,
                                                     Link.child_doc == doc_id))):
            s.delete(row)
        for l in links:
            if l.get("role") == "reviews":
                s.add(Link(parent_doc=doc_id, child_doc=l["to"], confidence=l.get("confidence", "")))
            else:
                s.add(Link(parent_doc=l["to"], child_doc=doc_id, confidence=l.get("confidence", "")))
        s.commit()


def links_for(doc_id: str) -> List[dict]:
    with session() as s:
        out = []
        for e in s.scalars(select(Link).where(or_(Link.parent_doc == doc_id,
                                                   Link.child_doc == doc_id))):
            other = e.child_doc if e.parent_doc == doc_id else e.parent_doc
            role = "reviews" if e.parent_doc == doc_id else "reviewed_by"
            out.append({"to": other, "role": role, "confidence": e.confidence})
        return out


def _dec_dict(d: Decision, *, body: bool = False) -> dict:
    r = {"doc_id": d.doc_id, "source_file": d.source_file, "format": d.fmt,
         "category": d.category, "level": d.level, "court": d.court,
         "decision_no": d.decision_no, "file_no": d.file_no, "date": d.decision_date,
         "case_id": d.case_id, "outcome": d.outcome, "pii_removed": d.pii_removed,
         "review": d.review, "state": d.state, "file_name": d.file_name,
         "updated_at": d.updated_at.isoformat() if d.updated_at else ""}
    if body:
        r["body_text"] = d.body_text
    return r


def get_decision(doc_id: str, *, body: bool = False) -> Optional[dict]:
    with session() as s:
        d = s.get(Decision, doc_id)
        return _dec_dict(d, body=body) if d else None


def list_decisions(*, states: Optional[tuple] = None, category: str = "",
                   level: str = "", limit: int = 100, offset: int = 0) -> List[dict]:
    with session() as s:
        q = select(Decision)
        if states:
            q = q.where(Decision.state.in_(states))
        if category:
            q = q.where(Decision.category == category)
        if level:
            q = q.where(Decision.level == level)
        q = q.order_by(Decision.updated_at.desc()).limit(limit).offset(offset)
        return [_dec_dict(d) for d in s.scalars(q)]


def search_decisions(query: str, *, states: tuple = ("published",),
                     category: str = "", level: str = "", limit: int = 50) -> List[dict]:
    nq = textnorm.normalize(query)
    with session() as s:
        q = select(Decision).where(Decision.state.in_(states))
        if category:
            q = q.where(Decision.category == category)
        if level:
            q = q.where(Decision.level == level)
        if nq:
            q = q.where(Decision.search_text.like(f"%{nq}%"))
        results = []
        for d in s.scalars(q.limit(limit)):
            row = _dec_dict(d)
            row["snippets"] = textnorm.snippets(d.body_text, query)
            results.append(row)
        return results


def update_decision_fields(doc_id: str, changes: dict, actor: str) -> Optional[dict]:
    allowed = {"category", "level", "court", "decision_no", "file_no",
               "decision_date", "outcome", "review"}
    with session() as s:
        d = s.get(Decision, doc_id)
        if not d:
            return None
        for k, v in changes.items():
            if k not in allowed:
                continue
            old = getattr(d, k)
            if str(old) != str(v):
                setattr(d, k, v)
                s.add(AuditLog(actor=actor, action="correct", entity="decision",
                               entity_id=doc_id, field=k, old_value=str(old), new_value=str(v)))
        s.commit()
        return _dec_dict(d)


def set_decision_state(doc_id: str, state: str, actor: str) -> Optional[dict]:
    if state not in STATES:
        return None
    with session() as s:
        d = s.get(Decision, doc_id)
        if not d:
            return None
        old = d.state
        d.state = state
        s.add(AuditLog(actor=actor, action=state, entity="decision", entity_id=doc_id,
                       field="state", old_value=old, new_value=state))
        s.commit()
        return _dec_dict(d)


def work_queue() -> List[dict]:
    """Decisions needing attention first (§I-7): unpublished + flagged/low-confidence."""
    with session() as s:
        q = select(Decision).where(
            Decision.state.in_(("imported", "under_review")),
        ).order_by(Decision.updated_at.desc())
        rows = []
        for d in s.scalars(q):
            reasons = []
            if d.review == "check":
                reasons.append("low-confidence link")
            if not d.category or d.category == "غير محدد":
                reasons.append("missing category")
            if not d.decision_no or not d.file_no:
                reasons.append("missing identifier")
            row = _dec_dict(d)
            row["reasons"] = reasons or ["needs review"]
            rows.append(row)
        return rows


# ---------------- audit / activity ----------------
def add_audit(actor: str, action: str, entity: str, entity_id: str,
              field: str = "", old: str = "", new: str = "") -> None:
    with session() as s:
        s.add(AuditLog(actor=actor, action=action, entity=entity, entity_id=entity_id,
                       field=field, old_value=old, new_value=new))
        s.commit()


def audit_for(entity_id: str) -> List[dict]:
    with session() as s:
        return [{"ts": a.ts.isoformat(), "actor": a.actor, "action": a.action,
                 "field": a.field, "old": a.old_value, "new": a.new_value}
                for a in s.scalars(select(AuditLog).where(AuditLog.entity_id == entity_id)
                                   .order_by(AuditLog.ts.desc()))]


def log_activity(actor: str, action: str, decision_id: str = "") -> None:
    with session() as s:
        s.add(ClientActivity(actor=actor, action=action, decision_id=decision_id))
        s.commit()


def activity_for(actor: str, limit: int = 50) -> List[dict]:
    with session() as s:
        rows = s.scalars(select(ClientActivity).where(ClientActivity.actor == actor)
                         .order_by(ClientActivity.ts.desc()).limit(limit))
        return [{"ts": a.ts.isoformat(), "action": a.action, "decision_id": a.decision_id}
                for a in rows]


def counts() -> dict:
    with session() as s:
        total = s.scalar(select(func.count()).select_from(Decision)) or 0
        published = s.scalar(select(func.count()).select_from(Decision)
                             .where(Decision.state == "published")) or 0
        pending = s.scalar(select(func.count()).select_from(Decision)
                           .where(Decision.state.in_(("imported", "under_review")))) or 0
        clients = s.scalar(select(func.count()).select_from(User)
                           .where(User.role == "client")) or 0
        return {"decisions": total, "published": published, "pending": pending,
                "clients": clients}
