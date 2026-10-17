"""Signing in: the password, the second factor, and the lockout that stops guessing."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

import accounts
import auth as authmod
import billing
import db
import limits
import settings
from deps import STAFF, current_user, set_session_cookie

router = APIRouter()


# ---------------- auth plumbing ----------------
# Who is asking and what they may do lives in deps.py, shared by every route module.


class LoginBody(BaseModel):
    email: str
    password: str
    code: str = ""          # the six digits, for an account with a second factor


# ---------------- guarding the sign-in ----------------
# Passwords could be guessed without limit: every attempt got the same prompt answer,
# as fast as the network allowed. A site holding court rulings cannot leave that open.
# After LOGIN_MAX_TRIES wrong passwords, that email and that address are turned away
# for LOGIN_LOCKOUT_SECONDS whether or not the next password is right, and a correct
# password clears the count. Kept in the database (limits.py), so every copy of the
# API sees the same count and a restart does not hand out fresh tries.


def _login_key(email: str, request: Request) -> tuple:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    caller = forwarded or (request.client.host if request.client else "?")
    return (email.strip().lower(), caller)


def _locked_for(key: tuple) -> int:
    """Seconds still to wait, 0 if the caller may try."""
    tries, lockout = settings.S.login_max_tries, settings.S.login_lockout_seconds
    fails = limits.recent("login", f"{key[0]}|{key[1]}", lockout)
    if len(fails) < tries:
        return 0
    # locked until the lockout has run from the failure that reached the limit
    reached = fails[-tries]
    return max(0, int((reached - dt.datetime.utcnow()).total_seconds()) + lockout)


def _note_failure(key: tuple) -> None:
    limits.add("login", f"{key[0]}|{key[1]}")


@router.post("/api/auth/login")
def login(body: LoginBody, request: Request, response: Response) -> dict:
    key = _login_key(body.email, request)
    wait = _locked_for(key)
    if wait:
        raise HTTPException(status_code=429, detail=f"Too many attempts. Try again in "
                                                    f"{max(1, wait // 60)} minute(s).",
                            headers={"Retry-After": str(wait)})
    user = db.get_user(body.email)
    if not user or not authmod.verify_password(body.password, user["password_hash"]):
        _note_failure(key)
        db.add_audit(body.email, "login_failed", "user", body.email, new=key[1])
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user["status"] != "active":
        raise HTTPException(status_code=403, detail="Account suspended")
    secret = user.get("mfa_secret", "")
    if secret and not secret.startswith("pending:"):
        if not body.code:
            # the password was right: ask for the second factor, count nothing yet
            raise HTTPException(status_code=401, detail={"mfa": True})
        if not authmod.verify_totp(secret, body.code):
            _note_failure(key)
            db.add_audit(body.email, "login_failed", "user", body.email, new="wrong code")
            raise HTTPException(status_code=401, detail={"mfa": True, "wrong": True})
    limits.clear("login", f"{key[0]}|{key[1]}")
    db.touch_login(user["email"])
    sid = accounts.open_session(user, key[1], request.headers.get("user-agent", ""))
    db.log_activity(user["email"], "login", "")
    token = authmod.make_token(user["email"], sid)
    set_session_cookie(response, request, token)
    # the token is still in the answer for scripts and older pages; the site uses the cookie
    return {"token": token, "email": user["email"],
            "role": user["role"], "language": user.get("language", "ar"),
            "access": billing.access_state(user.get("org_id")) if user["role"] not in STAFF else "ok"}


@router.post("/api/auth/session")
def adopt_session(request: Request, response: Response, user: dict = Depends(current_user)) -> dict:
    """A page that still holds its token from before the cookie existed hands it over
    once (in the Authorization header) and gets the cookie for the same session, then
    forgets the token: nobody is signed out by the change."""
    token = (request.headers.get("authorization") or "").split(" ", 1)[-1]
    if not token or not request.headers.get("authorization", "").startswith("Bearer "):
        raise HTTPException(status_code=400, detail="Send the token in the Authorization header")
    set_session_cookie(response, request, token)
    return {"email": user["email"], "role": user["role"], "language": user.get("language", "ar")}
