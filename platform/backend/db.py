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
    DateTime, LargeBinary, UniqueConstraint, case, literal_column, ForeignKey, Integer, String, Text,
    create_engine, func, or_, select, update,
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
    decision_date: Mapped[str] = mapped_column(String, default="")   # DD/MM/YYYY
    # What a court-portal listing shows beside the number and date: the city of the
    # lower court the appeal came from (the Court of Cassation sits only in Rabat),
    # and the year, kept as its own column so a year filter needs no date parsing.
    city: Mapped[str] = mapped_column(String, default="", index=True)
    year: Mapped[str] = mapped_column(String, default="", index=True)
    # "YYYYMMDD" + the padded decision number: one comparable string, so a listing
    # sorts newest-first straight off an index. Sorting by substr() of the date and
    # length() of the number could use no index at all, so every deeper page cost
    # more than the last.
    sort_key: Mapped[str] = mapped_column(String, default="", index=True)
    case_id: Mapped[str] = mapped_column(String, default="", index=True)
    outcome: Mapped[str] = mapped_column(String, default="")
    pii_removed: Mapped[int] = mapped_column(Integer, default=0)
    review: Mapped[str] = mapped_column(String, default="ok")          # ok | check
    state: Mapped[str] = mapped_column(String, default="imported", index=True)
    file_name: Mapped[str] = mapped_column(String, default="")         # anonymized file in the store
    body_text: Mapped[str] = mapped_column(Text, default="")           # anonymized text (safe)
    search_text: Mapped[str] = mapped_column(Text, default="")         # normalized, for search
    # Hand edits. `version` is the current entry in decision_versions (0: never edited,
    # as imported). Once edited_at is set, a re-import leaves the ruling alone.
    version: Mapped[int] = mapped_column(Integer, default=0)
    edited_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    edited_by: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow,
                                                    onupdate=dt.datetime.utcnow)


class DecisionVersion(Base):
    """Every state a ruling's text has been in, and the edits waiting for approval.

    applied:   it was live at some point; the one numbered decisions.version is live now.
               Keeps the Word file too, so restoring gives back the exact bytes.
    draft:     an edit that adds text, waiting for an admin (version is NULL until then).
    discarded: a refused draft; its text is blanked -- it may hold a name.
    """
    __tablename__ = "decision_versions"
    __table_args__ = (UniqueConstraint("doc_id", "version", name="uq_decision_version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, default="applied", index=True)
    action: Mapped[str] = mapped_column(String, default="")   # import|hide|hide_all|edit|restore|title|replace_file
    summary: Mapped[str] = mapped_column(String, default="")
    actor: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    base_version: Mapped[int] = mapped_column(Integer, default=0)
    restore_of: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    body_text: Mapped[str] = mapped_column(Text, default="")
    file_data: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    decided_by: Mapped[str] = mapped_column(String, default="")
    decided_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)


class Report(Base):
    """A reader pointing at something wrong in a ruling (usually a name left visible)."""
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String, index=True)
    reporter: Mapped[str] = mapped_column(String, default="")
    quote: Mapped[str] = mapped_column(Text, default="")      # blanked once handled
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="open", index=True)   # open|resolved|dismissed
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    resolved_by: Mapped[str] = mapped_column(String, default="")
    resolved_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)


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


def _add_missing_columns() -> None:
    """Add columns that post-date an existing database, in place.

    create_all() only creates missing *tables*, so a database made before the
    listing fields existed would keep failing every query that mentions them.
    """
    from sqlalchemy import inspect, text as _sql

    have = {c["name"] for c in inspect(_engine).get_columns("decisions")}
    for name, kind in (("city", "VARCHAR DEFAULT ''"), ("year", "VARCHAR DEFAULT ''"),
                       ("sort_key", "VARCHAR DEFAULT ''"), ("version", "INTEGER DEFAULT 0"),
                       ("edited_at", "TIMESTAMP"), ("edited_by", "VARCHAR DEFAULT ''")):
        if name not in have:
            with _engine.begin() as c:
                c.execute(_sql(f"ALTER TABLE decisions ADD COLUMN {name} {kind}"))


