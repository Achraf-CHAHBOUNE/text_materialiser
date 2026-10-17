"""How a client comes in, the way it happens in Morocco: a bank transfer, a signed
contract, then the accounts.

    contract   what was agreed: plan, number of accounts, from when to when, the price,
               and the signed PDF. Numbered C-2026-0001.
    transfer   money received: amount, date, the bank's reference, and the proof
               (the transfer receipt) if there is one.

Access opens when a transfer is recorded against the contract -- not before: an
account made for a client who has not paid stays closed (HTTP 402) until then. The
access runs exactly over the contract's dates. A renewal is a new contract starting
the day after the current one ends, and a new transfer.

An invoice is not a step of this: when a client asks for one for their accounting, it
is generated from the transfer, already paid.

Money is in centimes. What a client has paid is the sum of their transfers; what they
still owe is, contract by contract, the agreed price (with VAT) less what was received
against it.
"""
from __future__ import annotations

import datetime as dt
import io
import re
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Date, DateTime, Integer, String, Text, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

import clock
import accounts
import billing
import db
from deps import require_sales


class Contract(db.Base):
    __tablename__ = "contracts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    number: Mapped[str] = mapped_column(String, unique=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    plan_code: Mapped[str] = mapped_column(String, default="")
    seats: Mapped[int] = mapped_column(Integer, default=1)
    starts_on: Mapped[dt.date] = mapped_column(Date)
    ends_on: Mapped[dt.date] = mapped_column(Date, index=True)
    amount_ht: Mapped[int] = mapped_column(Integer, default=0)       # the whole contract, centimes
    vat_rate: Mapped[int] = mapped_column(Integer, default=2000)
    vat: Mapped[int] = mapped_column(Integer, default=0)
    amount_ttc: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    file_key: Mapped[str] = mapped_column(String, default="")         # the signed PDF
    file_name: Mapped[str] = mapped_column(String, default="")
    subscription_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cancelled_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=clock.utcnow)


class Transfer(db.Base):
    __tablename__ = "transfers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    contract_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    amount: Mapped[int] = mapped_column(Integer)                       # received, VAT included
    paid_on: Mapped[dt.date] = mapped_column(Date, index=True)
    bank: Mapped[str] = mapped_column(String, default="")
    bank_ref: Mapped[str] = mapped_column(String, default="")
    proof_key: Mapped[str] = mapped_column(String, default="")
    proof_name: Mapped[str] = mapped_column(String, default="")
    invoice_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    recorded_by: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=clock.utcnow)


# ---------------- reading ----------------
def _transfer_dict(t: Transfer) -> dict:
    return {"id": t.id, "org_id": t.org_id, "contract_id": t.contract_id, "amount": t.amount,
            "paid_on": t.paid_on.isoformat(), "bank": t.bank, "bank_ref": t.bank_ref,
            "has_proof": bool(t.proof_key), "proof_name": t.proof_name, "invoice_id": t.invoice_id,
            "recorded_by": t.recorded_by, "created_at": t.created_at.isoformat()}


def _status(c: Contract, received: int) -> str:
    if c.cancelled_at:
        return "cancelled"
    if c.subscription_id is None:
        return "awaiting_payment"
    today = dt.date.today()
    if c.ends_on < today:
        return "ended"
    if c.starts_on > today:
        return "upcoming"
    return "active"


def _contract_dict(c: Contract, transfers: List[Transfer], org_name: str = "") -> dict:
    received = sum(t.amount for t in transfers)
    plan = billing.get_plan(c.plan_code) or {}
    return {"id": c.id, "number": c.number, "org_id": c.org_id, "org_name": org_name,
            "plan_code": c.plan_code, "plan_name_ar": plan.get("name_ar", c.plan_code),
            "plan_name_fr": plan.get("name_fr", c.plan_code), "seats": c.seats,
            "starts_on": c.starts_on.isoformat(), "ends_on": c.ends_on.isoformat(),
            "days_left": (c.ends_on - dt.date.today()).days,
            "amount_ht": c.amount_ht, "vat_rate": c.vat_rate, "vat": c.vat, "amount_ttc": c.amount_ttc,
            "received": received, "balance": max(0, c.amount_ttc - received),
            "status": _status(c, received), "notes": c.notes, "has_file": bool(c.file_key),
            "file_name": c.file_name, "created_by": c.created_by, "created_at": c.created_at.isoformat(),
            "transfers": [_transfer_dict(t) for t in sorted(transfers, key=lambda t: t.paid_on)]}


def _by_contract(transfers: List[Transfer]) -> dict:
    out: dict = {}
    for t in transfers:
        out.setdefault(t.contract_id, []).append(t)
    return out


