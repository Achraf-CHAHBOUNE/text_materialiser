"""Every module that defines a table, imported together so db.Base knows them all.

Alembic compares db.Base.metadata with the database. A module left out of this list
would look, to `alembic revision --autogenerate`, like tables to drop -- so a new
module with a table is added here the day it is written.
"""
import accounts  # noqa: F401
import billing  # noqa: F401
import contracts  # noqa: F401
import crm  # noqa: F401
import db  # noqa: F401
import importer  # noqa: F401
import insights  # noqa: F401
import library  # noqa: F401
import limits  # noqa: F401
import mailer  # noqa: F401
import support  # noqa: F401
