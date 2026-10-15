"""The deeper CRM: our quotes and revenue, and a law firm's own cases.

The firm module holds real personal data, so most of what is tested here is that a
firm sees only itself, that our staff see nothing of it, and that erasing is real.

Env matches the other test modules: whichever is imported first configures the app.
"""
import datetime as dt
import io
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.update(
    DB_DIR=_tmp, FILESTORE_DIR=os.path.join(_tmp, "files"),
    AUTH_SECRET="test-secret", SEED_EMAIL="admin@x.com", SEED_PASSWORD="admin-pass",
    AUTO_PUBLISH="0",
)
os.environ.pop("DATABASE_URL", None)
os.environ.pop("SMTP_HOST", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

import accounts  # noqa: E402
import auth as authmod  # noqa: E402
import billing  # noqa: E402
import db  # noqa: E402
import practice  # noqa: E402
import server  # noqa: E402
import worker  # noqa: E402

server._startup()
db.init_db()
client = TestClient(server.app)
PW = "a-long-password"


def _login(email, pw=PW):
    r = client.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _person(email, role, org_id=None):
    if not db.get_user(email):
        db.upsert_user(email, authmod.hash_password(PW), role=role)
        if org_id:
            with db.session() as s:
                s.scalar(select(db.User).where(db.User.email == email)).org_id = org_id
                s.commit()
    return _login(email)


def _firm(name, plan="firm", status="active"):
    org = accounts.create_org({"name": name, "email": f"contact@{name.lower()}.ma", "language": "fr"}, "test")
    billing.start_subscription(org["id"], plan, status=status, days=365 if status == "active" else 14, actor="test")
    return org["id"]


@pytest.fixture(scope="module")
def sales():
    return _person("seller@x.com", "sales")


@pytest.fixture(scope="module")
def firms():
    # the module is off by default (readers have a reading space only): on for this plan
    with db.session() as s:
        s.get(billing.Plan, "firm").practice = True
        s.commit()
    a, b = _firm("Alpha"), _firm("Beta")
    return {"a": a, "b": b,
            "a_holder": _person("boss@alpha.ma", "client_admin", a),
            "a_clerk": _person("clerk@alpha.ma", "client", a),
            "b_holder": _person("boss@beta.ma", "client_admin", b)}


# ------------------------------------------------------------------ our sales
def test_an_accepted_quote_becomes_subscription_invoice_and_a_won_deal(sales):
    org = _firm("Gamma")
    client.post(f"/api/crm/orgs/{org}/opportunities", headers=sales, json={"title": "Gamma", "stage": "demo"})
    q = client.post(f"/api/crm/orgs/{org}/quotes", headers=sales,
                    json={"plan_code": "firm", "months": 12, "seats": 8}).json()
    assert q["number"].startswith(f"D-{dt.date.today().year}-") and q["amount_ht"] == 149900 * 12
    assert client.post(f"/api/crm/quotes/{q['id']}/send", headers=sales).json()["status"] == "sent"
    out = client.post(f"/api/crm/quotes/{q['id']}/accept", headers=sales).json()
    assert out["invoice"]["amount_ht"] == 149900 * 12 and out["quote"]["status"] == "accepted"
    detail = client.get(f"/api/crm/orgs/{org}", headers=sales).json()
    assert detail["status"] == "customer"
    assert [o["stage"] for o in detail["opportunities"]] == ["won"]
    subs = client.get(f"/api/crm/orgs/{org}/subscriptions", headers=sales).json()
    assert subs[0]["seats"] == 8 and subs[0]["monthly_price"] == 149900
    # twice is refused: one quote, one invoice
    assert client.post(f"/api/crm/quotes/{q['id']}/accept", headers=sales).status_code == 409


def test_a_negotiated_price_drives_the_mrr(sales):
    org = _firm("Delta", plan="trial", status="trial")  # on trial, then a quoted plan with no list price
    q = client.post(f"/api/crm/orgs/{org}/quotes", headers=sales, json={
        "plan_code": "institution", "months": 12,
        "lines": [{"label": "Université — 40 accès", "qty": 12, "unit_price": 500000}]}).json()
    client.post(f"/api/crm/quotes/{q['id']}/accept", headers=sales)
    r = client.get("/api/crm/reports", headers=sales).json()
    assert r["mrr"] >= 500000 and r["arr"] == r["mrr"] * 12
    assert len(r["revenue"]) == 12 and len(r["new_customers"]) == 12


def test_an_email_from_the_crm_is_sent_and_kept_in_the_history(sales):
    org = _firm("Epsilon")
    client.post(f"/api/crm/orgs/{org}/email", headers=sales,
                json={"to": "dg@epsilon.ma", "subject": "Votre essai", "body": "Bonjour"})
    acts = client.get(f"/api/crm/orgs/{org}", headers=sales).json()["activities"]
    assert acts[0]["kind"] == "email" and "dg@epsilon.ma" in acts[0]["body"]
    out = client.get("/api/admin/outbox", headers=_login("admin@x.com", "admin-pass")).json()
    assert any(m["to"] == "dg@epsilon.ma" and m["subject"] == "Votre essai" for m in out)


def test_a_list_imported_twice_creates_each_lead_once(sales):
    data = "full_name;email;company\nMaître A;a@cab.ma;Cab A\nMaître B;b@cab.ma;Cab B\n".encode("utf-8-sig")
    first = client.post("/api/crm/import/leads", headers=sales, files={"file": ("l.csv", data, "text/csv")}).json()
    again = client.post("/api/crm/import/leads", headers=sales, files={"file": ("l.csv", data, "text/csv")}).json()
    assert first == {"created": 2, "skipped": 0} and again == {"created": 0, "skipped": 2}
    dup = client.get("/api/crm/duplicates?email=a@cab.ma", headers=sales).json()
    assert [l["email"] for l in dup["leads"]] == ["a@cab.ma"]
    csv_ = client.get("/api/crm/export/leads", headers=sales)
    assert csv_.status_code == 200 and "a@cab.ma" in csv_.content.decode("utf-8-sig")


# ------------------------------------------------------------------ a firm's cases
def test_a_firm_sees_only_itself_and_our_staff_see_nothing(firms, sales):
    c = client.post("/api/practice/clients", headers=firms["a_holder"],
                    json={"full_name": "Client Confidentiel", "cin": "AB123456"}).json()
    m = client.post("/api/practice/matters", headers=firms["a_holder"],
                    json={"title": "Bail commercial", "client_id": c["id"], "level": "ابتدائي"}).json()
    assert m["reference"] == f"{dt.date.today().year}/0001"
    # the colleague sees it, the other firm and our staff do not
    assert client.get(f"/api/practice/matters/{m['id']}", headers=firms["a_clerk"]).status_code == 200
    assert client.get(f"/api/practice/matters/{m['id']}", headers=firms["b_holder"]).status_code == 404
    assert client.get("/api/practice/clients", headers=firms["b_holder"]).json() == []
    for staff in (sales, _login("admin@x.com", "admin-pass")):
        r = client.get("/api/practice/clients", headers=staff)
        assert r.status_code == 403 and r.json()["detail"] == {"practice": "members only"}
    # nor can the other firm attach its own case to our client
    r = client.post("/api/practice/matters", headers=firms["b_holder"], json={"title": "x", "client_id": c["id"]})
    assert r.status_code == 404
    # the audit trail keeps ids, never the client's name
    trail = " ".join(f"{a['new']} {a['old']}" for a in db.audit_for(f"{firms['a']}:{c['id']}"))
    assert "Confidentiel" not in trail and "AB123456" not in trail


def test_a_plan_without_the_module_keeps_it_closed(firms):
    with db.session() as s:
        s.get(billing.Plan, "individual").practice = False
        s.commit()
    solo = _firm("Solo", plan="individual")
    h = _person("solo@solo.ma", "client_admin", solo)
    assert client.get("/api/practice/dashboard", headers=h).json()["detail"] == {"practice": "not in plan"}


def test_deadlines_skip_the_weekend_and_wait_to_be_verified(firms):
    h = firms["a_holder"]
    m = client.post("/api/practice/matters", headers=h, json={"title": "Appel"}).json()
    friday = dt.date(2026, 10, 9)                       # +30 days lands on a Sunday
    d = client.post(f"/api/practice/matters/{m['id']}/deadlines", headers=h,
                    json={"kind": "appeal", "start_on": friday.isoformat()}).json()
    assert d["days"] == 30 and d["due_on"] == "2026-11-09" and d["verified_by"] == ""
    v = client.patch(f"/api/practice/deadlines/{d['id']}", headers=h, json={"verified": True}).json()
    assert v["verified_by"] == "boss@alpha.ma"


def test_a_hearing_outcome_can_set_the_next_one(firms):
    h = firms["a_holder"]
    m = client.post("/api/practice/matters", headers=h, json={"title": "Expulsion", "court": "TPI Rabat"}).json()
    first = client.post(f"/api/practice/matters/{m['id']}/hearings", headers=h,
                        json={"date": "2026-11-02", "purpose": "Première audience"}).json()
    out = client.patch(f"/api/practice/hearings/{first['id']}", headers=h,
                       json={"outcome": "Renvoi pour conclusions", "next_date": "2026-11-30"}).json()
    assert out["next"]["date"] == "2026-11-30" and out["next"]["court"] == "TPI Rabat"


def test_a_fee_note_bills_time_and_expenses_once(firms):
    h = firms["a_holder"]
    m = client.post("/api/practice/matters", headers=h, json={"title": "Recouvrement"}).json()
    client.post(f"/api/practice/matters/{m['id']}/time", headers=h,
                json={"minutes": 90, "rate": 80000, "description": "Rédaction"})
    client.post(f"/api/practice/matters/{m['id']}/expenses", headers=h, json={"label": "Huissier", "amount": 30000})
    fee = client.post("/api/practice/fees", headers=h, json={"matter_id": m["id"]}).json()
    assert fee["amount_ht"] == 120000 + 30000 and fee["vat"] == 15000            # 10% on lawyers' fees
    assert client.post("/api/practice/fees", headers=h, json={"matter_id": m["id"]}).status_code == 400
    assert client.get(f"/api/practice/matters/{m['id']}", headers=h).json()["unbilled"] == 0
    client.post(f"/api/practice/fees/{fee['id']}/cancel", headers=h)
    assert client.get(f"/api/practice/matters/{m['id']}", headers=h).json()["unbilled"] == 150000
    again = client.post("/api/practice/fees", headers=h, json={"matter_id": m["id"]}).json()
    paid = client.post(f"/api/practice/fees/{again['id']}/payments", headers=h,
                       json={"amount": again["amount_ttc"], "method": "cheque"}).json()
    assert paid["status"] == "paid" and paid["balance"] == 0


def test_a_ruling_tied_to_a_case_and_documents_kept_private(firms):
    h, other = firms["a_holder"], firms["b_holder"]
    with db.session() as s:
        s.merge(db.Decision(doc_id="pr_001", category="مدنية", state="published", decision_no="1",
                            decision_date="01/01/2020", body_text="نص", search_text="نص", rule="", abstract="ملخص"))
        s.commit()
    m = client.post("/api/practice/matters", headers=h, json={"title": "Jurisprudence"}).json()
    client.post(f"/api/practice/matters/{m['id']}/rulings", headers=h, json={"doc_id": "pr_001", "note": "à citer"})
    detail = client.get(f"/api/practice/matters/{m['id']}", headers=h).json()
    assert [r["doc_id"] for r in detail["rulings"]] == ["pr_001"]
    up = client.post(f"/api/practice/matters/{m['id']}/documents", headers=h,
                     files={"file": ("requête.pdf", b"%PDF-1.4 test", "application/pdf")}).json()
    assert client.get(f"/api/practice/documents/{up['id']}", headers=h).content == b"%PDF-1.4 test"
    assert client.get(f"/api/practice/documents/{up['id']}", headers=other).status_code == 404


def test_erasing_a_client_erases_everything_under_it(firms):
    h, clerk = firms["a_holder"], firms["a_clerk"]
    c = client.post("/api/practice/clients", headers=h, json={"full_name": "À effacer"}).json()
    m = client.post("/api/practice/matters", headers=h, json={"title": "Dossier", "client_id": c["id"]}).json()
    up = client.post(f"/api/practice/matters/{m['id']}/documents", headers=h,
                     files={"file": ("piece.txt", b"secret", "text/plain")}).json()
    with db.session() as s:
        key = s.get(practice.MatterDocument, up["id"]).file_key
    assert server.STORE.exists(key)
    assert client.delete(f"/api/practice/clients/{c['id']}", headers=clerk).status_code == 403
    out = client.delete(f"/api/practice/clients/{c['id']}", headers=h).json()
    assert out == {"ok": True, "matters": 1, "files": 1}
    assert not server.STORE.exists(key)
    assert client.get(f"/api/practice/matters/{m['id']}", headers=h).status_code == 404


def test_each_lawyer_gets_their_coming_hearings(firms):
    h = firms["a_holder"]
    m = client.post("/api/practice/matters", headers=h, json={"title": "Audience demain"}).json()
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    client.post(f"/api/practice/matters/{m['id']}/hearings", headers=h, json={"date": tomorrow.isoformat()})
    mine = [b for e, _, b in practice.digests(dt.date.today()) if e == "boss@alpha.ma"]
    assert mine and "Audience demain" in mine[0]
    assert worker.practice_digests(dt.date.today()) >= 1
    assert worker.practice_digests(dt.date.today()) == 0              # once a day