def contracts_for(org_id: int) -> List[dict]:
    with db.session() as s:
        rows = list(s.scalars(select(Contract).where(Contract.org_id == org_id).order_by(Contract.starts_on.desc())))
        ts = list(s.scalars(select(Transfer).where(Transfer.org_id == org_id)))
    by_c = _by_contract(ts)
    out = [_contract_dict(c, by_c.get(c.id, [])) for c in rows]
    loose = [t for t in ts if t.contract_id is None]
    if loose:      # money received but not tied to a contract: still shown, never lost
        out.append({"id": None, "number": "", "status": "unassigned", "transfers": [_transfer_dict(t) for t in loose],
                    "received": sum(t.amount for t in loose), "amount_ttc": 0, "balance": 0})
    return out


def current_contracts(org_ids: List[int]) -> dict:
    """{org_id: the contract running today, else the latest one} for a list of clients."""
    if not org_ids:
        return {}
    today = dt.date.today()
    with db.session() as s:
        rows = list(s.scalars(select(Contract).where(Contract.org_id.in_(org_ids), Contract.cancelled_at.is_(None))))
        ts = list(s.scalars(select(Transfer).where(Transfer.org_id.in_(org_ids))))
    out: dict = {}
    for c in rows:
        live = c.subscription_id is not None and c.starts_on <= today <= c.ends_on
        best = out.get(c.org_id)
        key = (live, c.ends_on)
        if best is None or key > best[0]:
            out[c.org_id] = (key, c)
    by_c = _by_contract(ts)
    return {o: _contract_dict(c, by_c.get(c.id, [])) for o, (_, c) in out.items()}


def money_by_org() -> dict:
    """{org_id: (paid, still owed)} in centimes, from transfers and contracts -- and from
    any invoice made before contracts existed, so no money ever drops out of sight."""
    with db.session() as s:
        transfers = list(s.execute(select(Transfer.org_id, Transfer.contract_id, Transfer.amount, Transfer.invoice_id)).all())
        contracts = list(s.execute(select(Contract.id, Contract.org_id, Contract.amount_ttc)
                                   .where(Contract.cancelled_at.is_(None))).all())
    from_transfers = {inv for *_, inv in transfers if inv}
    paid: dict = {}
    by_contract: dict = {}
    for org, cid, amount, _ in transfers:
        paid[org] = paid.get(org, 0) + amount
        if cid:
            by_contract[cid] = by_contract.get(cid, 0) + amount
    owed: dict = {}
    for cid, org, ttc in contracts:
        owed[org] = owed.get(org, 0) + max(0, ttc - by_contract.get(cid, 0))
    for i in billing.list_invoices():
        if i["id"] in from_transfers:
            continue                       # already counted as the transfer it came from
        paid[i["org_id"]] = paid.get(i["org_id"], 0) + i["paid"]
        if i["status"] in ("sent", "overdue"):
            owed[i["org_id"]] = owed.get(i["org_id"], 0) + i["balance"]
    return {o: (int(paid.get(o, 0)), int(owed.get(o, 0))) for o in set(paid) | set(owed)}


def received_since(day: dt.date) -> int:
    """Centimes received from `day` on: transfers, and payments on invoices made before
    contracts existed -- counted the way money_by_org counts them, so the figures agree."""
    with db.session() as s:
        transfers = s.scalar(select(func.sum(Transfer.amount)).where(Transfer.paid_on >= day)) or 0
        from_transfers = select(Transfer.invoice_id).where(Transfer.invoice_id.is_not(None))
        older = s.scalar(select(func.sum(billing.Payment.amount)).where(
            billing.Payment.paid_on >= day, billing.Payment.invoice_id.not_in(from_transfers))) or 0
    return int(transfers) + int(older)


# ---------------- writing ----------------
def _number(s) -> str:
    prefix = f"C-{dt.date.today().year}-"
    last = s.scalar(select(func.max(Contract.number)).where(Contract.number.like(prefix + "%")))
    return f"{prefix}{(int(last.rsplit('-', 1)[1]) + 1) if last else 1:04d}"


