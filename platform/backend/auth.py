"""Minimal auth: PBKDF2 password hashing + an HMAC-signed bearer token.

Stdlib only (no extra deps). Good enough for a single-tenant pilot; swap for
Supabase/OAuth + per-user scoping when going multi-tenant.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

import settings


# ---------- passwords ----------
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"pbkdf2$200000${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


# ---------- tokens ----------
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(email: str, sid: str = "") -> str:
    """A signed token for `email`. `sid` names the server-side session it belongs to,
    so signing out -- or signing in on another device -- can end it before it expires."""
    body = {"sub": email, "exp": int(time.time()) + settings.S.auth_ttl_seconds}
    if sid:
        body["sid"] = sid
    payload = _b64(json.dumps(body).encode())
    sig = _b64(hmac.new(settings.S.auth_secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def read_token(token: str) -> dict | None:
    """{"sub", "sid"} if the token is valid and unexpired, else None."""
    try:
        payload, sig = token.split(".")
        expected = _b64(hmac.new(settings.S.auth_secret.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_unb64(payload))
        if int(data.get("exp", 0)) < int(time.time()):
            return None
        return {"sub": data.get("sub"), "sid": data.get("sid", "")}
    except Exception:
        return None


def verify_token(token: str) -> str | None:
    """Return the email if the token is valid and unexpired, else None."""
    data = read_token(token)
    return data["sub"] if data else None


# ---------- one-time tokens (invitations, password resets) ----------
def new_secret_token() -> str:
    """What goes in the link. Only its hash is stored, so a copy of the database
    cannot be used to accept an invitation or reset a password."""
    return _b64(os.urandom(24))


def hash_secret(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------- second factor (TOTP, RFC 6238) ----------
# The six-digit codes of Google Authenticator, Microsoft Authenticator and the like.
# Written out rather than taken from a package: it is thirty lines of standard HMAC.
def new_totp_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode().rstrip("=")


def totp(secret: str, at: float | None = None, step: int = 30) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    counter = int((time.time() if at is None else at) // step)
    digest = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    """True if `code` is right now, or one step either side (a phone clock is rarely
    exact to the second)."""
    code = (code or "").strip().replace(" ", "")
    if not secret or len(code) != 6 or not code.isdigit():
        return False
    now = time.time()
    return any(hmac.compare_digest(totp(secret, now + k * 30), code)
               for k in range(-window, window + 1))


def totp_uri(secret: str, email: str, issuer: str = "Jurisprudence") -> str:
    from urllib.parse import quote
    return (f"otpauth://totp/{quote(issuer)}:{quote(email)}"
            f"?secret={secret}&issuer={quote(issuer)}&digits=6&period=30")
