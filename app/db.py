# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

"""SQLAlchemy engine and session wiring.

The schema is written portably: production and CI run Postgres, while the test
suite runs SQLite so ``pytest`` needs no external service. The tenant-isolation
logic under test is application-level (every query filtered by ``user_id``), so
it is validated identically on either engine.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import Settings


class Base(DeclarativeBase):
    pass


def make_engine(settings: Settings) -> Engine:
    connect_args: dict[str, object] = {}
    if settings.is_sqlite:
        # Sessions are opened from the request threadpool, so allow cross-thread
        # use of the SQLite connection. (Postgres has no such restriction.)
        connect_args["check_same_thread"] = False
    return create_engine(
        settings.database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        future=True,
    )


def make_session_factory(settings: Settings) -> tuple[Engine, sessionmaker]:
    engine = make_engine(settings)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
    return engine, factory


def now_iso() -> str:
    """ISO-8601 UTC timestamp, second precision.

    Timestamps are stored as strings to preserve the JSON store's ordering and
    display behavior byte-for-byte during the migration; string sort of ISO-8601
    is chronological.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
