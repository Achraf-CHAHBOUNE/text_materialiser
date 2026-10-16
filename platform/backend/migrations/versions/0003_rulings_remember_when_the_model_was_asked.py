"""Rulings remember when the model was asked for their subject and summary.

The worker asks only for rulings never asked (AUTO_ENRICH=1), so each is paid for once.
Every ruling already here went through the batch run of enrich.py, so it is marked as
asked: turning the worker's step on never re-asks the corpus.
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


# SQLite's word index used to re-index a ruling on ANY change to its row; marking every
# ruling below would have re-indexed the whole corpus. The trigger now fires only when
# the text changes (db.py makes new databases that way).
FTS_TRIGGER = (
    "CREATE TRIGGER decisions_fts_au AFTER UPDATE OF search_text ON decisions BEGIN"
    "  INSERT INTO decisions_fts(decisions_fts, rowid, search_text)"
    "  VALUES ('delete', old.rowid, old.search_text);"
    "  INSERT INTO decisions_fts(rowid, search_text) VALUES (new.rowid, new.search_text);"
    " END")
FTS_FR_TRIGGER = (
    "CREATE TRIGGER decision_i18n_fts_au AFTER UPDATE OF search_text ON decision_i18n BEGIN"
    "  INSERT INTO decision_i18n_fts(decision_i18n_fts, rowid, search_text)"
    "  VALUES ('delete', old.id, old.search_text);"
    "  INSERT INTO decision_i18n_fts(rowid, search_text) VALUES (new.id, new.search_text);"
    " END")


def _narrow_sqlite_triggers() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    for name, table, sql in (("decisions_fts_au", "decisions_fts", FTS_TRIGGER),
                             ("decision_i18n_fts_au", "decision_i18n_fts", FTS_FR_TRIGGER)):
        if bind.exec_driver_sql("SELECT 1 FROM sqlite_master WHERE name = ?", (table,)).scalar():
            op.execute(f"DROP TRIGGER IF EXISTS {name}")
            op.execute(sql)


def upgrade() -> None:
    _narrow_sqlite_triggers()
    # a table an older database lacked is made from today's models, column included
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("decisions")}
    if "enriched_at" not in have:
        with op.batch_alter_table("decisions") as batch:
            batch.add_column(sa.Column("enriched_at", sa.DateTime(), nullable=True))
    op.create_index("ix_decisions_enriched_at", "decisions", ["enriched_at"], if_not_exists=True)
    op.execute("UPDATE decisions SET enriched_at = CURRENT_TIMESTAMP WHERE enriched_at IS NULL")


def downgrade() -> None:
    op.drop_index("ix_decisions_enriched_at", table_name="decisions")
    with op.batch_alter_table("decisions") as batch:
        batch.drop_column("enriched_at")
