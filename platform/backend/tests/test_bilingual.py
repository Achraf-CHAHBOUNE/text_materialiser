"""The French site: the same rulings, their French alongside, never in place of the Arabic.

Env matches the other test modules: whichever is imported first configures the app.
"""
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

import db  # noqa: E402
import server  # noqa: E402
import textnorm  # noqa: E402

server._startup()
client = TestClient(server.app)

AR_BODY = "وحيث إن عقد الكراء صحيح ولا يحتاج إلى إثبات"
FR_BODY = "Attendu que le contrat de bail est valable et ne nécessite pas de preuve"


def _add(doc_id, *, theme_key="", theme="", keywords="", rule="", abstract=""):
    with db.session() as s:
        s.merge(db.Decision(
            doc_id=doc_id, category="مدنية", court="محكمة النقض", decision_no=doc_id[-3:],
            decision_date="01/02/2020", year="2020", state="published",
            theme_key=theme_key, theme=theme, keywords=keywords, rule=rule, abstract=abstract,
            body_text=AR_BODY, search_text=textnorm.normalize(AR_BODY),
            sort_key=f"2020-02-01:{doc_id}"))
        s.commit()


@pytest.fixture(scope="module", autouse=True)
def _corpus():
    _add("bi_001", theme_key="كراء", theme="الكراء", keywords="الكراء - الإثبات",
         abstract="ملخص مكتوب لنا")
    _add("bi_002")                      # a ruling with no French at all
    db.save_i18n("bi_001", "fr", body_text=FR_BODY, abstract="Le bail se prouve par écrit.",
                 abstract_of="abstract", keywords="Bail - Preuve", model="test", version=0)
    with db.session() as s:
        s.merge(db.Subject(key="كراء", label_ar="الكراء", label_fr="Bail"))
        s.commit()
    yield


def _auth():
    tok = client.post("/api/auth/login",
                      json={"email": "admin@x.com", "password": "admin-pass"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_french_is_folded_for_search():
    assert textnorm.fold_latin("Arrêt — CONTRAT, Bail!") == "arret contrat bail"


def test_arabic_listing_is_unchanged():
    got = client.get("/api/browse/rulings?chamber=مدنية&lang=ar", headers=_auth()).json()
    row = next(r for r in got["items"] if r["doc_id"] == "bi_001")
    assert "abstract_fr" not in row and row["keywords"] == "الكراء - الإثبات"


def test_french_listing_carries_french_beside_arabic():
    got = client.get("/api/browse/rulings?chamber=مدنية&lang=fr", headers=_auth()).json()
    row = next(r for r in got["items"] if r["doc_id"] == "bi_001")
    assert row["abstract_fr"] == "Le bail se prouve par écrit."
    assert row["keywords_fr"] == "Bail - Preuve"
    assert row["theme_fr"] == "Bail"
    assert row["keywords"] == "الكراء - الإثبات"          # the Arabic is still there
    bare = next(r for r in got["items"] if r["doc_id"] == "bi_002")
    assert bare["abstract_fr"] == "" and bare["has_fr"] is False


def test_a_french_search_reads_the_french_text_without_accents():
    got = client.get("/api/browse/rulings?q=necessite&lang=fr", headers=_auth()).json()
    assert [r["doc_id"] for r in got["items"]] == ["bi_001"]


def test_an_arabic_search_on_the_french_site_reads_the_arabic():
    got = client.get("/api/browse/rulings?q=الكراء&lang=fr", headers=_auth()).json()
    assert {r["doc_id"] for r in got["items"]} == {"bi_001", "bi_002"}


def test_subjects_are_named_in_french_with_the_arabic_kept():
    got = client.get("/api/browse/themes?chamber=مدنية&lang=fr", headers=_auth()).json()
    t = next(x for x in got if x["key"] == "كراء")
    assert t["label"] == "Bail" and t["label_ar"] == "الكراء"


def test_the_ruling_and_its_translation_carry_the_french_headnote():
    d = client.get("/api/decisions/bi_001?lang=fr", headers=_auth()).json()
    assert d["has_fr"] is True and d["abstract_fr_of"] == "abstract"
    tr = client.get("/api/decisions/bi_001/translation?lang=fr", headers=_auth()).json()
    assert tr["ready"] is True and tr["text"] == FR_BODY and tr["keywords_fr"] == "Bail - Preuve"


def test_an_unknown_language_is_read_as_arabic():
    d = client.get("/api/decisions/bi_001?lang=xx", headers=_auth()).json()
    assert "abstract_fr" not in d
