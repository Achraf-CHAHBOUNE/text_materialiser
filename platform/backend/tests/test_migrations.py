"""The structure of the database moves by migrations, for a new database and for one
made before migrations existed."""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.update(DB_DIR=_tmp, FILESTORE_DIR=os.path.join(_tmp, "files"), AUTH_SECRET="test-secret")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("S3_ENDPOINT", None)

from sqlalchemy import create_engine, inspect, text  # noqa: E402

import db  # noqa: E402
import models  # noqa: E402,F401
import settings  # noqa: E402


def _use(folder):
    os.environ["DB_DIR"] = str(folder)
    settings.reload()
    db.configure()


def _version():
    with db._engine.connect() as c:
        return c.execute(text("SELECT version_num FROM alembic_version")).scalar()


def test_a_new_database_is_made_by_the_migrations(tmp_path):
    _use(tmp_path)
    db.init_db()
    assert _version() == "0002"
    have = set(inspect(db._engine).get_table_names())
    assert {t.name for t in db.Base.metadata.sorted_tables} <= have


def test_a_database_from_before_migrations_is_brought_into_line(tmp_path):
    # the way databases used to be made: create_all, and columns added later by ALTER
    old = create_engine(f"sqlite:///{(tmp_path / 'app.db').as_posix()}")
    db.Base.metadata.create_all(old, tables=[t for t in db.Base.metadata.sorted_tables
                                             if t.name in db._baseline_tables()])
    with old.begin() as c:
        c.execute(text("DROP INDEX ix_users_org_id"))
        c.execute(text("ALTER TABLE users DROP COLUMN mfa_secret"))
        c.execute(text("INSERT INTO users (email, password_hash, role, status, full_name, phone, language, created_at) "
                       "VALUES ('kept@x.ma', '', 'client', 'active', '', '', 'ar', CURRENT_TIMESTAMP)"))
    old.dispose()

    _use(tmp_path)
    db.init_db()
    assert _version() == "0002"
    cols = {c["name"] for c in inspect(db._engine).get_columns("users")}
    idx = {i["name"] for i in inspect(db._engine).get_indexes("users")}
    assert "mfa_secret" in cols and "ix_users_org_id" in idx
    assert db.get_user("kept@x.ma") is not None, "nothing already there is lost"

    db.init_db()                                   # a second start changes nothing
    assert _version() == "0002"
