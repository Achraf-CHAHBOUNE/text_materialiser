"""Who is asking, and what they may do. Every route module takes its guards from here.

Roles:
    admin         everything, settings, staff accounts
    editor        the rulings: import, correct, publish, error reports
    sales         the CRM: leads, organizations, subscriptions, invoices, tickets
    client_admin  a customer's account holder: reads, and manages the firm's seats
    client        a customer's reader

A customer's people read only while their organization has a running subscription.
The routes they need to put that right -- their account, invoices, support -- stay
open when it has lapsed.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request

import auth as authmod
import db

STAFF = ("admin", "editor", "sales")
CLIENTS = ("client_admin", "client")
ROLES = STAFF + CLIENTS

# Reachable with a lapsed subscription: enough to see why, pay, and ask for help.
_OPEN_WHEN_LAPSED = ("/api/auth/", "/api/account", "/api/support", "/api/me/profile")


def _user_from_token(token: str, path: str = "") -> dict:
    data = authmod.read_token(token or "")
    if not data or not data.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.get_user(data["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="Unknown account")
    if user["status"] != "active":               # suspension takes effect immediately
        raise HTTPException(status_code=403, detail="Account suspended")
    import accounts
    if not accounts.session_alive(data.get("sid", ""), user["id"]):
        raise HTTPException(status_code=401, detail="Session ended")
    user["sid"] = data.get("sid", "")
    if user["role"] in CLIENTS and not path.startswith(_OPEN_WHEN_LAPSED):
        import billing
        state = billing.access_state(user.get("org_id"))
        if state != "ok":
            raise HTTPException(status_code=402, detail={"subscription": state})
    return user


def current_user(request: Request, authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _user_from_token(authorization.split(" ", 1)[1], request.url.path)


def flex_user(request: Request, authorization: Optional[str], token: str) -> dict:
    """Auth for browser file links: Bearer header OR ?token= query."""
    tok = (authorization.split(" ", 1)[1]
           if authorization and authorization.startswith("Bearer ") else token)
    return _user_from_token(tok, request.url.path)


def require(*roles: str):
    def guard(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Not allowed")
        return user
    return guard


require_admin = require("admin")
require_editor = require("admin", "editor")          # the rulings
require_sales = require("admin", "sales")            # the CRM
require_staff = require(*STAFF)


def today() -> dt.date:
    return dt.date.today()