# ---------------- full-text search ----------------
# LIKE '%word%' reads every ruling's text on every search: 1.9 s over 15,923 rulings,
# and worse as the corpus grows. SQLite's FTS5 indexes the words instead. The index is
# "external content": it stores no copy of the text and its row ids ARE the decisions'
# row ids, so a match joins back by primary key (86 ms -> 2 ms for a count). Triggers
# keep it in step with every write. Postgres has its own path (pg_trgm, see init_db).
_FTS = {"ok": False}

_FTS_SETUP = (
    # tokenize='trigram' indexes three-character sequences, so a search matches
    # *inside* a word. Arabic attaches prefixes -- و، ب، ال -- and a word-based index
    # would not find "بالتحفيظ" when someone searches "التحفيظ", which the old
    # (slow) LIKE search did find.
    "CREATE VIRTUAL TABLE decisions_fts USING fts5("
    "  search_text, content='decisions', content_rowid='rowid', tokenize='trigram')",
    "CREATE TRIGGER IF NOT EXISTS decisions_fts_ai AFTER INSERT ON decisions BEGIN"
    "  INSERT INTO decisions_fts(rowid, search_text) VALUES (new.rowid, new.search_text);"
    " END",
    "CREATE TRIGGER IF NOT EXISTS decisions_fts_ad AFTER DELETE ON decisions BEGIN"
    "  INSERT INTO decisions_fts(decisions_fts, rowid, search_text)"
    "  VALUES ('delete', old.rowid, old.search_text);"
    " END",
    "CREATE TRIGGER IF NOT EXISTS decisions_fts_au AFTER UPDATE ON decisions BEGIN"
    "  INSERT INTO decisions_fts(decisions_fts, rowid, search_text)"
    "  VALUES ('delete', old.rowid, old.search_text);"
    "  INSERT INTO decisions_fts(rowid, search_text) VALUES (new.rowid, new.search_text);"
    " END",
    "INSERT INTO decisions_fts(decisions_fts) VALUES ('rebuild')",
)


def _fts_enabled() -> bool:
    return _engine.dialect.name == "sqlite" and _FTS["ok"]


def _init_fts() -> None:
    """Create the word index (once) and keep it current through triggers."""
    if _engine.dialect.name != "sqlite":
        return
    from sqlalchemy import text as _sql
    try:
        with _engine.begin() as c:
            shape = c.execute(_sql(
                "SELECT sql FROM sqlite_master WHERE name = 'decisions_fts'")).scalar()
            if shape and ("content='decisions'" not in shape or "trigram" not in shape):
                c.execute(_sql("DROP TABLE decisions_fts"))   # earlier, slower shape
                shape = None
            if not shape:
                for statement in _FTS_SETUP:
                    c.execute(_sql(statement))
        _FTS["ok"] = True
    except Exception:
        _FTS["ok"] = False      # no FTS5 in this build: searches fall back to LIKE


def _fts_rowids(query: str):
    """A subquery of matching row ids, or None if full-text search is unavailable."""
    if not _fts_enabled():
        return None
    from sqlalchemy import text as _sql
    words = [w for w in textnorm.normalize(query).split() if w]
    # A trigram index cannot match anything shorter than three characters; those
    # fall back to LIKE, which is fine because such a query is rare.
    if not words or any(len(w) < 3 for w in words):
        return None
    # Every word must appear, each matched as a substring.
    expr = " AND ".join('"' + w.replace('"', "") + '"' for w in words)
    return _sql("SELECT rowid FROM decisions_fts WHERE decisions_fts MATCH :fts_q").bindparams(
        fts_q=expr)


def _add_browse_indexes() -> None:
    """Composite indexes matching how a listing filters and sorts."""
    from sqlalchemy import text as _sql

    for name, cols in (
        ("ix_dec_browse_chamber", "state, category, sort_key DESC"),
        ("ix_dec_browse_year", "state, category, year, sort_key DESC"),
        ("ix_dec_browse_city", "state, category, city, sort_key DESC"),
    ):
        with _engine.begin() as c:
            c.execute(_sql(f"CREATE INDEX IF NOT EXISTS {name} ON decisions ({cols})"))


def init_db() -> None:
    Base.metadata.create_all(_engine)
    _add_missing_columns()
    _add_browse_indexes()
    _init_fts()
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
def _sort_key(date: str, decision_no: str) -> str:
    """'28/12/2021' + '853' -> '20211228000853' (sorts newest and highest first)."""
    parts = (date or "").split("/")
    ymd = f"{parts[2]}{parts[1]}{parts[0]}" if len(parts) == 3 else "00000000"
    digits = "".join(ch for ch in (decision_no or "") if ch.isdigit())
    return ymd + digits.rjust(6, "0")[:6]


