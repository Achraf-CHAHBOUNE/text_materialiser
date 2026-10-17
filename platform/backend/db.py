"""Relational model for the consultation platform (website_brief).

The platform stores ONLY anonymized content: decision metadata, the anonymized body
text (for search/preview), users, links, and a full audit trail. Raw documents never
appear here. Uses DATABASE_URL (Postgres in Docker) or a local SQLite file for dev.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from contextlib import contextmanager
from typing import Iterator, List, Optional

from sqlalchemy import (
    DateTime, LargeBinary, UniqueConstraint, case, literal_column, Integer, String, Text,
    create_engine, func, or_, select, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

import clock
import settings  # reads platform/.env before anything connects
import textnorm

# The chambers a ruling is filed under, in the order the site lists them.
CATEGORIES = ["إدارية", "تجارية", "مدنية", "جنائية", "اجتماعية", "أحوال شخصية", "عقارية"]

# Publication lifecycle (website_brief §I-6).
STATES = ("imported", "under_review", "published", "withdrawn")


def _url() -> str:
    url = settings.S.database_url
    if url:
        return url
    p = Path(settings.S.db_dir)
    p.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(p / 'app.db').as_posix()}"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String, default="")
    # admin | editor | sales (staff) -- client_admin | client (a customer's people)
    role: Mapped[str] = mapped_column(String, default="client")
    status: Mapped[str] = mapped_column(String, default="active")   # active | suspended
    full_name: Mapped[str] = mapped_column(String, default="")
    phone: Mapped[str] = mapped_column(String, default="")
    language: Mapped[str] = mapped_column(String, default="ar")     # ar | fr
    org_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    mfa_secret: Mapped[str] = mapped_column(String, default="")     # empty: no second factor
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=clock.utcnow)
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
    # What the court itself prints above the ruling: the subject it files the case
    # under, the sub-issues that narrow it, and the legal rule. The Cassation portal
    # shows all of this in one column headed "المفاتيح أو القاعدة أو المحتوى" and
    # searches it as free text; it publishes no list of subjects to classify against,
    # so these are the court's own words rather than ours. About half the corpus
    # prints no headnote at all, and those rulings keep these fields empty.
    theme: Mapped[str] = mapped_column(String, default="", index=True)
    theme_key: Mapped[str] = mapped_column(String, default="", index=True)
    keywords: Mapped[str] = mapped_column(String, default="")   # the whole dash chain
    rule: Mapped[str] = mapped_column(Text, default="")         # القاعدة: the abstract
    # Where the subject came from, and a summary written for the rulings that print
    # no rule of their own. `rule` above is only ever the court's words; a machine
    # summary lives here instead, so the two can never be confused on the page or in
    # an export. An empty theme_source means the ruling has no subject at all.
    theme_source: Mapped[str] = mapped_column(String, default="", index=True)  # court|model
    abstract: Mapped[str] = mapped_column(Text, default="")     # written for us, not by the court
    # when the model was asked for a subject and summary (enrich.py); set once, so a
    # ruling is never paid for twice
    enriched_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True, index=True)
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
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=clock.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=clock.utcnow,
                                                    onupdate=clock.utcnow)


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
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=clock.utcnow)
    base_version: Mapped[int] = mapped_column(Integer, default=0)
    restore_of: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    body_text: Mapped[str] = mapped_column(Text, default="")
    file_data: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    decided_by: Mapped[str] = mapped_column(String, default="")
    decided_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)


class Translation(Base):
    """A ruling in another language, kept so it is produced only once.

    The Arabic is what the court wrote and what counts; this is a machine
    translation, held here to spare the next reader the wait and the cost.
    """
    __tablename__ = "translations"
    __table_args__ = (UniqueConstraint("doc_id", "lang", name="uq_translation"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String, index=True)
    lang: Mapped[str] = mapped_column(String, default="fr")
    text: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String, default="")
    source_version: Mapped[int] = mapped_column(Integer, default=0)   # ruling version translated
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=clock.utcnow)


class DecisionI18n(Base):
    """A ruling's text and headnote in another language, one row per language.

    Replaces `translations`, which held only the body. The Arabic in `decisions`
    stays the official text; everything here is a machine translation and says so on
    screen. `abstract_of` records what the abstract translates -- the court's rule
    ("rule") or the summary written for us ("abstract") -- so the page can label it.
    A row whose source_version differs from the ruling's version is out of date.
    """
    __tablename__ = "decision_i18n"
    __table_args__ = (UniqueConstraint("doc_id", "lang", name="uq_decision_i18n"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String, index=True)
    lang: Mapped[str] = mapped_column(String, default="fr")
    abstract: Mapped[str] = mapped_column(Text, default="")
    abstract_of: Mapped[str] = mapped_column(String, default="")      # rule | abstract
    keywords: Mapped[str] = mapped_column(String, default="")
    body_text: Mapped[str] = mapped_column(Text, default="")
    search_text: Mapped[str] = mapped_column(Text, default="")        # folded, for search
    model: Mapped[str] = mapped_column(String, default="")
    source_version: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=clock.utcnow)


class Subject(Base):
    """A subject (الموضوع) rulings are filed under, named in each language.

    Keyed by the same normalised key as decisions.theme_key, so one subject spelled
    two ways by the court is still one row. label_ar is the court's commonest spelling.
    """
    __tablename__ = "subjects"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    label_ar: Mapped[str] = mapped_column(String, default="")
    label_fr: Mapped[str] = mapped_column(String, default="")
    model: Mapped[str] = mapped_column(String, default="")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=clock.utcnow)


class Report(Base):
    """A reader pointing at something wrong in a ruling (usually a name left visible)."""
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String, index=True)
    reporter: Mapped[str] = mapped_column(String, default="")
    quote: Mapped[str] = mapped_column(Text, default="")      # blanked once handled
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="open", index=True)   # open|resolved|dismissed
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=clock.utcnow)
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
    ts: Mapped[dt.datetime] = mapped_column(DateTime, default=clock.utcnow)
    actor: Mapped[str] = mapped_column(String, default="")
    action: Mapped[str] = mapped_column(String, default="")       # correct | publish | withdraw | import | ...
    entity: Mapped[str] = mapped_column(String, default="")       # decision | user
    entity_id: Mapped[str] = mapped_column(String, default="")
    field: Mapped[str] = mapped_column(String, default="")
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")


class WorkerState(Base):
    """What the worker remembers between passes, e.g. the day it last ran the daily jobs.
    Here rather than in worker.py: that file runs as a program, and a table declared in
    it would be declared twice once anything imports it as a module."""
    __tablename__ = "worker_state"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, default="")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=clock.utcnow)


class ClientActivity(Base):
    __tablename__ = "client_activity"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime, default=clock.utcnow)
    actor: Mapped[str] = mapped_column(String, index=True)
    action: Mapped[str] = mapped_column(String, default="")       # view | search | download
    decision_id: Mapped[str] = mapped_column(String, default="")


# SQLite (development) locks the whole file while a script writes; a reader waits up
# to 30 s for it rather than failing after the default 5 -- a sign-in during a long
# import used to error out. Postgres has no such lock.
def _make_engine():
    url = _url()
    return create_engine(url, future=True, pool_pre_ping=True,
                         connect_args={"timeout": 30} if url.startswith("sqlite") else {})


_engine = _make_engine()


def configure() -> None:
    """Connect again with the current settings (settings.reload() first): for tests,
    which each run against a database of their own."""
    global _engine
    _engine.dispose()
    _engine = _make_engine()
    _FTS["ok"] = False


def add_columns(table: str, columns: List[tuple]) -> None:
    """Add (name, SQL type) columns a table made before them lacks. For modules whose
    tables already exist in a serving database: create_all() never alters a table."""
    from sqlalchemy import inspect, text as _sql
    if table not in inspect(_engine).get_table_names():
        return
    have = {c["name"] for c in inspect(_engine).get_columns(table)}
    for name, kind in columns:
        if name not in have:
            with _engine.begin() as c:
                c.execute(_sql(f"ALTER TABLE {table} ADD COLUMN {name} {kind}"))


def _add_missing_columns() -> None:
    """Add columns that post-date an existing database, in place.

    create_all() only creates missing *tables*, so a database made before the
    listing fields existed would keep failing every query that mentions them.
    """
    from sqlalchemy import inspect, text as _sql

    have = {c["name"] for c in inspect(_engine).get_columns("decisions")}
    for name, kind in (("city", "VARCHAR DEFAULT ''"), ("year", "VARCHAR DEFAULT ''"),
                       ("sort_key", "VARCHAR DEFAULT ''"), ("version", "INTEGER DEFAULT 0"),
                       ("edited_at", "TIMESTAMP"), ("edited_by", "VARCHAR DEFAULT ''"),
                       ("theme", "VARCHAR DEFAULT ''"), ("theme_key", "VARCHAR DEFAULT ''"),
                       ("keywords", "VARCHAR DEFAULT ''"), ("rule", "TEXT DEFAULT ''"),
                       ("theme_source", "VARCHAR DEFAULT ''"),
                       ("abstract", "TEXT DEFAULT ''")):
        if name not in have:
            with _engine.begin() as c:
                c.execute(_sql(f"ALTER TABLE decisions ADD COLUMN {name} {kind}"))
    have = {c["name"] for c in inspect(_engine).get_columns("users")}
    for name, kind in (("full_name", "VARCHAR DEFAULT ''"), ("phone", "VARCHAR DEFAULT ''"),
                       ("language", "VARCHAR DEFAULT 'ar'"), ("org_id", "INTEGER"),
                       ("mfa_secret", "VARCHAR DEFAULT ''")):
        if name not in have:
            with _engine.begin() as c:
                c.execute(_sql(f"ALTER TABLE users ADD COLUMN {name} {kind}"))


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
    # only when the text changes: publishing or giving a subject re-indexes nothing
    "CREATE TRIGGER IF NOT EXISTS decisions_fts_au AFTER UPDATE OF search_text ON decisions BEGIN"
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


_FTS_FR_SETUP = (
    "CREATE VIRTUAL TABLE decision_i18n_fts USING fts5("
    "  search_text, content='decision_i18n', content_rowid='id', tokenize='trigram')",
    "CREATE TRIGGER IF NOT EXISTS decision_i18n_fts_ai AFTER INSERT ON decision_i18n BEGIN"
    "  INSERT INTO decision_i18n_fts(rowid, search_text) VALUES (new.id, new.search_text);"
    " END",
    "CREATE TRIGGER IF NOT EXISTS decision_i18n_fts_ad AFTER DELETE ON decision_i18n BEGIN"
    "  INSERT INTO decision_i18n_fts(decision_i18n_fts, rowid, search_text)"
    "  VALUES ('delete', old.id, old.search_text);"
    " END",
    "CREATE TRIGGER IF NOT EXISTS decision_i18n_fts_au AFTER UPDATE OF search_text ON decision_i18n BEGIN"
    "  INSERT INTO decision_i18n_fts(decision_i18n_fts, rowid, search_text)"
    "  VALUES ('delete', old.id, old.search_text);"
    "  INSERT INTO decision_i18n_fts(rowid, search_text) VALUES (new.id, new.search_text);"
    " END",
    "INSERT INTO decision_i18n_fts(decision_i18n_fts) VALUES ('rebuild')",
)


_FTS_FR = {"ok": False}


def _init_i18n_search() -> None:
    """The French word index: FTS5 on SQLite, a stored French tsvector on Postgres."""
    from sqlalchemy import text as _sql
    try:
        with _engine.begin() as c:
            if _engine.dialect.name == "sqlite":
                if not c.execute(_sql("SELECT 1 FROM sqlite_master "
                                      "WHERE name = 'decision_i18n_fts'")).scalar():
                    for statement in _FTS_FR_SETUP:
                        c.execute(_sql(statement))
                _FTS_FR["ok"] = True
            elif _engine.dialect.name == "postgresql":
                # French stemming, so "contrats" finds "contrat". Instant on an empty
                # table; on a full one it rewrites the table, like search_tsv does.
                c.execute(_sql(
                    "ALTER TABLE decision_i18n ADD COLUMN IF NOT EXISTS search_tsv tsvector "
                    "GENERATED ALWAYS AS (to_tsvector('french', search_text)) STORED"))
                c.execute(_sql("CREATE INDEX IF NOT EXISTS ix_i18n_tsv "
                               "ON decision_i18n USING gin (search_tsv)"))
    except Exception:
        pass        # searches in French fall back to LIKE


def _i18n_match(q: str, lang: str):
    """Doc ids whose text in `lang` contains `q`, as a subquery."""
    from sqlalchemy import text as _sql
    fq = textnorm.fold_latin(q)
    words = [w for w in fq.split() if w]
    base = select(DecisionI18n.doc_id).where(DecisionI18n.lang == lang)
    if not words:
        return base
    if _engine.dialect.name == "postgresql":
        return base.where(_sql("search_tsv @@ plainto_tsquery('french', :fq)").bindparams(fq=fq))
    # "de", "la", "du" are in every ruling and too short for the trigram index; kept
    # in, they forced a scan of every text (12 s for "contrat de bail" instead of <1).
    long_words = [w for w in words if len(w) >= 3]
    if long_words:
        words = long_words
    if _FTS_FR["ok"] and all(len(w) >= 3 for w in words):
        expr = " AND ".join('"' + w.replace('"', "") + '"' for w in words)
        ids = _sql("SELECT rowid FROM decision_i18n_fts WHERE decision_i18n_fts "
                   "MATCH :fr_q").bindparams(fr_q=expr)
        return base.where(DecisionI18n.id.in_(ids))
    for w in words:
        base = base.where(DecisionI18n.search_text.like(f"%{w}%"))
    return base


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
        ("ix_dec_browse_theme", "state, theme_key, sort_key DESC"),
        # the facet list groups by key and label: with both in the index, in that
        # order, it reads the counts straight off it instead of sorting 14,000 rows
        ("ix_dec_theme_facet", "state, theme_key, theme"),
    ):
        with _engine.begin() as c:
            c.execute(_sql(f"CREATE INDEX IF NOT EXISTS {name} ON decisions ({cols})"))


def _alembic(action: str, target: str) -> None:
    from alembic import command
    from alembic.config import Config
    here = Path(__file__).resolve().parent
    cfg = Config(str(here / "alembic.ini"))
    cfg.set_main_option("script_location", str(here / "migrations"))
    with _engine.begin() as conn:
        cfg.attributes["connection"] = conn
        getattr(command, action)(cfg, target)


def _baseline_tables() -> List[str]:
    import re
    here = Path(__file__).resolve().parent / "migrations" / "versions" / "0001_baseline.py"
    return re.findall(r"op\.create_table\('(\w+)'", here.read_text(encoding="utf-8"))


def migrate() -> None:
    """Bring the database's structure up to date (migrations/versions, by Alembic).

    A database made before migrations existed is first brought to the baseline the way
    it always was -- missing tables made, missing columns added -- and marked 0001, so
    only the migrations written after it run there."""
    from sqlalchemy import inspect
    tables = set(inspect(_engine).get_table_names())
    if "alembic_version" not in tables and "decisions" in tables:
        base = set(_baseline_tables())
        Base.metadata.create_all(_engine, tables=[t for t in Base.metadata.sorted_tables if t.name in base])
        _add_missing_columns()
        add_columns("subscriptions", [("monthly_price", "INTEGER")])
        _alembic("stamp", "0001")
    _alembic("upgrade", "head")


def init_db() -> None:
    """The structure up to date, then the search indexes in place. Several API and
    worker copies may start together: one migrates while the others wait their turn."""
    with exclusive("schema", wait=True):
        migrate()
    _add_browse_indexes()
    _init_fts()
    _init_i18n_search()
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
                # A word index beside the trigram one. The trigram index finds
                # candidates in milliseconds, but LIKE is lossy, so Postgres then has
                # to fetch and decompress every candidate ruling to recheck it: 11,544
                # of them, 3.4 seconds. Matching whole words needs no recheck.
                #
                # The tsvector is a stored column rather than an index expression.
                # Indexed as an expression it was still recomputed whenever the planner
                # chose to walk the sort order and filter -- a tsvector over a 15 KB
                # ruling, 472 times, 1.5 seconds. Stored, there is nothing to recompute.
                # On an empty database this is instant; on a full one it rewrites the
                # table, so it is done once, deliberately, not at startup.
                c.execute(_sql(
                    "ALTER TABLE decisions ADD COLUMN IF NOT EXISTS search_tsv tsvector "
                    "GENERATED ALWAYS AS (to_tsvector('simple', search_text)) STORED"))
                c.execute(_sql(
                    "CREATE INDEX IF NOT EXISTS ix_dec_tsv_col "
                    "ON decisions USING gin (search_tsv)"))
        except Exception:
            pass  # insufficient privileges: search still works, just unindexed


def session() -> Session:
    return Session(_engine)


@contextmanager
def exclusive(name: str, wait: bool = False) -> Iterator[bool]:
    """One holder at a time for `name`, across every process and container that shares
    this database. Yields True when held. With wait=False a busy lock yields False at
    once (another worker is doing the job); with wait=True it waits its turn.

    Postgres: an advisory lock held for the block on its own connection. SQLite runs
    one process in development, so there it is always granted."""
    if _engine.dialect.name != "postgresql":
        yield True
        return
    with _engine.connect() as c:
        key = c.execute(text("SELECT hashtext(:n)"), {"n": name}).scalar()
        if wait:
            c.execute(text("SELECT pg_advisory_lock(:k)"), {"k": key})
            got = True
        else:
            got = bool(c.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar())
        try:
            yield got
        finally:
            if got:
                c.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
            c.commit()


# ---------------- users ----------------
def get_user(email: str) -> Optional[dict]:
    with session() as s:
        u = s.scalar(select(User).where(User.email == email))
        return _user_dict(u) if u else None


def _user_dict(u: User) -> dict:
    return {"id": u.id, "email": u.email, "role": u.role, "status": u.status,
            "password_hash": u.password_hash,
            "full_name": u.full_name or "", "phone": u.phone or "",
            "language": u.language or "ar", "org_id": u.org_id,
            "mfa": bool(u.mfa_secret), "mfa_secret": u.mfa_secret or "",
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


def set_user_status(email: str, status: str) -> bool:
    with session() as s:
        u = s.scalar(select(User).where(User.email == email))
        if not u:
            return False
        u.status = status
        s.commit()
        return True


def touch_login(email: str) -> None:
    with session() as s:
        u = s.scalar(select(User).where(User.email == email))
        if u:
            u.last_login = clock.utcnow()
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
                  "outcome", "pii_removed", "review",
                  "theme", "theme_key", "keywords", "rule",
                  "theme_source", "abstract"):
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
         "theme": d.theme or "", "theme_key": d.theme_key or "",
         "keywords": d.keywords or "", "rule": d.rule or "",
         "theme_source": d.theme_source or "", "abstract": d.abstract or "",
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
                     category: str = "", level: str = "", limit: int = 50, offset: int = 0) -> List[dict]:
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
        # a fixed order, newest first, so page 2 continues page 1 without repeats or gaps
        q = q.order_by(Decision.sort_key.desc(), Decision.doc_id).offset(offset).limit(limit)
        for d in s.scalars(q):
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
            d.edited_at, d.edited_by = clock.utcnow(), actor
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


def _text_match(q: str, nq: str):
    """The condition that finds `q` in a ruling's text, by whatever the database has.

    On Postgres this is a word match over the tsvector index. The trigram index it
    replaces was not the problem - it answered in 8 ms - but LIKE is lossy, so every
    candidate had to be fetched and decompressed to be rechecked, which cost 3.4
    seconds on a common word. Matching words needs no recheck: 101 ms, and 99.3% of
    the same rulings. The few it misses are words glued to another, so a query that
    finds nothing is tried again the old way rather than answered with an empty page.

    SQLite (development) keeps its FTS5 trigram index, which is fast at that scale.
    """
    if _engine.dialect.name == "postgresql":
        tsq = textnorm.tsquery(q)
        if tsq:
            return text("search_tsv @@ to_tsquery('simple', :tsq)").bindparams(tsq=tsq)
    matches = _fts_rowids(q)
    if matches is not None:
        return literal_column("decisions.rowid").in_(matches)
    return Decision.search_text.like(f"%{nq}%")


RULE_EXCERPT = 400


def _excerpt(rule: str) -> str:
    """The opening of the rule, cut on a word so it does not end mid-letter."""
    if len(rule) <= RULE_EXCERPT:
        return rule
    cut = rule[:RULE_EXCERPT]
    space = cut.rfind(" ")
    return (cut[:space] if space > RULE_EXCERPT * 0.6 else cut).rstrip() + "…"


def browse_themes(chamber: str = "", *, states: tuple = ("published",),
                  limit: int = 300, lang: str = "ar") -> List[dict]:
    """The subjects rulings are filed under, commonest first.

    Grouped by the normalised key, labelled with the spelling the court used most
    often for it, so "الكراء" and "كراء" are offered once rather than twice.
    """
    with session() as s:
        where = [Decision.state.in_(states), Decision.theme_key != ""]
        if chamber:
            where.append(Decision.category == chamber)
        rows = s.execute(
            select(Decision.theme_key, Decision.theme, func.count(Decision.doc_id))
            .where(*where).group_by(Decision.theme_key, Decision.theme)
        ).all()
    best: dict = {}
    for key, label, n in rows:
        slot = best.setdefault(key, {"key": key, "label": label, "count": 0, "_top": 0})
        slot["count"] += n
        if n > slot["_top"]:
            slot["_top"], slot["label"] = n, label
    out = sorted(best.values(), key=lambda t: -t["count"])[:limit]
    labels = subject_labels([t["key"] for t in out], lang)
    for t in out:
        t.pop("_top", None)
        if lang != "ar":
            # the Arabic stays alongside: a subject the model has not named yet is
            # shown in Arabic rather than dropped from the menu
            t["label_ar"] = t["label"]
            t["label"] = labels.get(t["key"], t["label"])
    return out


def browse_rulings(*, chamber: str = "", year: str = "", city: str = "", q: str = "",
                   theme: str = "", states: tuple = ("published",), limit: int = 50,
                   offset: int = 0, lang: str = "ar") -> dict:
    """One page of listing rows, plus the total, ordered as a portal lists them."""
    with session() as s:
        where = [Decision.state.in_(states)]
        if chamber:
            where.append(Decision.category == chamber)
        if year:
            where.append(Decision.year == year)
        if city:
            where.append(Decision.city == city)
        if theme:
            # matched on the key, so one subject spelled two ways stays one subject
            where.append(Decision.theme_key == theme)
        exact_first = None
        if q.strip():
            nq = textnorm.normalize(q)
            if lang != "ar" and not textnorm.has_arabic(q):
                # A French query searches the French text. An Arabic one typed on the
                # French site still searches the Arabic: the reader knows what they want.
                text_match = Decision.doc_id.in_(_i18n_match(q, lang))
            else:
                text_match = _text_match(q, nq)
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
        if (total == 0 and q.strip() and _engine.dialect.name == "postgresql"
                and not (lang != "ar" and not textnorm.has_arabic(q))):
            # The word index files بالتحفيظ apart from التحفيظ. A search that finds
            # nothing is tried again as a substring over the trigram index, so a word
            # met only with a letter glued to it is still found -- slower, but only
            # when the fast way came back empty.
            where[-1] = Decision.search_text.like(f"%{textnorm.normalize(q)}%")
            total = s.execute(select(func.count(Decision.doc_id)).where(*where)).scalar_one()
        # Newest first, straight off the sort key.
        order = [] if exact_first is None else [exact_first]
        # Only the columns a row shows. Selecting whole objects dragged every ruling's
        # full text (kilobytes each) out of the database to print a table. The rule is
        # cut here rather than in the browser for the same reason: a page of fifty
        # rules in full is a far bigger reply than the rest of the page put together.
        rows = s.execute(
            select(Decision.doc_id, Decision.decision_no, Decision.decision_date,
                   Decision.city, Decision.category, Decision.court, Decision.year,
                   Decision.case_id, Decision.file_no, Decision.theme,
                   Decision.theme_key, Decision.keywords, Decision.rule,
                   Decision.theme_source, Decision.abstract)
            .where(*where)
            .order_by(*order, Decision.sort_key.desc())
            .limit(limit).offset(offset)
        ).all()
        items = [{"doc_id": r[0], "decision_no": r[1], "date": r[2], "city": r[3],
                  "chamber": r[4], "court": r[5] or "محكمة النقض", "year": r[6],
                  "case_id": r[7], "file_no": r[8] or "", "theme": r[9] or "",
                  "theme_key": r[10] or "", "keywords": r[11] or "",
                  "rule": _excerpt(r[12] or ""), "theme_source": r[13] or "",
                  "abstract": _excerpt(r[14] or "")} for r in rows]
    if lang != "ar":
        extra = i18n_for([i["doc_id"] for i in items], lang)
        labels = subject_labels([i["theme_key"] for i in items], lang)
        for i in items:
            with_language(i, lang, extra.get(i["doc_id"]), labels)
            i["abstract_fr"] = _excerpt(i["abstract_fr"])
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


# ---------------- other languages ----------------
def _fold_i18n(row: "DecisionI18n") -> str:
    return textnorm.fold_latin(" ".join((row.abstract or "", row.keywords or "", row.body_text or "")))


def get_translation(doc_id: str, lang: str = "fr") -> Optional[dict]:
    """The stored translation of the text, unless the ruling has been edited since."""
    with session() as s:
        t = s.scalar(select(DecisionI18n).where(DecisionI18n.doc_id == doc_id,
                                                DecisionI18n.lang == lang))
        if t is None or not t.body_text:
            return None
        d = s.get(Decision, doc_id)
        stale = d is not None and (d.version or 0) != t.source_version
        return {"doc_id": t.doc_id, "lang": t.lang, "text": t.body_text, "model": t.model,
                "created_at": t.updated_at.isoformat() if t.updated_at else "",
                "stale": stale}


def save_i18n(doc_id: str, lang: str, *, model: str = "", version: Optional[int] = None,
              **fields) -> None:
    """Set some of a ruling's fields in `lang` (body_text, abstract, abstract_of,
    keywords), creating the row if needed. Fields not given are left as they are."""
    with session() as s:
        t = s.scalar(select(DecisionI18n).where(DecisionI18n.doc_id == doc_id,
                                                DecisionI18n.lang == lang))
        if t is None:
            t = DecisionI18n(doc_id=doc_id, lang=lang)
            s.add(t)
        for k in ("body_text", "abstract", "abstract_of", "keywords"):
            if k in fields and fields[k] is not None:
                setattr(t, k, fields[k])
        if model:
            t.model = model
        if version is not None:
            t.source_version = version
        t.search_text = _fold_i18n(t)
        t.updated_at = clock.utcnow()
        s.commit()


def save_translation(doc_id: str, lang: str, text: str, model: str, version: int) -> None:
    """Store a translated text, replacing an older one (a corrected ruling is
    translated again)."""
    save_i18n(doc_id, lang, body_text=text, model=model, version=version)


def translation_count(lang: str = "fr") -> int:
    with session() as s:
        return s.scalar(select(func.count()).select_from(DecisionI18n)
                        .where(DecisionI18n.lang == lang, DecisionI18n.body_text != "")) or 0


def i18n_for(doc_ids: List[str], lang: str) -> dict:
    """{doc_id: {abstract, abstract_of, keywords, has_text}} for the rulings that have
    anything in `lang`. One query for a whole page of rows."""
    if not doc_ids or lang == "ar":
        return {}
    with session() as s:
        rows = s.execute(
            select(DecisionI18n.doc_id, DecisionI18n.abstract, DecisionI18n.abstract_of,
                   DecisionI18n.keywords, func.length(DecisionI18n.body_text))
            .where(DecisionI18n.lang == lang, DecisionI18n.doc_id.in_(doc_ids))).all()
    return {r[0]: {"abstract": r[1] or "", "abstract_of": r[2] or "",
                   "keywords": r[3] or "", "has_text": bool(r[4])} for r in rows}


def subject_labels(keys: List[str], lang: str) -> dict:
    """{key: label} in `lang`, for the subjects that have one."""
    keys = [k for k in set(keys) if k]
    if not keys or lang == "ar":
        return {}
    with session() as s:
        rows = s.execute(select(Subject.key, Subject.label_fr)
                         .where(Subject.key.in_(keys), Subject.label_fr != "")).all()
    return {k: v for k, v in rows}


def with_language(row: dict, lang: str, extra: Optional[dict] = None,
                  labels: Optional[dict] = None) -> dict:
    """A ruling's row with its fields in `lang` alongside the Arabic ones.

    The Arabic fields are never replaced: the French goes in *_fr fields and the
    page chooses. A missing translation is an empty field, and has_fr says whether
    the text itself exists in French.
    """
    if lang == "ar":
        return row
    extra = extra or {}
    labels = labels or {}
    row["theme_fr"] = labels.get(row.get("theme_key", "") or "", "")
    row["keywords_fr"] = extra.get("keywords", "")
    row["abstract_fr"] = extra.get("abstract", "")
    row["abstract_fr_of"] = extra.get("abstract_of", "")
    row["has_fr"] = extra.get("has_text", False)
    return row


def upsert_many(rows: List[tuple], *, publish: bool, batch: int = 400) -> dict:
    """Insert or update many rulings in one pass.

    One import used to cost four transactions per ruling -- the row, its links, its
    published state, and a lookup before all that. At 29,384 rulings that is the bulk
    of the time. Here one session serves the whole run and commits every `batch`
    rulings, which is also the unit of work that survives an interruption.

    Each row is (fields, body_text, file_name, links). Same rules as before: a
    ruling edited by hand is left exactly as edited.
    """
    counts = {"imported": 0, "updated": 0, "kept_edited": 0}
    with session() as s:
        for n, (data, body_text, file_name, links) in enumerate(rows, 1):
            d = s.get(Decision, data["doc_id"])
            if d is not None and d.edited_at is not None:
                counts["kept_edited"] += 1
                continue
            existed = d is not None
            if d is None:
                d = Decision(doc_id=data["doc_id"])
                s.add(d)
            for k in ("source_file", "fmt", "read_method", "category", "level", "court",
                      "decision_no", "file_no", "decision_date", "city", "year",
                      "case_id", "outcome", "pii_removed", "review",
                      "theme", "theme_key", "keywords", "rule",
                      "theme_source", "abstract"):
                if k in data:
                    setattr(d, k, data[k])
            d.sort_key = _sort_key(d.decision_date, d.decision_no)
            d.file_name = file_name
            d.body_text = body_text
            d.search_text = textnorm.normalize(body_text)
            if publish:
                d.state = "published"
            elif d.state in ("", "withdrawn") or d.state not in STATES:
                d.state = "imported"
            elif d.state == "published":
                d.state = "under_review"

            if links:
                for row in s.scalars(select(Link).where(
                        or_(Link.parent_doc == d.doc_id, Link.child_doc == d.doc_id))):
                    s.delete(row)
                for l in links:
                    if l.get("role") == "reviews":
                        s.add(Link(parent_doc=d.doc_id, child_doc=l["to"],
                                   confidence=l.get("confidence", "")))
                    else:
                        s.add(Link(parent_doc=l["to"], child_doc=d.doc_id,
                                   confidence=l.get("confidence", "")))

            counts["updated" if existed else "imported"] += 1
            if n % batch == 0:
                s.commit()
        s.commit()
    return counts
