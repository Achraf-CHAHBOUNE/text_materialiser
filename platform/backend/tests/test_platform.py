"""Platform tests (website_brief §6): permissions, the anonymized-only boundary,
import gate, publication workflow, Arabic search, immediate suspension.

Env is set BEFORE importing the app so the DB engine + admin seed use a temp location.
"""
import io
import json
import os
import tempfile
import zipfile

_tmp = tempfile.mkdtemp()
os.environ.update(
    DB_DIR=_tmp, FILESTORE_DIR=os.path.join(_tmp, "files"),
    AUTH_SECRET="test-secret", SEED_EMAIL="admin@x.com", SEED_PASSWORD="admin-pass",
)
os.environ.pop("DATABASE_URL", None)
os.environ.pop("MINIO_ENDPOINT", None)

from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402

server._startup()  # create tables + seed admin (startup event doesn't fire without a lifespan ctx)
client = TestClient(server.app)


# ---------- helpers ----------
def _docx(text: str) -> bytes:
    from docx import Document
    d = Document()
    for line in text.split("\n"):
        d.add_paragraph(line)
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()


def _record(doc_id: str, category="تجارية", level="نقض", links=None):
    return {
        "doc_id": doc_id, "anonymized_file": f"{doc_id}.docx",
        "source_file": f"{doc_id}.doc", "format": "docx",
        "fields": {"رقم القرار": {"value": "652"}, "رقم الملف": {"value": "1293/8222/2017"},
                   "تاريخ القرار": {"value": "2018-12-12"}},
        "category": {"value": category}, "level": level, "court": "محكمة النقض",
        "case_id": "C:1293/8222/2017", "links": links or [],
        "pii": {"removed_count": 2}, "review": "ok",
    }


def _zip(records, files) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("records.json", json.dumps(records, ensure_ascii=False))
        for name, data in files.items():
            z.writestr(name, data)
    return b.getvalue()


def _token(email, pw):
    r = client.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


ADMIN = None


def _admin():
    global ADMIN
    if ADMIN is None:
        ADMIN = _token("admin@x.com", "admin-pass")
    return ADMIN


# ---------- tests ----------
def test_admin_login_role():
    r = client.post("/api/auth/login", json={"email": "admin@x.com", "password": "admin-pass"})
    assert r.status_code == 200 and r.json()["role"] == "admin"


def test_import_gate_quarantines_pii():
    clean = _docx("محكمة النقض\nحكمت المحكمة على XXXXXXX بأداء المبلغ المحكوم به")
    dirty = _docx("المطلوب اتصل على الرقم 0612345678 لتسوية الملف")  # phone => PII pattern
    payload = _zip([_record("clean1"), _record("dirty1")],
                   {"clean1.docx": clean, "dirty1.docx": dirty})
    r = client.post("/api/admin/import", headers=_h(_admin()),
                    files={"file": ("batch.zip", payload, "application/zip")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == 1
    assert any(q["doc_id"] == "dirty1" for q in body["quarantined"])
    # the quarantined doc was NOT stored
    assert client.get("/api/admin/decisions/dirty1", headers=_h(_admin())).status_code == 404


def test_unauthenticated_blocked():
    assert client.get("/api/decisions").status_code == 401
    assert client.get("/api/admin/decisions").status_code == 401


def test_client_cannot_reach_admin():
    r = client.post("/api/admin/clients", headers=_h(_admin()),
                    json={"email": "c1@x.com", "password": "pw123456"})
    assert r.status_code == 200
    ctok = _token("c1@x.com", "pw123456")
    # every admin surface must be forbidden for a client
    assert client.get("/api/admin/decisions", headers=_h(ctok)).status_code == 403
    assert client.get("/api/admin/queue", headers=_h(ctok)).status_code == 403
    assert client.post("/api/admin/clients", headers=_h(ctok),
                       json={"email": "x@x.com", "password": "pw123456"}).status_code == 403


def test_publish_workflow_and_client_visibility():
    # import already put clean1 in "imported"; a client must not see it yet
    ctok = _token("c1@x.com", "pw123456")
    assert client.get("/api/decisions", headers=_h(ctok)).json() == []
    # publish it
    r = client.post("/api/admin/decisions/clean1/state", headers=_h(_admin()),
                    json={"state": "published"})
    assert r.status_code == 200 and r.json()["state"] == "published"
    got = client.get("/api/decisions", headers=_h(ctok)).json()
    assert [d["doc_id"] for d in got] == ["clean1"]


def test_no_client_gets_unpublished_document_by_any_route():
    ctok = _token("c1@x.com", "pw123456")
    # move clean1 back to review -> client loses access immediately, by every route
    client.post("/api/admin/decisions/clean1/state", headers=_h(_admin()),
                json={"state": "under_review"})
    assert client.get("/api/decisions/clean1", headers=_h(ctok)).status_code == 404
    assert client.get("/api/decisions/clean1/file", headers=_h(ctok)).status_code == 404
    assert client.get("/api/decisions", headers=_h(ctok)).json() == []
    # restore published for later tests
    client.post("/api/admin/decisions/clean1/state", headers=_h(_admin()),
                json={"state": "published"})


def test_arabic_search_variant_insensitive():
    # publish a decision whose body contains "الإدارية"; search a normalized variant
    body = _docx("قرار صادر عن الغرفة الإدارية بمحكمة النقض بشأن نزاع إداري")
    client.post("/api/admin/import", headers=_h(_admin()),
                files={"file": ("b.zip", _zip([_record("adm1", category="إدارية")],
                                              {"adm1.docx": body}), "application/zip")})
    client.post("/api/admin/decisions/adm1/state", headers=_h(_admin()),
                json={"state": "published"})
    ctok = _token("c1@x.com", "pw123456")
    # query with alef/ya variant + no diacritics
    r = client.get("/api/search", headers=_h(ctok), params={"q": "الاداريه"})
    hits = r.json()
    assert any(d["doc_id"] == "adm1" for d in hits)
    assert any(d.get("snippets") for d in hits)  # shows why it matched


def test_suspension_is_immediate():
    ctok = _token("c1@x.com", "pw123456")
    assert client.get("/api/decisions", headers=_h(ctok)).status_code == 200
    # admin suspends; the SAME existing token must stop working on the next request
    client.patch("/api/admin/clients/c1@x.com", headers=_h(_admin()),
                 json={"status": "suspended"})
    assert client.get("/api/decisions", headers=_h(ctok)).status_code == 403
    assert client.post("/api/auth/login",
                       json={"email": "c1@x.com", "password": "pw123456"}).status_code == 403


def test_audit_trail_records_corrections():
    client.patch("/api/admin/decisions/clean1", headers=_h(_admin()),
                 json={"changes": {"category": "مدنية"}})
    detail = client.get("/api/admin/decisions/clean1", headers=_h(_admin())).json()
    assert detail["category"] == "مدنية"
    assert any(a["field"] == "category" and a["new"] == "مدنية" for a in detail["audit"])