def upsert_decision(data: dict, body_text: str, file_name: str) -> bool:
    """Insert or UPDATE (never duplicate) a decision, keyed by doc_id (§I-8).

    Returns False, changing nothing, for a ruling someone has edited by hand: a
    re-run of the pipeline must not silently undo a hidden name. The caller must
    then leave its file alone too.
    """
    with session() as s:
        d = s.get(Decision, data["doc_id"])
        if d is not None and d.edited_at is not None:
            return False
        if d is None:
            d = Decision(doc_id=data["doc_id"])
            s.add(d)
        for k in ("source_file", "fmt", "read_method", "category", "level", "court",
                  "decision_no", "file_no", "decision_date", "city", "year", "case_id",
                  "outcome", "pii_removed", "review"):
            if k in data:
                setattr(d, k, data[k])
        d.sort_key = _sort_key(d.decision_date, d.decision_no)
        d.file_name = file_name
        d.body_text = body_text
        d.search_text = textnorm.normalize(body_text)
        # A re-import returns a decision to review rather than silently republishing.
        if d.state in ("", "withdrawn") or d.state not in STATES:
            d.state = "imported"
        elif d.state == "published":
            d.state = "under_review"
        s.commit()
        return True


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
         "city": d.city, "year": d.year,
         "case_id": d.case_id, "outcome": d.outcome, "pii_removed": d.pii_removed,
         "review": d.review, "state": d.state, "file_name": d.file_name,
         "version": d.version or 0,
         "edited_at": d.edited_at.isoformat() if d.edited_at else "",
         "edited_by": d.edited_by or "",
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


EDITABLE_FIELDS = ("category", "level", "court", "decision_no", "file_no",
                   "decision_date", "city", "year", "outcome", "review")


def update_decision_fields(doc_id: str, changes: dict, actor: str) -> Optional[dict]:
    """Correct listing fields. The result carries the (court, chamber) the ruling had
    before under "_old_title_parts", so the caller can retitle the Word file."""
    with session() as s:
        d = s.get(Decision, doc_id)
        if not d:
            return None
        before = (d.court, d.category)
        changed = False
        for k in EDITABLE_FIELDS:
            if k not in changes:
                continue
            v = str(changes[k] if changes[k] is not None else "").strip()
            old = getattr(d, k)
            if str(old) != v:
                setattr(d, k, v)
                changed = True
                s.add(AuditLog(actor=actor, action="correct", entity="decision",
                               entity_id=doc_id, field=k, old_value=str(old), new_value=v))
                if k == "decision_date" and "year" not in changes and len(v) == 10:
                    d.year = v[-4:]
        if changed:
            d.sort_key = _sort_key(d.decision_date, d.decision_no)
            d.edited_at, d.edited_by = dt.datetime.utcnow(), actor
        s.commit()
        out = _dec_dict(d)
        out["_old_title_parts"] = before
        return out


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


# ---------------- browse (court > chamber > year > rulings) ----------------
def browse_tree(states: tuple = ("published",)) -> List[dict]:
    """Courts, each with its chambers and how many rulings each holds."""
    with session() as s:
        rows = s.execute(
            select(Decision.court, Decision.level, Decision.category,
                   func.count(Decision.doc_id))
            .where(Decision.state.in_(states))
            .group_by(Decision.court, Decision.level, Decision.category)
        ).all()
    courts: dict = {}
    for court, level, chamber, n in rows:
        name = court or {"نقض": "محكمة النقض", "استئناف": "محكمة الاستئناف",
                         "ابتدائي": "المحكمة الابتدائية"}.get(level, "محكمة النقض")
        entry = courts.setdefault(name, {"court": name, "total": 0, "chambers": {}})
        entry["total"] += n
        entry["chambers"][chamber] = entry["chambers"].get(chamber, 0) + n
    out = []
    for c in courts.values():
        chambers = [{"chamber": k, "count": v} for k, v in c["chambers"].items()]
        chambers.sort(key=lambda x: -x["count"])
        out.append({"court": c["court"], "total": c["total"], "chambers": chambers})
    out.sort(key=lambda x: -x["total"])
    return out


