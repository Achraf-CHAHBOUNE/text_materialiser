"""The time, as the platform stores it: UTC, without a time zone attached.

Every timestamp column is TIMESTAMP WITHOUT TIME ZONE holding UTC, and every
comparison in the code is between such values. datetime.utcnow() produced exactly
that but is deprecated (Python 3.12); this produces the same value from the API
that stays. Moving the columns to time-zone-aware values would be a migration of
every timestamp for no change in behaviour, so the stored form stays as it is.
"""
from __future__ import annotations

import datetime as dt


def utcnow() -> dt.datetime:
    """Now, in UTC, naive -- the form every stored timestamp has."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
