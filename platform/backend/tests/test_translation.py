"""Reading a ruling in French: translated once, stored, and never anything but
already-anonymized text leaving the building.

Env matches the other test modules: whichever is imported first configures the app.
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
    AUTO_PUBLISH="0",
)
os.environ.pop("DATABASE_URL", None)
os.environ.pop("MINIO_ENDPOINT", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import db  # noqa: E402
import server  # noqa: E402
import translate  # noqa: E402

server._startup()
client = TestClient(server.app)

ARABIC = "محكمة النقض\nحضر السيد XXXXXXX بصفته محاميا\nوحيث إن الطلب مقبول شكلا"
FRENCH = "Cour de cassation\nXXXXXXX a comparu en qualité d'avocat\nAttendu que la demande est recevable"


@pytest.fixture(scope="module", autouse=True)
def _leave_no_trace():
    yield
    from sqlalchemy import delete, select
    with db.session() as s:
        ids = list(s.scalars(select(db.Decision.doc_id).where(db.Decision.doc_id.like("tr_%"))))
        for model in (db.Translation, db.Link):
            col = model.doc_id if hasattr(model, "doc_id") else model.parent_doc
            s.execute(delete(model).where(col.in_(ids)))
        s.execute(delete(db.Decision).where(db.Decision.doc_id.in_(ids)))
        s.commit()


def _docx(text):
    from docx import Document
    d = Document()
    for line in text.split("\n"):
        d.add_paragraph(line)
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()


def _token(email="admin@x.com", pw="admin-pass"):
    return client.post("/api/auth/login", json={"email": email, "password": pw}).json()["token"]


def _h():
    return {"Authorization": f"Bearer {_token()}"}


def _import(doc_id, text=ARABIC, publish=True):
    rec = {"doc_id": doc_id, "anonymized_file": f"{doc_id}.docx", "format": "docx",
           "fields": {"رقم القرار": {"value": "5"}, "تاريخ القرار": {"value": "01/01/2020"}},
           "category": {"value": "مدنية"}, "level": "نقض", "court": "محكمة النقض",
           "pii": {"removed_count": 1}, "review": "ok"}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("records.json", json.dumps([rec], ensure_ascii=False))
        z.writestr(f"{doc_id}.docx", _docx(text))
    client.post("/api/admin/import", headers=_h(),
                files={"file": ("b.zip", buf.getvalue(), "application/zip")})
    if publish:
        client.post(f"/api/admin/decisions/{doc_id}/state", headers=_h(), json={"state": "published"})


# ---------------------------------------------------------------- the engine alone
def test_a_long_ruling_is_split_on_paragraph_breaks():
    para = "و" * 1000
    text = "\n\n".join([para] * 20)                       # ~20,000 characters
    pieces = translate.split_for_translation(text, limit=6000)
    assert len(pieces) > 1
    assert all(len(p) <= 6000 for p in pieces)
    assert "".join(pieces).replace("\n", "") == text.replace("\n", "")   # nothing dropped


def test_one_paragraph_longer_than_the_limit_is_still_cut():
    text = "\n".join("سطر" * 50 for _ in range(400))      # one block, no blank lines
    pieces = translate.split_for_translation(text, limit=5000)
    assert all(len(p) <= 5000 for p in pieces)
    assert len(pieces) > 1


def test_every_piece_is_translated_and_joined_in_order():
    seen = []

    def fake(piece):
        seen.append(piece)
        return f"[fr]{piece[:8]}"

    text = "\n\n".join(["أ" * 5000, "ب" * 5000, "ج" * 5000])
    out = translate.translate(text, call=fake)
    assert len(seen) == 3
    assert out.count("[fr]") == 3
    assert out.index("[fr]أ") < out.index("[fr]ب") < out.index("[fr]ج")   # order kept


def test_an_empty_or_oversized_ruling_is_refused():
    with pytest.raises(translate.TranslationError, match="no text"):
        translate.translate("   ", call=lambda p: "x")
    with pytest.raises(translate.TranslationError, match="too long"):
        translate.translate("ا" * 200_000, call=lambda p: "x")


def test_without_a_key_it_says_so_instead_of_failing_obscurely(monkeypatch):
    monkeypatch.delenv("TRANSLATE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(translate.TranslationError, match="not configured"):
        translate.translate("نص")


# ---------------------------------------------------------------- through the API
def test_a_ruling_is_translated_once_and_then_served_from_store(monkeypatch):
    _import("tr_once")
    calls = []
    monkeypatch.setattr(translate, "translate", lambda text, **kw: (calls.append(text), FRENCH)[1])

    before = client.get("/api/decisions/tr_once/translation", headers=_h()).json()
    assert before["ready"] is False                      # nothing stored yet

    made = client.post("/api/decisions/tr_once/translation", headers=_h())
    assert made.status_code == 200 and made.json()["text"] == FRENCH
    assert len(calls) == 1
    assert "XXXXXXX" in calls[0], "only anonymized text may be sent out"

    again = client.post("/api/decisions/tr_once/translation", headers=_h())
    assert again.json()["text"] == FRENCH
    assert len(calls) == 1, "the second request must not pay for a second translation"

    stored = client.get("/api/decisions/tr_once/translation", headers=_h()).json()
    assert stored["ready"] is True and stored["text"] == FRENCH


def test_correcting_a_ruling_makes_its_translation_stale(monkeypatch):
    _import("tr_stale")
    monkeypatch.setattr(translate, "translate", lambda text, **kw: FRENCH)
    client.post("/api/decisions/tr_stale/translation", headers=_h())
    assert client.get("/api/decisions/tr_stale/translation", headers=_h()).json()["ready"] is True

    version = client.get("/api/admin/decisions/tr_stale", headers=_h()).json()["version"]
    client.post("/api/admin/decisions/tr_stale/hide", headers=_h(),
                json={"value": "محاميا", "base_version": version})

    after = client.get("/api/decisions/tr_stale/translation", headers=_h()).json()
    assert after["ready"] is False and after["stale"] is True, \
        "a French text of the old wording must not be shown for an edited ruling"


def test_a_failure_is_reported_and_nothing_is_stored(monkeypatch):
    _import("tr_fail")

    def boom(text, **kw):
        raise translate.TranslationError("the translation service is busy; try again in a minute")

    monkeypatch.setattr(translate, "translate", boom)
    r = client.post("/api/decisions/tr_fail/translation", headers=_h())
    assert r.status_code == 503 and "busy" in r.json()["detail"]
    assert client.get("/api/decisions/tr_fail/translation", headers=_h()).json()["ready"] is False


def test_an_unpublished_ruling_cannot_be_translated(monkeypatch):
    _import("tr_hidden", publish=False)
    monkeypatch.setattr(translate, "translate", lambda text, **kw: FRENCH)
    assert client.post("/api/decisions/tr_hidden/translation", headers=_h()).status_code == 404
    assert client.get("/api/decisions/tr_hidden/translation", headers=_h()).status_code == 404


def test_signing_in_is_required():
    assert client.post("/api/decisions/tr_once/translation").status_code == 401
    assert client.get("/api/decisions/tr_once/translation").status_code == 401


def test_only_french_is_offered():
    assert client.post("/api/decisions/tr_once/translation?lang=en", headers=_h()).status_code == 400
