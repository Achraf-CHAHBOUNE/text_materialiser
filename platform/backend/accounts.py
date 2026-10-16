"""Organizations, their people, and how those people get in.

A customer is an organization -- a firm, a company, an institution, or one lawyer on
their own. Its people are users with org_id set. Its account holder (client_admin)
invites colleagues up to the seats its subscription pays for.

Sessions are rows, not just signed tokens, so they can be ended: signing out ends one,
a password reset ends all, and a reader signing in on a second device ends the first --
one seat is one person at a time. Staff may be signed in on several devices.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import DateTime, Integer, String, Text, func, select
from sqlalchemy.orm import Mapped, mapped_column

import auth as authmod
import db
import mailer
from deps import CLIENTS, ROLES, STAFF, current_user, require_admin, require_sales


# ---------------- tables ----------------
class Organization(db.Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String, default="firm")   # firm|company|institution|individual
    city: Mapped[str] = mapped_column(String, default="")
    ice: Mapped[str] = mapped_column(String, default="")        # identifiant commun de l'entreprise
    address: Mapped[str] = mapped_column(String, default="")
    phone: Mapped[str] = mapped_column(String, default="")
    email: Mapped[str] = mapped_column(String, default="")
    language: Mapped[str] = mapped_column(String, default="ar")
    account_manager: Mapped[str] = mapped_column(String, default="")   # a sales user's email
    status: Mapped[str] = mapped_column(String, default="prospect")    # prospect|customer|former
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    deleted_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)


class UserSession(db.Base):
    __tablename__ = "user_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    ip: Mapped[str] = mapped_column(String, default="")
    device: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    last_seen: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    revoked_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    revoked_why: Mapped[str] = mapped_column(String, default="")


class Invitation(db.Base):
    __tablename__ = "invitations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, index=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    role: Mapped[str] = mapped_column(String, default="client")
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    invited_by: Mapped[str] = mapped_column(String, default="")
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)
    accepted_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class PasswordReset(db.Base):
    __tablename__ = "password_resets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)
    used_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)


# ---------------- sessions ----------------
_SEEN_EVERY = dt.timedelta(minutes=5)     # last_seen is a guide, not a log: write rarely


def open_session(user: dict, ip: str, device: str) -> str:
    """A new session; for a customer's reader, the end of any other."""
    sid = uuid.uuid4().hex
    now = dt.datetime.utcnow()
    with db.session() as s:
        if user["role"] in CLIENTS:
            for old in s.scalars(select(UserSession).where(UserSession.user_id == user["id"],
                                                           UserSession.revoked_at.is_(None))):
                old.revoked_at, old.revoked_why = now, "signed in elsewhere"
        s.add(UserSession(id=sid, user_id=user["id"], ip=ip[:64], device=device[:200]))
        s.commit()
    return sid


def session_alive(sid: str, user_id: int) -> bool:
    if not sid:
        return False
    with db.session() as s:
        row = s.get(UserSession, sid)
        if row is None or row.user_id != user_id or row.revoked_at is not None:
            return False
        now = dt.datetime.utcnow()
        if now - (row.last_seen or now) > _SEEN_EVERY:
            row.last_seen = now
            s.commit()
        return True


def end_sessions(user_id: int, why: str, except_sid: str = "") -> int:
    n = 0
    with db.session() as s:
        for row in s.scalars(select(UserSession).where(UserSession.user_id == user_id,
                                                       UserSession.revoked_at.is_(None))):
            if row.id != except_sid:
                row.revoked_at, row.revoked_why = dt.datetime.utcnow(), why
                n += 1
        s.commit()
    return n


def end_session(sid: str, why: str = "signed out") -> None:
    with db.session() as s:
        row = s.get(UserSession, sid)
        if row and row.revoked_at is None:
            row.revoked_at, row.revoked_why = dt.datetime.utcnow(), why
            s.commit()


# ---------------- organizations ----------------
ORG_FIELDS = ("name", "kind", "city", "ice", "address", "phone", "email", "language",
              "account_manager", "status", "notes")


def org_dict(o: Organization) -> dict:
    return {"id": o.id, **{k: getattr(o, k) or "" for k in ORG_FIELDS},
            "created_at": o.created_at.isoformat() if o.created_at else ""}


def get_org(org_id: Optional[int]) -> Optional[dict]:
    if not org_id:
        return None
    with db.session() as s:
        o = s.get(Organization, org_id)
        return org_dict(o) if o and o.deleted_at is None else None