def create_contract(org_id: int, data: dict, actor: str) -> dict:
    plan = billing.get_plan(data.get("plan_code") or "")
    if not plan:
        raise HTTPException(status_code=400, detail="Unknown plan")
    start = _date(data.get("starts_on")) or dt.date.today()
    end = _date(data.get("ends_on")) or (start + dt.timedelta(days=364))
    if end < start:
        raise HTTPException(status_code=400, detail="The contract ends before it starts")
    ht = int(data.get("amount_ht") or 0)
    if ht < 0:
        raise HTTPException(status_code=400, detail="The price cannot be negative")
    rate = int(data.get("vat_rate", 2000))
    vat = round(ht * rate / 10000)
    for _ in range(5):
        with db.session() as s:
            c = Contract(number=_number(s), org_id=org_id, plan_code=plan["code"],
                         seats=int(data.get("seats") or plan["seats"]), starts_on=start, ends_on=end,
                         amount_ht=ht, vat_rate=rate, vat=vat, amount_ttc=ht + vat,
                         notes=(data.get("notes") or "")[:2000], created_by=actor)
            s.add(c)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                continue
            cid, number = c.id, c.number
        db.add_audit(actor, "contract", "organization", str(org_id), new=number)
        return {"id": cid, "number": number}
    raise HTTPException(status_code=409, detail="Could not number the contract; try again")


def _activate(s, c: Contract, actor: str) -> None:
    """The first transfer opens the access, over the contract's dates exactly."""
    if c.subscription_id is not None or c.cancelled_at:
        return
    days = (c.ends_on - c.starts_on).days + 1
    months = max(1, round(days / 30.4))
    sub = billing.start_subscription(c.org_id, c.plan_code, status="active", days=days, starts_on=c.starts_on,
                                     seats=c.seats, actor=actor, session=s, monthly=c.amount_ht // months)
    c.subscription_id = sub["id"]
    o = s.get(accounts.Organization, c.org_id)
    if o:
        o.status = "customer"


def record_transfer(org_id: int, contract_id: Optional[int], data: dict, actor: str) -> dict:
    amount = int(data.get("amount") or 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="The amount must be positive")
    with db.session() as s:
        c = None
        if contract_id:
            c = s.get(Contract, contract_id)
            if not c or c.org_id != org_id:
                raise HTTPException(status_code=404, detail="Contract not found")
            if c.cancelled_at:
                raise HTTPException(status_code=409, detail="This contract is cancelled")
        t = Transfer(org_id=org_id, contract_id=contract_id, amount=amount,
                     paid_on=_date(data.get("paid_on")) or dt.date.today(),
                     bank=(data.get("bank") or "")[:80], bank_ref=(data.get("bank_ref") or "")[:120],
                     recorded_by=actor)
        s.add(t)
        if c:
            _activate(s, c, actor)
        s.commit()
        out = _transfer_dict(t)
    db.add_audit(actor, "transfer", "organization", str(org_id),
                 new=f"{amount / 100:.2f} MAD {out['bank_ref']}".strip())
    return out


def _date(v) -> Optional[dt.date]:
    if not v:
        return None
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Bad date: {v}")


def _store_file(prefix: str, org_id: int, upload: UploadFile, data: bytes) -> tuple:
    from storage import STORE
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="15 MB at most")
    name = re.sub(r"[^\w.\- ]+", "_", upload.filename or "document")[:120]
    ext = re.sub(r"[^a-z0-9]", "", (name.rsplit(".", 1)[-1] if "." in name else "").lower())[:8]
    key = f"{prefix}-{org_id}-{uuid.uuid4().hex}" + (f".{ext}" if ext else "")
    STORE.put(key, data)
    return key, name


