"""The platform's API: the application, put together from its modules.

Each area keeps its own routes beside its own code:

  auth_routes    signing in (password, second factor, lockout)
  reading        the reader's side: browse, search, a ruling, its French, the file
  editing        the admin's side of a ruling: review, publish, correct, drafts, reports
  import_routes  the admin's upload of a delivery (the import itself: importer.py)
  accounts, billing, contracts, crm, support, library, insights
                 people and organizations, plans, contracts and transfers, the CRM,
                 support tickets, a reader's library, following the readers

The platform stores only anonymized content. Raw documents never enter it: imports carry
anonymized files + metadata, and the import gate refuses anything that still looks like PII.

Run (local):   uvicorn server:app --port 8000
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import accounts
import auth as authmod
import auth_routes
import billing
import contracts
import crm
import db
import editing
import import_routes
import insights
import library
import reading
import settings
import storage
import support

app = FastAPI(title="Anonymized Decisions Platform", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.S.allow_origins.split(","),
    allow_methods=["*"], allow_headers=["*"],
)

for _module in (auth_routes, reading, editing, import_routes,
                accounts, billing, contracts, crm, support, library, insights):
    app.include_router(_module.router)


def configure() -> None:
    """Read the settings again and reconnect the database and the store -- for tests,
    each of which runs with its own."""
    settings.reload()
    db.configure()
    storage.reset()
    billing.forget_plans()
    _startup()


@app.on_event("startup")
def _startup() -> None:
    settings.check()
    db.init_db()
    email, pw = os.getenv("SEED_EMAIL", ""), os.getenv("SEED_PASSWORD", "")
    if email and pw and not db.get_user(email):
        db.upsert_user(email, authmod.hash_password(pw), role="admin")
    ce, cp = os.getenv("SEED_CLIENT_EMAIL", ""), os.getenv("SEED_CLIENT_PASSWORD", "")
    if ce and cp and not db.get_user(ce):
        db.upsert_user(ce, authmod.hash_password(cp), role="client")
    billing.seed_plans()
    accounts.adopt_orphan_clients()
    insights.ensure_indexes()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "storage": type(storage.STORE).__name__}