def create_org(data: dict, actor: str) -> dict:
    with db.session() as s:
        o = Organization(**{k: (data.get(k) or "") for k in ORG_FIELDS if k in data})
        if not o.name:
            raise HTTPException(status_code=400, detail="Name required")
        s.add(o)
        s.commit()
        out = org_dict(o)
    db.add_audit(actor, "create", "organization", str(out["id"]), new=out["name"])
    return out


def update_org(org_id: int, data: dict, actor: str) -> dict:
    with db.session() as s:
        o = s.get(Organization, org_id)
        if not o or o.deleted_at:
            raise HTTPException(status_code=404, detail="Organization not found")
        for k in ORG_FIELDS:
            if k in data and data[k] is not None and str(getattr(o, k) or "") != str(data[k]):
                s.add(db.AuditLog(actor=actor, action="correct", entity="organization",
                                  entity_id=str(org_id), field=k, old_value=str(getattr(o, k) or ""),
                                  new_value=str(data[k])))
                setattr(o, k, data[k])
        s.commit()
        return org_dict(o)


def org_members(org_id: int) -> List[dict]:
    with db.session() as s:
        users = s.scalars(select(db.User).where(db.User.org_id == org_id).order_by(db.User.email))
        out = []
        for u in users:
            d = db._user_dict(u)
            d.pop("password_hash", None)
            d.pop("mfa_secret", None)
            out.append(d)
        return out


def pending_invitations(org_id: int) -> List[dict]:
    now = dt.datetime.utcnow()
    with db.session() as s:
        rows = s.scalars(select(Invitation).where(
            Invitation.org_id == org_id, Invitation.accepted_at.is_(None),
            Invitation.cancelled_at.is_(None), Invitation.expires_at > now))
        return [{"id": i.id, "email": i.email, "role": i.role, "invited_by": i.invited_by,
                 "expires_at": i.expires_at.isoformat()} for i in rows]


def seats_used(org_id: int) -> int:
    with db.session() as s:
        users = s.scalar(select(func.count()).select_from(db.User).where(
            db.User.org_id == org_id, db.User.status == "active")) or 0
    return users + len(pending_invitations(org_id))


def seats_used_many(org_ids) -> dict:
    """{org_id: seats_used(org_id)} for many organizations, in two queries."""
    ids = list({o for o in org_ids if o})
    if not ids:
        return {}
    now = dt.datetime.utcnow()
    with db.session() as s:
        users = dict(s.execute(select(db.User.org_id, func.count()).where(
            db.User.org_id.in_(ids), db.User.status == "active").group_by(db.User.org_id)).all())
        invited = dict(s.execute(select(Invitation.org_id, func.count()).where(
            Invitation.org_id.in_(ids), Invitation.accepted_at.is_(None),
            Invitation.cancelled_at.is_(None), Invitation.expires_at > now).group_by(Invitation.org_id)).all())
    return {o: int(users.get(o, 0)) + int(invited.get(o, 0)) for o in ids}