def browse_years(chamber: str = "", states: tuple = ("published",)) -> List[dict]:
    """Years present for a chamber (or for everything), newest first."""
    with session() as s:
        q = (select(Decision.year, func.count(Decision.doc_id))
             .where(Decision.state.in_(states), Decision.year != "")
             .group_by(Decision.year))
        if chamber:
            q = q.where(Decision.category == chamber)
        rows = s.execute(q).all()
    return [{"year": y, "count": n} for y, n in sorted(rows, key=lambda r: r[0], reverse=True)]


def browse_rulings(*, chamber: str = "", year: str = "", city: str = "", q: str = "",
                   states: tuple = ("published",), limit: int = 50,
                   offset: int = 0) -> dict:
    """One page of listing rows, plus the total, ordered as a portal lists them."""
    with session() as s:
        where = [Decision.state.in_(states)]
        if chamber:
            where.append(Decision.category == chamber)
        if year:
            where.append(Decision.year == year)
        if city:
            where.append(Decision.city == city)
        exact_first = None
        if q.strip():
            nq = textnorm.normalize(q)
            matches = _fts_rowids(q)
            text_match = (Decision.search_text.like(f"%{nq}%") if matches is None
                          else literal_column("decisions.rowid").in_(matches))
            if q.strip().isdigit():
                # A number could be a decision number or appear in the text: allow both.
                where.append(or_(text_match, Decision.decision_no.like(f"%{q.strip()}%")))
            else:
                # Words only. OR-ing a LIKE on the number here would force a scan of
                # every ruling and undo the word index (190 ms -> a few).
                where.append(text_match)
            if q.strip().isdigit():
                # Someone typing a bare number wants that decision, not every ruling
                # whose text happens to contain those digits.
                exact_first = case((Decision.decision_no == q.strip(), 0), else_=1)
        total = s.execute(select(func.count(Decision.doc_id)).where(*where)).scalar_one()
        # Newest first, straight off the sort key.
        order = [] if exact_first is None else [exact_first]
        # Only the eight columns a row shows. Selecting whole objects dragged every
        # ruling's full text (kilobytes each) out of the database to print a table.
        rows = s.execute(
            select(Decision.doc_id, Decision.decision_no, Decision.decision_date,
                   Decision.city, Decision.category, Decision.court, Decision.year,
                   Decision.case_id)
            .where(*where)
            .order_by(*order, Decision.sort_key.desc())
            .limit(limit).offset(offset)
        ).all()
        items = [{"doc_id": r[0], "decision_no": r[1], "date": r[2], "city": r[3],
                  "chamber": r[4], "court": r[5] or "محكمة النقض", "year": r[6],
                  "case_id": r[7]} for r in rows]
    return {"total": total, "items": items}


def browse_cities(chamber: str = "", states: tuple = ("published",)) -> List[dict]:
    with session() as s:
        q = (select(Decision.city, func.count(Decision.doc_id))
             .where(Decision.state.in_(states), Decision.city != "")
             .group_by(Decision.city))
        if chamber:
            q = q.where(Decision.category == chamber)
        rows = s.execute(q).all()
    return [{"city": c, "count": n} for c, n in sorted(rows, key=lambda r: -r[1])]


# ---------------- hand edits: versions, drafts, reports ----------------
class Conflict(Exception):
    """The ruling changed since the edit was prepared."""


def editing_state(doc_id: str) -> Optional[dict]:
    with session() as s:
        d = s.get(Decision, doc_id)
        if not d:
            return None
        return {"doc_id": d.doc_id, "version": d.version or 0, "body_text": d.body_text,
                "file_name": d.file_name, "court": d.court, "category": d.category}


