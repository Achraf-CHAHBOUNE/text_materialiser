"""Every setting the platform needs to start, read from the environment in one place
and checked before anything serves a request.

    import settings
    settings.S.auto_publish          # read where it is used, never copied at import

A setting read deep inside one feature (SMTP_*, TRANSLATE_*, SELLER_*) stays next to
that feature; this module holds what decides how the platform starts and behaves.
`check()` runs at startup and refuses a production start (DATABASE_URL set) with an
unsafe or missing value, naming every problem at once rather than the first.
`reload()` re-reads the environment -- for tests, which each run with their own.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# From a terminal the settings live in platform/.env; inside Docker they come from
# compose, and load_dotenv leaves anything already set alone, so the container's
# environment always wins. Everything reads its settings through this module first, so
# a key goes in one file and is found everywhere -- scripts included.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:                       # python-dotenv is optional at runtime
    pass

DEV_SECRET = "dev-secret-change-me"


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name, "")
    return default if raw == "" else raw.strip().lower() not in ("0", "false", "no", "off")


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "")
    try:
        return int(raw) if raw.strip() else default
    except ValueError:
        raise SystemExit(f"Setting {name}={raw!r} must be a whole number")


@dataclass(frozen=True)
class Settings:
    database_url: str               # Postgres in production; empty means SQLite in db_dir
    db_dir: str
    filestore_dir: str
    s3_endpoint: str
    auth_secret: str
    auth_ttl_seconds: int
    auto_publish: bool
    login_max_tries: int
    login_lockout_seconds: int
    import_inline_max: int
    allow_origins: str
    auto_enrich: bool               # the worker asks the model for new rulings' subjects
    enrich_per_pass: int

    @property
    def production(self) -> bool:
        return bool(self.database_url)


def load() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", ""),
        db_dir=os.getenv("DB_DIR", "data"),
        filestore_dir=os.getenv("FILESTORE_DIR", "data/files"),
        s3_endpoint=os.getenv("S3_ENDPOINT") or os.getenv("MINIO_ENDPOINT") or "",
        auth_secret=os.getenv("AUTH_SECRET") or DEV_SECRET,
        auth_ttl_seconds=_int("AUTH_TTL_SECONDS", 7 * 24 * 3600),
        auto_publish=_flag("AUTO_PUBLISH", True),
        login_max_tries=_int("LOGIN_MAX_TRIES", 8),
        login_lockout_seconds=_int("LOGIN_LOCKOUT_SECONDS", 900),
        import_inline_max=_int("IMPORT_INLINE_MAX", 200),
        allow_origins=os.getenv("ALLOW_ORIGINS", "*"),
        auto_enrich=_flag("AUTO_ENRICH", False),
        enrich_per_pass=_int("ENRICH_PER_PASS", 200),
    )


def problems(s: Settings) -> list:
    """What would make this start unsafe. Empty for a development start."""
    out = []
    if not s.production:
        return out
    if s.auth_secret == DEV_SECRET or len(s.auth_secret) < 32:
        out.append("AUTH_SECRET must be set to a long random value (32 characters or more)")
    if not s.s3_endpoint and s.filestore_dir == "data/files":
        out.append("set S3_ENDPOINT (object store) or FILESTORE_DIR (a mounted folder) for the Word files")
    if s.auto_enrich and not (os.getenv("TRANSLATE_API_KEY") or os.getenv("GEMINI_API_KEY")
                              or os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENCODE_API_KEY")):
        out.append("AUTO_ENRICH=1 needs a model key (GEMINI_API_KEY, TRANSLATE_API_KEY, ...)")
    if s.login_max_tries < 1 or s.login_lockout_seconds < 1:
        out.append("LOGIN_MAX_TRIES and LOGIN_LOCKOUT_SECONDS must be positive")
    return out


def check() -> None:
    found = problems(S)
    if found:
        raise SystemExit("Refusing to start:\n  - " + "\n  - ".join(found))


def reload() -> Settings:
    global S
    S = load()
    return S


S = load()