def invite(org_id: int, email: str, role: str, inviter: dict, lang: str = "") -> dict:
    """Invite someone into an organization, within its seats. Emails the link."""
    import billing
    email = email.strip().lower()
    if role not in CLIENTS:
        raise HTTPException(status_code=400, detail="Role must be client or client_admin")
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Email required")
    existing = db.get_user(email)
    if existing and existing.get("org_id") == org_id:
        raise HTTPException(status_code=409, detail="Already a member")
    if existing:
        raise HTTPException(status_code=409, detail="This email already has an account")
    org = get_org(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    seats = billing.seats_for(org_id)
    if inviter["role"] not in STAFF and seats_used(org_id) >= seats:
        raise HTTPException(status_code=409, detail={"seats": seats})
    token = authmod.new_secret_token()
    with db.session() as s:
        for old in s.scalars(select(Invitation).where(Invitation.email == email,
                                                      Invitation.org_id == org_id,
                                                      Invitation.accepted_at.is_(None))):
            old.cancelled_at = dt.datetime.utcnow()
        s.add(Invitation(email=email, org_id=org_id, role=role,
                         token_hash=authmod.hash_secret(token), invited_by=inviter["email"],
                         expires_at=dt.datetime.utcnow() + dt.timedelta(days=7)))
        s.commit()
    lang = lang or org.get("language") or "ar"
    mailer.queue(email, "invitation", lang, org=org["name"],
                 inviter=inviter.get("full_name") or inviter["email"],
                 link=f"{mailer.site_url()}/{lang}/invite/{token}")
    db.add_audit(inviter["email"], "invite", "organization", str(org_id), new=f"{email} ({role})")
    return {"email": email, "role": role, "link": f"/invite/{token}"}


# ---------------- routes ----------------
router = APIRouter()


class ProfileBody(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    language: Optional[str] = None


class PasswordBody(BaseModel):
    current: str
    new: str


class InviteBody(BaseModel):
    email: str
    role: str = "client"
    language: str = ""


class AcceptBody(BaseModel):
    password: str
    full_name: str = ""


class ForgotBody(BaseModel):
    email: str
    language: str = "ar"


class ResetBody(BaseModel):
    password: str


class CodeBody(BaseModel):
    code: str


def _strong(pw: str) -> None:
    if len(pw or "") < 10:
        raise HTTPException(status_code=400, detail="Password: at least 10 characters")


def _public_user(u: dict) -> dict:
    out = {k: u.get(k) for k in ("email", "role", "status", "full_name", "phone",
                                 "language", "org_id", "mfa", "last_login")}
    return out


@router.get("/api/account")
def account(user: dict = Depends(current_user)) -> dict:
    """Who I am, my organization, its subscription and seats."""
    import billing
    out = {"user": _public_user(user), "org": None, "subscription": None,
           "access": "ok", "mfa_required": user["role"] in STAFF and not user.get("mfa")}
    org = get_org(user.get("org_id"))
    if org:
        out["org"] = org
        out["subscription"] = billing.current_subscription(org["id"])
        out["access"] = billing.access_state(org["id"])
        out["seats"] = {"total": billing.seats_for(org["id"]), "used": seats_used(org["id"])}
        out["quota"] = billing.daily_downloads(org["id"])
    return out


@router.patch("/api/account/profile")
def update_profile(body: ProfileBody, user: dict = Depends(current_user)) -> dict:
    with db.session() as s:
        u = s.get(db.User, user["id"])
        if body.full_name is not None:
            u.full_name = body.full_name.strip()[:120]
        if body.phone is not None:
            u.phone = body.phone.strip()[:40]
        if body.language in ("ar", "fr"):
            u.language = body.language
        s.commit()
    return _public_user(db.get_user(user["email"]))


@router.post("/api/account/password")
def change_password(body: PasswordBody, user: dict = Depends(current_user)) -> dict:
    if not authmod.verify_password(body.current, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is wrong")
    _strong(body.new)
    with db.session() as s:
        u = s.get(db.User, user["id"])
        u.password_hash = authmod.hash_password(body.new)
        s.commit()
    end_sessions(user["id"], "password changed", except_sid=user.get("sid", ""))
    db.add_audit(user["email"], "change_password", "user", user["email"])
    return {"ok": True}


@router.post("/api/auth/logout")
def logout(user: dict = Depends(current_user)) -> dict:
    end_session(user.get("sid", ""))
    return {"ok": True}


# -- second factor --
@router.post("/api/account/mfa/setup")
def mfa_setup(user: dict = Depends(current_user)) -> dict:
    """A new secret, held as pending until a code from it is confirmed."""
    if user.get("mfa"):
        raise HTTPException(status_code=409, detail="Already enabled")
    secret = authmod.new_totp_secret()
    with db.session() as s:
        s.get(db.User, user["id"]).mfa_secret = "pending:" + secret
        s.commit()
    return {"secret": secret, "uri": authmod.totp_uri(secret, user["email"])}


@router.post("/api/account/mfa/enable")
def mfa_enable(body: CodeBody, user: dict = Depends(current_user)) -> dict:
    pending = user.get("mfa_secret", "")
    if not pending.startswith("pending:"):
        raise HTTPException(status_code=400, detail="Start the setup first")
    secret = pending.split(":", 1)[1]
    if not authmod.verify_totp(secret, body.code):
        raise HTTPException(status_code=400, detail="Wrong code")
    with db.session() as s:
        s.get(db.User, user["id"]).mfa_secret = secret
        s.commit()
    db.add_audit(user["email"], "mfa_enable", "user", user["email"])
    return {"ok": True}


@router.post("/api/account/mfa/disable")
def mfa_disable(body: CodeBody, user: dict = Depends(current_user)) -> dict:
    secret = user.get("mfa_secret", "")
    if not secret or secret.startswith("pending:") or not authmod.verify_totp(secret, body.code):
        raise HTTPException(status_code=400, detail="Wrong code")
    with db.session() as s:
        s.get(db.User, user["id"]).mfa_secret = ""
        s.commit()
    db.add_audit(user["email"], "mfa_disable", "user", user["email"])
    return {"ok": True}


# -- the firm's seats (client_admin) --
def _my_org(user: dict) -> int:
    if user["role"] != "client_admin" or not user.get("org_id"):
        raise HTTPException(status_code=403, detail="Account holder only")
    return user["org_id"]


@router.get("/api/account/team")
def team(user: dict = Depends(current_user)) -> dict:
    import billing
    org_id = user.get("org_id")
    if not org_id:
        return {"members": [], "invitations": [], "seats": {"total": 0, "used": 0}}
    return {"members": org_members(org_id),
            "invitations": pending_invitations(org_id) if user["role"] == "client_admin" else [],
            "seats": {"total": billing.seats_for(org_id), "used": seats_used(org_id)}}


@router.post("/api/account/team/invite")
def team_invite(body: InviteBody, user: dict = Depends(current_user)) -> dict:
    return invite(_my_org(user), body.email, body.role, user, body.language)


@router.delete("/api/account/team/invitations/{inv_id}")
def team_cancel_invitation(inv_id: int, user: dict = Depends(current_user)) -> dict:
    org_id = _my_org(user)
    with db.session() as s:
        inv = s.get(Invitation, inv_id)
        if not inv or inv.org_id != org_id:
            raise HTTPException(status_code=404, detail="Not found")
        inv.cancelled_at = dt.datetime.utcnow()
        s.commit()
    return {"ok": True}


@router.delete("/api/account/team/{email}")
def team_remove(email: str, user: dict = Depends(current_user)) -> dict:
    """Removing a colleague suspends the account and frees the seat; their history stays."""
    org_id = _my_org(user)
    target = db.get_user(email)
    if not target or target.get("org_id") != org_id or target["email"] == user["email"]:
        raise HTTPException(status_code=404, detail="Not found")
    db.set_user_status(email, "suspended")
    end_sessions(target["id"], "removed from the organization")
    db.add_audit(user["email"], "remove_member", "organization", str(org_id), new=email)
    return {"ok": True}


# -- invitations and resets: opened from an email link, no session yet --
def _invitation(token: str) -> Invitation:
    with db.session() as s:
        inv = s.scalar(select(Invitation).where(Invitation.token_hash == authmod.hash_secret(token)))
        if (not inv or inv.accepted_at or inv.cancelled_at
                or inv.expires_at < dt.datetime.utcnow()):
            raise HTTPException(status_code=404, detail="This invitation is no longer valid")
        s.expunge(inv)
        return inv


@router.get("/api/invitations/{token}")
def invitation_info(token: str) -> dict:
    inv = _invitation(token)
    org = get_org(inv.org_id) or {}
    return {"email": inv.email, "org": org.get("name", ""), "role": inv.role}


@router.post("/api/invitations/{token}")
def invitation_accept(token: str, body: AcceptBody) -> dict:
    inv = _invitation(token)
    _strong(body.password)
    if db.get_user(inv.email):
        raise HTTPException(status_code=409, detail="This email already has an account")
    org = get_org(inv.org_id) or {}
    with db.session() as s:
        s.add(db.User(email=inv.email, password_hash=authmod.hash_password(body.password),
                      role=inv.role, status="active", org_id=inv.org_id,
                      full_name=body.full_name.strip()[:120], language=org.get("language") or "ar"))
        row = s.get(Invitation, inv.id)
        row.accepted_at = dt.datetime.utcnow()
        s.commit()
    db.add_audit(inv.email, "accept_invitation", "organization", str(inv.org_id))
    return {"ok": True, "email": inv.email}


_RESET_TTL = dt.timedelta(hours=1)


@router.post("/api/auth/forgot")
def forgot(body: ForgotBody) -> dict:
    """Always the same answer, so the form cannot be used to learn who has an account."""
    user = db.get_user(body.email.strip().lower()) or db.get_user(body.email.strip())
    if user and user["status"] == "active":
        token = authmod.new_secret_token()
        with db.session() as s:
            s.add(PasswordReset(user_id=user["id"], token_hash=authmod.hash_secret(token),
                                expires_at=dt.datetime.utcnow() + _RESET_TTL))
            s.commit()
        lang = body.language if body.language in ("ar", "fr") else user.get("language", "ar")
        mailer.queue(user["email"], "password_reset", lang,
                     link=f"{mailer.site_url()}/{lang}/reset/{token}")
    return {"ok": True}


@router.post("/api/auth/reset/{token}")
def reset(token: str, body: ResetBody) -> dict:
    _strong(body.password)
    with db.session() as s:
        row = s.scalar(select(PasswordReset).where(PasswordReset.token_hash == authmod.hash_secret(token)))
        if not row or row.used_at or row.expires_at < dt.datetime.utcnow():
            raise HTTPException(status_code=404, detail="This link is no longer valid")
        u = s.get(db.User, row.user_id)
        u.password_hash = authmod.hash_password(body.password)
        row.used_at = dt.datetime.utcnow()
        uid, email = u.id, u.email
        s.commit()
    end_sessions(uid, "password reset")
    db.add_audit(email, "reset_password", "user", email)
    return {"ok": True}


# -- staff accounts (admin) --
class StaffBody(BaseModel):
    email: str
    role: str
    full_name: str = ""
    password: str = ""


@router.get("/api/admin/staff")
def staff_list(_: dict = Depends(require_admin)) -> list:
    with db.session() as s:
        rows = s.scalars(select(db.User).where(db.User.role.in_(STAFF)).order_by(db.User.email))
        out = []
        for u in rows:
            d = db._user_dict(u)
            d.pop("password_hash", None)
            d.pop("mfa_secret", None)
            out.append(d)
        return out


@router.post("/api/admin/staff")
def staff_create(body: StaffBody, user: dict = Depends(require_admin)) -> dict:
    if body.role not in STAFF:
        raise HTTPException(status_code=400, detail="Role must be admin, editor or sales")
    if db.get_user(body.email):
        raise HTTPException(status_code=409, detail="Account already exists")
    _strong(body.password)
    with db.session() as s:
        s.add(db.User(email=body.email.strip().lower(), role=body.role, status="active",
                      full_name=body.full_name, password_hash=authmod.hash_password(body.password)))
        s.commit()
    db.add_audit(user["email"], "create_staff", "user", body.email, new=body.role)
    return {"email": body.email, "role": body.role}


class RoleBody(BaseModel):
    role: Optional[str] = None
    status: Optional[str] = None


@router.patch("/api/admin/users/{email}")
def user_update(email: str, body: RoleBody, user: dict = Depends(require_sales)) -> dict:
    """Change a person's role or suspend them. Sales may manage customers' people;
    only an admin may touch staff."""
    target = db.get_user(email)
    if not target:
        raise HTTPException(status_code=404, detail="Not found")
    staff_target = target["role"] in STAFF or (body.role or "") in STAFF
    if staff_target and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    if email == user["email"] and (body.role or body.status == "suspended"):
        raise HTTPException(status_code=400, detail="Not on your own account")
    with db.session() as s:
        u = s.scalar(select(db.User).where(db.User.email == email))
        if body.role and body.role in ROLES and body.role != u.role:
            s.add(db.AuditLog(actor=user["email"], action="correct", entity="user", entity_id=email,
                              field="role", old_value=u.role, new_value=body.role))
            u.role = body.role
        if body.status in ("active", "suspended") and body.status != u.status:
            s.add(db.AuditLog(actor=user["email"], action=body.status, entity="user",
                              entity_id=email, field="status", old_value=u.status,
                              new_value=body.status))
            u.status = body.status
        uid = u.id
        s.commit()
    if body.status == "suspended":
        end_sessions(uid, "suspended")
    out = db.get_user(email)
    out.pop("password_hash", None)
    out.pop("mfa_secret", None)
    return out


def adopt_orphan_clients() -> int:
    """Every customer account made before organizations existed gets one of its own,
    with a year's subscription, so nobody loses access in the upgrade."""
    import billing
    n = 0
    with db.session() as s:
        orphans = list(s.scalars(select(db.User).where(db.User.role.in_(("client", "client_admin")),
                                                       db.User.org_id.is_(None))))
        for u in orphans:
            o = Organization(name=u.email, kind="individual", email=u.email, status="customer",
                             language=u.language or "ar")
            s.add(o)
            s.flush()
            u.org_id, u.role = o.id, "client_admin"
            n += 1
            billing.start_subscription(o.id, "individual", status="active", days=365,
                                       actor="upgrade", session=s)
        s.commit()
    return n
