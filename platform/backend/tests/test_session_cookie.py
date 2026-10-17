"""The session lives in an HttpOnly cookie: no token for page scripts to read, none in
file addresses, and no change accepted from another site's page."""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.update(DB_DIR=_tmp, FILESTORE_DIR=os.path.join(_tmp, "files"), AUTH_SECRET="test-secret",
                  SEED_EMAIL="admin@x.com", SEED_PASSWORD="admin-pass")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("S3_ENDPOINT", None)

from fastapi.testclient import TestClient  # noqa: E402

import db  # noqa: E402
import server  # noqa: E402
import storage  # noqa: E402

SITE = "http://testserver"


def _client():
    return TestClient(server.app, base_url=SITE)


def _sign_in(c):
    r = c.post("/api/auth/login", json={"email": "admin@x.com", "password": "admin-pass"})
    assert r.status_code == 200
    return r


def test_signing_in_sets_an_httponly_cookie_that_signs_the_browser_in():
    with _client() as c:
        r = _sign_in(c)
        cookie = r.headers["set-cookie"]
        assert "tok_session=" in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
        assert "Secure" not in cookie                    # plain http here; https sets it
        assert c.get("/api/account").status_code == 200, "the cookie alone signs the browser in"


def test_a_change_with_the_cookie_must_come_from_the_site_itself():
    with _client() as c:
        _sign_in(c)
        body = {"name": "Dossier"}
        assert c.post("/api/me/folders", json=body).status_code == 403, "no origin: refused"
        assert c.post("/api/me/folders", json=body, headers={"Origin": "https://evil.example"}).status_code == 403
        assert c.post("/api/me/folders", json=body, headers={"Origin": SITE}).status_code == 200


def test_the_authorization_header_still_works_from_anywhere():
    with _client() as c:
        tok = _sign_in(c).json()["token"]
        c.cookies.clear()
        r = c.post("/api/me/folders", json={"name": "Script"}, headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, "a script or an older page keeps working"


def test_a_file_downloads_with_the_cookie_and_no_token_in_its_address():
    db.upsert_decision({"doc_id": "ck_file", "category": "مدنية"}, body_text="نص", file_name="ck_file.docx")
    db.set_decision_state("ck_file", "published", "t")
    storage.STORE.put("ck_file.docx", b"PK\x03\x04 a word file")
    with _client() as c:
        tok = _sign_in(c).json()["token"]
        assert c.get("/api/decisions/ck_file/file").status_code == 200
        c.cookies.clear()
        assert c.get("/api/decisions/ck_file/file").status_code == 401
        assert c.get(f"/api/decisions/ck_file/file?token={tok}").status_code == 200, "an old link still works"


def test_a_page_holding_an_old_token_moves_to_the_cookie():
    with _client() as c:
        tok = _sign_in(c).json()["token"]
        c.cookies.clear()
        r = c.post("/api/auth/session", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200 and "tok_session=" in r.headers["set-cookie"]
        assert c.get("/api/account").status_code == 200, "same session, now by cookie"


def test_signing_out_ends_the_session_and_clears_the_cookie():
    with _client() as c:
        _sign_in(c)
        old = c.cookies.get("tok_session")
        r = c.post("/api/auth/logout", headers={"Origin": SITE})
        assert r.status_code == 200 and 'tok_session=""' in r.headers["set-cookie"]
        c.cookies.set("tok_session", old)                # replayed: the session is over
        assert c.get("/api/account").status_code == 401
