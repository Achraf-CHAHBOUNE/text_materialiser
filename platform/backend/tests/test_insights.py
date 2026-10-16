"""The admin's view of the readers: what each one reads, downloads and searches, what
they pay, from where -- visible to us, never to the readers.

Env matches the other test modules: whichever is imported first configures the app.
"""
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

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import accounts  # noqa: E402
import auth as authmod  # noqa: E402
import billing  # noqa: E402
import db  # noqa: E402
import server  # noqa: E402
import storage  # noqa: E402
import textnorm  # noqa: E402

server._startup()
client = TestClient(server.app)
PW = "a-long-password"


def _login(email, pw=PW):
    r = client.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def reader():
    from docx import Document
    d = Document()
    d.add_paragraph("وحيث إن عقد الكراء صحيح")
    b = io.BytesIO()
    d.save(b)
    storage.STORE.put("ins_001.docx", b.getvalue())
    with db.session() as s:
        s.merge(db.Decision(doc_id="ins_001", category="تجارية", decision_no="501", decision_date="02/03/2021",
                            state="published", file_name="ins_001.docx", body_text="وحيث إن عقد الكراء صحيح",
                            search_text=textnorm.normalize("وحيث إن عقد الكراء صحيح"), sort_key="20210302000501"))
        s.commit()
    org = accounts.create_org({"name": "Cabinet Lecteur"}, "test")
    billing.start_subscription(org["id"], "firm", status="active", days=365, actor="test")
    inv = billing.create_invoice(org["id"], 149900, "Cabinet, 1 mois", "test")
    billing.record_payment(inv["id"], 100000, "transfer", "VIR-1", None, "test")
    db.upsert_user("lecteur@cab.ma", authmod.hash_password(PW), role="client")
    with db.session() as s:
        u = s.scalar(db.select(db.User).where(db.User.email == "lecteur@cab.ma"))
        u.org_id = org["id"]
        s.commit()
    h = _login("lecteur@cab.ma")
    client.get("/api/decisions/ins_001", headers=h)
    client.get("/api/decisions/ins_001", headers=h)
    client.get("/api/decisions/ins_001/file", headers=h)
    client.get("/api/browse/rulings?q=الكراء", headers=h)
    client.get("/api/browse/rulings?q=zzzintrouvable", headers=h)
    return {"h": h, "org": org["id"]}


def admin():
    return _login("admin@x.com", "admin-pass")


def test_every_reader_is_listed_with_money_and_use(reader):
    rows = client.get("/api/crm/users", headers=admin()).json()
    me = next(r for r in rows if r["email"] == "lecteur@cab.ma")
    assert me["reads_30d"] == 2 and me["downloads_30d"] == 1 and me["searches_30d"] == 2
    assert me["logins_30d"] == 1 and me["org_name"] == "Cabinet Lecteur" and me["plan"] == "firm"
    assert me["org_paid"] == 100000 and me["org_owed"] == 179880 - 100000
    assert me["sessions"] == 1


def test_one_reader_in_full(reader):
    d = client.get("/api/crm/users/lecteur@cab.ma", headers=admin()).json()
    assert d["totals"]["view"] == 2 and d["totals"]["search_empty"] == 1
    read = [t for t in d["timeline"] if t["action"] == "view"]
    assert read[0]["decision_no"] == "501" and read[0]["chamber"] == "تجارية"
    assert d["downloads"][0]["decision_no"] == "501" and d["downloads"][0]["ref"]
    assert d["chambers"] == [{"chamber": "تجارية", "count": 2}]
    assert d["money"]["paid"] == 100000 and len(d["money"]["invoices"]) == 1
    assert d["sessions"][0]["ended"] == ""


def test_the_platform_usage_shows_what_is_read_and_what_is_missing(reader):
    u = client.get("/api/crm/usage?days=30", headers=admin()).json()
    assert u["active_readers"] >= 1
    assert u["top_read"][0]["doc_id"] == "ins_001" and u["top_read"][0]["readers"] == 1
    assert {"query": "zzzintrouvable", "count": 1} == {k: u["empty_searches"][0][k] for k in ("query", "count")}
    assert u["top_searches"][0]["query"] == "الكراء"


def test_a_reader_can_be_signed_out_everywhere(reader):
    out = client.post("/api/crm/users/lecteur@cab.ma/logout", headers=admin()).json()
    assert out["ended"] == 1
    assert client.get("/api/account", headers=reader["h"]).status_code == 401


def test_readers_never_see_this(reader):
    h = _login("lecteur@cab.ma")
    for path in ("/api/crm/users", "/api/crm/users/lecteur@cab.ma", "/api/crm/usage", "/api/crm/activity/export"):
        assert client.get(path, headers=h).status_code == 403, path


def test_the_activity_exports_for_excel(reader):
    r = client.get("/api/crm/activity/export?email=lecteur@cab.ma", headers=admin())
    text = r.content.decode("utf-8-sig")
    assert r.status_code == 200 and "lecteur@cab.ma,view,ins_001,501" in text


def test_a_file_found_circulating_leads_back_to_who_took_it(reader):
    d = client.get("/api/crm/users/lecteur@cab.ma", headers=admin()).json()
    ref = d["downloads"][0]["ref"]
    found = client.get(f"/api/crm/downloads/{ref.lower()}", headers=admin()).json()
    assert found["email"] == "lecteur@cab.ma" and found["decision_no"] == "501" and found["org"] == "Cabinet Lecteur"
    assert client.get("/api/crm/downloads/NOPE", headers=admin()).status_code == 404


def test_reading_time_tells_a_read_from_a_click(reader):
    h = _login("lecteur@cab.ma")
    for _ in range(3):
        client.post("/api/decisions/ins_001/reading", headers=h, json={"seconds": 30, "lang": "fr"})
    client.post("/api/decisions/ins_001/reading", headers=h, json={"seconds": 5000, "lang": "ar"})   # capped at 60
    d = client.get("/api/crm/users/lecteur@cab.ma", headers=admin()).json()
    assert d["reading"]["minutes"] == 2 and d["reading"]["french_share"] == 60
    assert d["reading"]["longest"][0]["doc_id"] == "ins_001"


def test_notes_and_emails_stay_on_the_reader(reader):
    client.post("/api/crm/users/lecteur@cab.ma/notes", headers=admin(), json={"body": "Appelé : renouvelle en janvier"})
    client.post("/api/crm/users/lecteur@cab.ma/email", headers=admin(), json={"subject": "Bienvenue", "body": "Bonjour"})
    notes = client.get("/api/crm/users/lecteur@cab.ma", headers=admin()).json()["notes"]
    assert {n["body"].split("\n")[0] for n in notes} == {"Appelé : renouvelle en janvier", "✉ Bienvenue"}
    out = client.get("/api/admin/outbox", headers=admin()).json()
    assert any(m["to"] == "lecteur@cab.ma" and m["subject"] == "Bienvenue" for m in out)


def test_an_account_used_from_three_addresses_in_a_day_is_flagged(reader):
    for ip in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
        client.post("/api/auth/login", json={"email": "lecteur@cab.ma", "password": PW},
                    headers={"x-forwarded-for": ip})
    al = client.get("/api/crm/alerts", headers=admin()).json()
    shared = [a for a in al if a["kind"] == "shared_ips" and a["email"] == "lecteur@cab.ma"]
    assert shared and shared[0]["level"] == "high" and shared[0]["count"] >= 3
    assert al[0]["level"] == "high"                                              # the serious first
