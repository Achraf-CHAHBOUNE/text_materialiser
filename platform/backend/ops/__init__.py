"""Operations run inside the backend image: preparing the stores, moving data into them.

    python -m ops.storage_init     give Garage its node, key and bucket (idempotent)
    python -m ops.migrate          copy a SQLite database and a file folder into
                                   Postgres and the object store, then check them
"""
