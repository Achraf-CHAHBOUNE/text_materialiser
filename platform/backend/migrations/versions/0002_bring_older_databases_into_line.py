"""Bring a database made before migrations into line with the models.

Older databases got some columns by ALTER TABLE (allowing NULL where the models do
not) and never got two indexes that were added to the models later: lookups by a
ruling's subject source and by a person's organization read the whole table. A
database made by 0001 already has all of this; every step here is a no-op there.

The NOT NULL part runs on Postgres only. On SQLite it would mean rebuilding the
rulings table, which loses the word index's link to its rows -- and the application
always fills these columns, so NULL never appears there in practice.
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

FILLED = (                      # (table, column, value for any NULL already there)
    ("decisions", "theme_source", "''"),
    ("decisions", "abstract", "''"),
    ("users", "full_name", "''"),
    ("users", "phone", "''"),
    ("users", "language", "'ar'"),
    ("users", "mfa_secret", "''"),
)


def upgrade() -> None:
    op.create_index("ix_decisions_theme_source", "decisions", ["theme_source"], if_not_exists=True)
    op.create_index("ix_users_org_id", "users", ["org_id"], if_not_exists=True)
    if op.get_bind().dialect.name == "postgresql":
        for table, column, value in FILLED:
            op.execute(f"UPDATE {table} SET {column} = {value} WHERE {column} IS NULL")
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL")


def downgrade() -> None:
    # 0001 has these indexes and NOT NULLs too: going back changes nothing
    pass