def apply_version(doc_id: str, *, base_version: int, current_file: bytes, new_file: bytes,
                  new_text: str, actor: str, action: str, summary: str,
                  restore_of: Optional[int] = None, draft_id: Optional[int] = None) -> int:
    """Make new_text/new_file the live ruling, in one transaction. Returns the new version.

    The first edit also records the ruling as imported (version 1), so it can always be
    restored. The decision row is only updated while it is still at base_version, and a
    version number can be taken once: of two admins saving at the same moment, the
    second gets Conflict instead of silently replacing the first.
    """
    from sqlalchemy.exc import IntegrityError

    now = dt.datetime.utcnow()
    with session() as s:
        d = s.get(Decision, doc_id)
        if d is None:
            raise LookupError(doc_id)
        if (d.version or 0) != base_version:
            raise Conflict(doc_id)
        if base_version == 0:
            s.add(DecisionVersion(doc_id=doc_id, version=1, status="applied", action="import",
                                  summary="as imported", actor="pipeline", base_version=0,
                                  body_text=d.body_text, file_data=current_file,
                                  created_at=d.created_at or now))
        new_version = max(base_version, 1) + 1
        if draft_id is not None:
            v = s.get(DecisionVersion, draft_id)
            if v is None or v.doc_id != doc_id or v.status != "draft":
                raise LookupError(draft_id)
            v.version, v.status, v.decided_by, v.decided_at = new_version, "applied", actor, now
            v.body_text, v.file_data = new_text, new_file
        else:
            s.add(DecisionVersion(doc_id=doc_id, version=new_version, status="applied",
                                  action=action, summary=summary, actor=actor,
                                  base_version=base_version, restore_of=restore_of,
                                  body_text=new_text, file_data=new_file, decided_by=actor,
                                  decided_at=now))
        done = s.execute(
            update(Decision)
            .where(Decision.doc_id == doc_id, Decision.version == d.version)
            .values(version=new_version, body_text=new_text,
                    search_text=textnorm.normalize(new_text),
                    edited_at=now, edited_by=actor, updated_at=now)
            .execution_options(synchronize_session=False))
        if done.rowcount != 1:
            s.rollback()
            raise Conflict(doc_id)
        s.add(AuditLog(actor=actor, action=action, entity="decision", entity_id=doc_id,
                       field="text", old_value=f"v{max(base_version, 1)}",
                       new_value=f"v{new_version}: {summary}"))
        try:
            s.commit()
        except IntegrityError:
            s.rollback()
            raise Conflict(doc_id)
        return new_version


def add_draft(doc_id: str, *, base_version: int, text: str, actor: str, action: str,
              summary: str, restore_of: Optional[int] = None) -> int:
    with session() as s:
        v = DecisionVersion(doc_id=doc_id, version=None, status="draft", action=action,
                            summary=summary, actor=actor, base_version=base_version,
                            restore_of=restore_of, body_text=text)
        s.add(v)
        s.add(AuditLog(actor=actor, action="draft", entity="decision", entity_id=doc_id,
                       field="text", old_value=f"v{base_version}", new_value=summary))
        s.commit()
        return v.id


def _version_dict(v: DecisionVersion, *, full: bool = False) -> dict:
    r = {"id": v.id, "doc_id": v.doc_id, "version": v.version, "status": v.status,
         "action": v.action, "summary": v.summary, "actor": v.actor,
         "created_at": v.created_at.isoformat() if v.created_at else "",
         "base_version": v.base_version, "restore_of": v.restore_of,
         "decided_by": v.decided_by,
         "decided_at": v.decided_at.isoformat() if v.decided_at else ""}
    if full:
        r["body_text"], r["file_data"] = v.body_text, v.file_data
    return r


def get_version_row(row_id: int) -> Optional[dict]:
    with session() as s:
        v = s.get(DecisionVersion, row_id)
        return _version_dict(v, full=True) if v else None


def version_by_number(doc_id: str, version: int) -> Optional[dict]:
    with session() as s:
        v = s.scalar(select(DecisionVersion).where(DecisionVersion.doc_id == doc_id,
                                                   DecisionVersion.version == version,
                                                   DecisionVersion.status == "applied"))
        return _version_dict(v, full=True) if v else None


def history(doc_id: str) -> dict:
    """Versions newest first, and the drafts still waiting -- no text, no files."""
    with session() as s:
        rows = list(s.scalars(select(DecisionVersion)
                              .where(DecisionVersion.doc_id == doc_id,
                                     DecisionVersion.status.in_(("applied", "draft")))
                              .order_by(DecisionVersion.id.desc())))
        versions = sorted((v for v in rows if v.status == "applied"),
                          key=lambda v: v.version or 0, reverse=True)
        return {"versions": [_version_dict(v) for v in versions],
                "drafts": [_version_dict(v) for v in rows if v.status == "draft"]}


