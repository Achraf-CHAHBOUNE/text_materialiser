"""A request leaves one line in the log, with no personal data in it."""
import json
import logging
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.update(DB_DIR=_tmp, FILESTORE_DIR=os.path.join(_tmp, "files"), AUTH_SECRET="test-secret",
                  SEED_EMAIL="admin@x.com", SEED_PASSWORD="admin-pass")
os.environ.pop("DATABASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402

import logs  # noqa: E402
import server  # noqa: E402


def test_a_request_is_logged_by_its_route_never_its_address(caplog):
    with TestClient(server.app) as c, caplog.at_level(logging.INFO, logger="api"):
        tok = c.post("/api/auth/login", json={"email": "admin@x.com", "password": "admin-pass"}).json()["token"]
        r = c.get("/api/crm/users/someone.private@cabinet.ma", headers={"Authorization": f"Bearer {tok}",
                                                                      "X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"
    line = next(rec for rec in caplog.records if getattr(rec, "rid", "") == "abc123")
    assert line.path == "/api/crm/users/{email}" and line.status in (200, 404)
    text = logs._Json("api").format(line)
    assert "someone.private" not in text and json.loads(text)["service"] == "api"
