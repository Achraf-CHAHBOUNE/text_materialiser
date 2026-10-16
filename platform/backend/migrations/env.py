"""How Alembic reaches the database: the backend's own connection and models.

Run by `alembic ...` from backend/, and by db.init_db() at every start (which passes
its connection in config.attributes["connection"]).
"""
from alembic import context

import db
import models  # noqa: F401  -- every table registered on db.Base

config = context.config
target_metadata = db.Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    # Things the models do not describe -- the word-search columns and indexes made by
    # db.py, SQLite's FTS tables -- are left alone: a migration never drops them.
    if reflected and compare_to is None:
        return False
    return True


def run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata,
                      include_object=include_object,
                      render_as_batch=connection.dialect.name == "sqlite",   # SQLite cannot ALTER much
                      compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


given = config.attributes.get("connection")
if given is not None:
    run(given)
else:
    with db._engine.connect() as conn:
        run(conn)
        conn.commit()