def discard_draft(row_id: int, actor: str) -> bool:
    with session() as s:
        v = s.get(DecisionVersion, row_id)
        if v is None or v.status != "draft":
            return False
        v.status, v.decided_by, v.decided_at = "discarded", actor, dt.datetime.utcnow()
        v.body_text = ""                     # a refused edit may carry a name: keep nothing
        s.add(AuditLog(actor=actor, action="discard", entity="decision", entity_id=v.doc_id,
                       field="text", new_value=v.summary))
        s.commit()
        return True


def purge_history(doc_id: str, actor: str) -> int:
    """Delete every earlier version of a ruling, keeping the live one.

    Undo needs the old text, and the old text still holds whatever was hidden since.
    Once an admin is sure of a hide, this removes the last copy of the name.
    """
    with session() as s:
        d = s.get(Decision, doc_id)
        if d is None:
            return 0
        old = list(s.scalars(select(DecisionVersion).where(
            DecisionVersion.doc_id == doc_id,
            or_(DecisionVersion.status == "discarded",
                (DecisionVersion.status == "applied")
                & (DecisionVersion.version < (d.version or 0))))))
        for v in old:
            s.delete(v)
        s.add(AuditLog(actor=actor, action="purge_history", entity="decision", entity_id=doc_id,
                       field="text", new_value=f"{len(old)} earlier version(s) deleted"))
        s.commit()
        return len(old)


def pending_drafts(limit: int = 200) -> List[dict]:
    with session() as s:
        rows = s.execute(select(DecisionVersion, Decision.decision_no, Decision.category)
                         .join(Decision, Decision.doc_id == DecisionVersion.doc_id)
                         .where(DecisionVersion.status == "draft")
                         .order_by(DecisionVersion.created_at).limit(limit))
        return [dict(_version_dict(v), decision_no=no, category=cat) for v, no, cat in rows]


MAX_OPEN_REPORTS_PER_READER = 50


def add_report(doc_id: str, reporter: str, quote: str, note: str) -> Optional[int]:
    with session() as s:
        open_mine = s.scalar(select(func.count()).select_from(Report).where(
            Report.reporter == reporter, Report.status == "open")) or 0
        if open_mine >= MAX_OPEN_REPORTS_PER_READER:
            return None
        r = Report(doc_id=doc_id, reporter=reporter, quote=quote[:500], note=note[:1000])
        s.add(r)
        s.commit()
        return r.id


def list_reports(status: str = "open", doc_id: str = "", limit: int = 200) -> List[dict]:
    with session() as s:
        q = (select(Report, Decision.decision_no, Decision.category)
             .join(Decision, Decision.doc_id == Report.doc_id))
        if status:
            q = q.where(Report.status == status)
        if doc_id:
            q = q.where(Report.doc_id == doc_id)
        q = q.order_by(Report.created_at.desc()).limit(limit)
        return [{"id": r.id, "doc_id": r.doc_id, "decision_no": no, "category": cat,
                 "reporter": r.reporter, "quote": r.quote, "note": r.note, "status": r.status,
                 "created_at": r.created_at.isoformat() if r.created_at else "",
                 "resolved_by": r.resolved_by,
                 "resolved_at": r.resolved_at.isoformat() if r.resolved_at else ""}
                for r, no, cat in s.execute(q)]


def resolve_report(report_id: int, status: str, actor: str) -> bool:
    if status not in ("resolved", "dismissed"):
        return False
    with session() as s:
        r = s.get(Report, report_id)
        if r is None:
            return False
        r.status, r.resolved_by, r.resolved_at = status, actor, dt.datetime.utcnow()
        r.quote = ""                          # the quoted text is usually the name itself
        s.add(AuditLog(actor=actor, action=f"report_{status}", entity="decision",
                       entity_id=r.doc_id, field="report", new_value=str(report_id)))
        s.commit()
        return True


def edited_decisions() -> List[dict]:
    with session() as s:
        return [_dec_dict(d) for d in s.scalars(
            select(Decision).where(Decision.edited_at.is_not(None)).order_by(Decision.doc_id))]


def attach_draft_file(row_id: int, data: bytes) -> None:
    """A draft that is a whole uploaded file keeps the file, to apply it as given."""
    with session() as s:
        v = s.get(DecisionVersion, row_id)
        if v is not None and v.status == "draft":
            v.file_data = data
            s.commit()