def _send_file(key: str, name: str) -> StreamingResponse:
    from urllib.parse import quote
    from storage import STORE
    if not key or not STORE.exists(key):
        raise HTTPException(status_code=404, detail="No file")
    plain = name.encode("ascii", "replace").decode().replace("?", "_").replace('"', "")
    media = "application/pdf" if name.lower().endswith(".pdf") else "application/octet-stream"
    return StreamingResponse(io.BytesIO(STORE.get(key)), media_type=media, headers={
        "Content-Disposition": f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(name)}"})


# ---------------- routes ----------------
router = APIRouter()


class OrgIn(BaseModel):
    name: str
    kind: str = "individual"       # individual | firm | company | institution
    ice: str = ""
    address: str = ""
    city: str = ""
    phone: str = ""
    email: str = ""
    language: str = "ar"


class ContractIn(BaseModel):
    plan_code: str
    seats: Optional[int] = None
    starts_on: Optional[str] = None
    ends_on: Optional[str] = None
    amount_ht: int = 0
    vat_rate: int = 2000
    notes: str = ""


class TransferIn(BaseModel):
    amount: int
    paid_on: Optional[str] = None
    bank: str = ""
    bank_ref: str = ""


class AccountIn(BaseModel):
    email: str
    role: str = "client"


class NewClient(BaseModel):
    org: OrgIn
    contract: ContractIn
    transfer: Optional[TransferIn] = None
    accounts: List[AccountIn] = []
    lead_id: Optional[int] = None     # the public request this client came from, if any


@router.post("/api/crm/clients")
def new_client(body: NewClient, user: dict = Depends(require_sales)) -> dict:
    """The whole arrival of a client in one step: who they are, the contract, the
    transfer if it has come in, and the accounts to create."""
    if not body.org.name.strip():
        raise HTTPException(status_code=400, detail="Name required")
    emails = [a.email.strip().lower() for a in body.accounts if a.email.strip()]
    for e in emails:
        if "@" not in e:
            raise HTTPException(status_code=400, detail=f"Bad email: {e}")
        if db.get_user(e):
            raise HTTPException(status_code=409, detail=f"{e} already has an account")
    if len(set(emails)) != len(emails):
        raise HTTPException(status_code=400, detail="The same email twice")
    plan = billing.get_plan(body.contract.plan_code)
    if not plan:
        raise HTTPException(status_code=400, detail="Unknown plan")
    if len(emails) > (body.contract.seats or plan["seats"]):
        raise HTTPException(status_code=400, detail="More accounts than the contract allows")
    org = accounts.create_org({**body.org.model_dump(), "status": "prospect"}, user["email"])
    contract = create_contract(org["id"], body.contract.model_dump(), user["email"])
    transfer = None
    if body.transfer and body.transfer.amount > 0:
        transfer = record_transfer(org["id"], contract["id"], body.transfer.model_dump(), user["email"])
    invited = []
    for a in body.accounts:
        if a.email.strip():
            invited.append(accounts.invite(org["id"], a.email, a.role if a.role in ("client", "client_admin") else "client",
                                           user, body.org.language)["email"])
    if body.lead_id:                   # the request is converted only once the client exists
        import crm
        with db.session() as s:
            lead = s.get(crm.Lead, body.lead_id)
            if lead and not lead.deleted_at:
                lead.status, lead.org_id = "converted", org["id"]
                s.commit()
    # a contract starting later is paid but not open yet: say what is true today
    return {"org_id": org["id"], "contract": contract, "transfer": transfer, "invited": invited,
            "active": billing.access_state(org["id"]) == "ok"}


@router.get("/api/crm/contracts")
def all_contracts(status: str = "", _: dict = Depends(require_sales)) -> list:
    with db.session() as s:
        rows = list(s.execute(select(Contract, accounts.Organization.name)
                              .join(accounts.Organization, accounts.Organization.id == Contract.org_id)
                              .order_by(Contract.ends_on.desc())).all())
        ts = list(s.scalars(select(Transfer)))
    by_c = _by_contract(ts)
    out = [_contract_dict(c, by_c.get(c.id, []), name) for c, name in rows]
    if status == "ending":
        return [c for c in out if c["status"] == "active" and c["days_left"] <= 30]
    if status == "owing":
        return [c for c in out if c["balance"] > 0 and c["status"] != "cancelled"]
    return [c for c in out if not status or c["status"] == status]


@router.get("/api/crm/transfers")
def all_transfers(_: dict = Depends(require_sales)) -> list:
    with db.session() as s:
        rows = list(s.execute(select(Transfer, accounts.Organization.name, Contract.number)
                              .join(accounts.Organization, accounts.Organization.id == Transfer.org_id)
                              .outerjoin(Contract, Contract.id == Transfer.contract_id)
                              .order_by(Transfer.paid_on.desc(), Transfer.id.desc()).limit(2000)).all())
    return [{**_transfer_dict(t), "org_name": name, "contract_number": number or ""} for t, name, number in rows]


@router.post("/api/crm/orgs/{org_id}/contracts")
def add_contract(org_id: int, body: ContractIn, user: dict = Depends(require_sales)) -> dict:
    """A new contract or a renewal: by default it starts the day after the current one ends."""
    if not accounts.get_org(org_id):
        raise HTTPException(status_code=404, detail="Client not found")
    data = body.model_dump()
    if not data.get("starts_on"):
        cur = current_contracts([org_id]).get(org_id)
        if cur and cur["status"] in ("active", "upcoming"):
            start = dt.date.fromisoformat(cur["ends_on"]) + dt.timedelta(days=1)
            data["starts_on"] = start.isoformat()
            if not data.get("ends_on"):
                data["ends_on"] = (start + dt.timedelta(days=364)).isoformat()
    return create_contract(org_id, data, user["email"])


class ContractPatch(BaseModel):
    notes: Optional[str] = None
    cancel: bool = False


@router.patch("/api/crm/contracts/{contract_id}")
def change_contract(contract_id: int, body: ContractPatch, user: dict = Depends(require_sales)) -> dict:
    with db.session() as s:
        c = s.get(Contract, contract_id)
        if not c:
            raise HTTPException(status_code=404, detail="Not found")
        if body.notes is not None:
            c.notes = body.notes[:2000]
        if body.cancel:
            if s.scalar(select(func.count()).select_from(Transfer).where(Transfer.contract_id == contract_id)):
                raise HTTPException(status_code=409, detail="Money was received on this contract: it cannot be cancelled")
            c.cancelled_at = clock.utcnow()
        s.commit()
        org_id, number = c.org_id, c.number
    if body.cancel:
        db.add_audit(user["email"], "cancel", "contract", number)
    return next(x for x in contracts_for(org_id) if x.get("id") == contract_id)


@router.post("/api/crm/contracts/{contract_id}/transfers")
def add_transfer(contract_id: int, body: TransferIn, user: dict = Depends(require_sales)) -> dict:
    with db.session() as s:
        c = s.get(Contract, contract_id)
        if not c:
            raise HTTPException(status_code=404, detail="Not found")
        org_id = c.org_id
    return record_transfer(org_id, contract_id, body.model_dump(), user["email"])


@router.post("/api/crm/contracts/{contract_id}/file")
async def contract_file_upload(contract_id: int, file: UploadFile = File(...), user: dict = Depends(require_sales)) -> dict:
    data = await file.read()
    with db.session() as s:
        c = s.get(Contract, contract_id)
        if not c:
            raise HTTPException(status_code=404, detail="Not found")
        c.file_key, c.file_name = _store_file("contract", c.org_id, file, data)
        s.commit()
        number = c.number
    db.add_audit(user["email"], "contract_file", "contract", number)
    return {"ok": True}


@router.get("/api/crm/contracts/{contract_id}/file")
def contract_file(contract_id: int, _: dict = Depends(require_sales)) -> StreamingResponse:
    with db.session() as s:
        c = s.get(Contract, contract_id)
        if not c:
            raise HTTPException(status_code=404, detail="Not found")
        return _send_file(c.file_key, c.file_name or f"{c.number}.pdf")


@router.post("/api/crm/transfers/{transfer_id}/proof")
async def proof_upload(transfer_id: int, file: UploadFile = File(...), user: dict = Depends(require_sales)) -> dict:
    data = await file.read()
    with db.session() as s:
        t = s.get(Transfer, transfer_id)
        if not t:
            raise HTTPException(status_code=404, detail="Not found")
        t.proof_key, t.proof_name = _store_file("transfer", t.org_id, file, data)
        s.commit()
    return {"ok": True}


@router.get("/api/crm/transfers/{transfer_id}/proof")
def proof(transfer_id: int, _: dict = Depends(require_sales)) -> StreamingResponse:
    with db.session() as s:
        t = s.get(Transfer, transfer_id)
        if not t:
            raise HTTPException(status_code=404, detail="Not found")
        return _send_file(t.proof_key, t.proof_name or f"virement-{t.id}")


@router.post("/api/crm/transfers/{transfer_id}/invoice")
def invoice_from_transfer(transfer_id: int, user: dict = Depends(require_sales)) -> dict:
    """An invoice for a client who asks for one: made from the transfer, already paid."""
    with db.session() as s:
        t = s.get(Transfer, transfer_id)
        if not t:
            raise HTTPException(status_code=404, detail="Not found")
        if t.invoice_id:
            return {"invoice_id": t.invoice_id}
        c = s.get(Contract, t.contract_id) if t.contract_id else None
        rate = c.vat_rate if c else 2000
        ht = round(t.amount * 10000 / (10000 + rate))
        desc = f"{c.number} — {c.plan_code}, {c.starts_on.isoformat()} → {c.ends_on.isoformat()}" if c else "Abonnement"
        org_id, amount, paid_on, ref = t.org_id, t.amount, t.paid_on, t.bank_ref
    inv = billing.create_invoice(org_id, ht, desc, user["email"], vat_rate=rate, due_days=0)
    # Splitting a received amount into price and VAT can leave a centime either way: the
    # invoice is paid by this transfer, so it is settled at its own total.
    settled = inv["amount_ttc"] if abs(inv["amount_ttc"] - amount) <= 1 else amount
    billing.record_payment(inv["id"], settled, "transfer", ref, paid_on, user["email"])
    with db.session() as s:
        s.get(Transfer, transfer_id).invoice_id = inv["id"]
        s.commit()
    return {"invoice_id": inv["id"], "number": inv["number"]}
