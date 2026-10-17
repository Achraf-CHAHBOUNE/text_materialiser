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
from typing import Optional, Tuple
from urllib.parse import urlparse

from fastapi import Depends, Header, HTTPException, Request, Response

import auth as authmod
import db
import settings

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


# ---------------- the session cookie ----------------
# The browser keeps the session in an HttpOnly cookie: page scripts never see it, so
# a script slipped into a page cannot carry the session away, and file links need no
# token in their address (where logs, history and copied links would keep it). The
# Authorization header still works -- scripts, tests, a page loaded before this change.
COOKIE = "tok_session"
_SAFE = ("GET", "HEAD", "OPTIONS")


def set_session_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(COOKIE, token, max_age=settings.S.auth_ttl_seconds, path="/",
                        httponly=True, samesite="lax", secure=request.url.scheme == "https")


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


def _same_origin(request: Request) -> bool:
    """A change made with the cookie must come from the site itself (or an origin the
    settings allow): another site's page cannot make the reader's browser act."""
    source = request.headers.get("origin") or request.headers.get("referer") or ""
    host = urlparse(source).netloc
    allowed = {request.headers.get("host", "")} | {
        urlparse(o.strip()).netloc for o in settings.S.allow_origins.split(",") if o.strip() not in ("", "*")}
    return bool(host) and host in allowed


def _credentials(request: Request, authorization: Optional[str]) -> Tuple[str, str]:
    """(token, where it came from): the header first, then the cookie."""
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ", 1)[1], "header"
    cookie = request.cookies.get(COOKIE, "")
    return (cookie, "cookie") if cookie else ("", "")


def _authenticate(request: Request, token: str, source: str) -> dict:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if source == "cookie" and request.method not in _SAFE and not _same_origin(request):
        raise HTTPException(status_code=403, detail="Cross-site request refused")
    return _user_from_token(token, request.url.path)


def current_user(request: Request, authorization: Optional[str] = Header(None)) -> dict:
    return _authenticate(request, *_credentials(request, authorization))


def flex_user(request: Request, authorization: Optional[str], token: str) -> dict:
    """Auth for browser file links: the header, the cookie, or -- for a link made before
    the cookie existed -- ?token= in the address."""
    found, source = _credentials(request, authorization)
    if not found and token:
        found, source = token, "query"
    return _authenticate(request, found, source)


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
