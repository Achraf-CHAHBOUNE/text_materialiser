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

_SECRET = os.getenv("AUTH_SECRET", "dev-secret-change-me").encode()
_TOKEN_TTL = int(os.getenv("AUTH_TTL_SECONDS", str(7 * 24 * 3600)))  # 7 days


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


def make_token(email: str) -> str:
    payload = _b64(json.dumps({"sub": email, "exp": int(time.time()) + _TOKEN_TTL}).encode())
    sig = _b64(hmac.new(_SECRET, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def verify_token(token: str) -> str | None:
    """Return the email if the token is valid and unexpired, else None."""
    try:
        payload, sig = token.split(".")
        expected = _b64(hmac.new(_SECRET, payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_unb64(payload))
        if int(data.get("exp", 0)) < int(time.time()):
            return None
        return data.get("sub")
    except Exception:
        return None
