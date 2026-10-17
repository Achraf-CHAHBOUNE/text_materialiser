"""Limits that hold across every copy of the API: kept in the database, not in memory.

A limit counts events for a key within a window -- wrong passwords for one email from
one address, requests from one address on the public form. Several API processes or
containers see the same counts, and a restart forgets nothing it should remember.

    limits.add("login", key)
    limits.recent("login", key, seconds=900)      # events still inside the window
    limits.clear("login", key)                    # e.g. after a correct password
    limits.prune()                                # the worker drops what has expired
"""
from __future__ import annotations

import datetime as dt
from typing import List

from sqlalchemy import DateTime, Integer, String, delete, select
from sqlalchemy.orm import Mapped, mapped_column

import clock
import db

KEEP = dt.timedelta(days=1)           # no window is longer than this


class RateEvent(db.Base):
    __tablename__ = "rate_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket: Mapped[str] = mapped_column(String(32), index=True)
    key: Mapped[str] = mapped_column(String(320), index=True)
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=clock.utcnow, index=True)


def add(bucket: str, key: str) -> None:
    with db.session() as s:
        s.add(RateEvent(bucket=bucket, key=key[:320]))
        s.commit()


def recent(bucket: str, key: str, seconds: int) -> List[dt.datetime]:
    """When each event inside the window happened, oldest first."""
    since = clock.utcnow() - dt.timedelta(seconds=seconds)
    with db.session() as s:
        return list(s.scalars(select(RateEvent.at).where(
            RateEvent.bucket == bucket, RateEvent.key == key[:320], RateEvent.at >= since)
            .order_by(RateEvent.at)))


def clear(bucket: str, key: str) -> None:
    with db.session() as s:
        s.execute(delete(RateEvent).where(RateEvent.bucket == bucket, RateEvent.key == key[:320]))
        s.commit()


def prune() -> int:
    with db.session() as s:
        n = s.execute(delete(RateEvent).where(RateEvent.at < clock.utcnow() - KEEP)).rowcount
        s.commit()
    return n or 0
