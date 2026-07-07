# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

"""Database-backed sliding-window rate limiter.

Backed by a Postgres table (``rate_events``) rather than an in-process counter,
so the limit is shared across every worker and instance. Chosen over Redis to
avoid adding infrastructure for a small single-tenant-per-user tool; revisit if
throughput ever needs it.
"""

from __future__ import annotations

import time
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.models import RateEvent


def allow(session_factory: sessionmaker, bucket: str, max_count: int, window_seconds: int) -> bool:
    """Record an attempt against ``bucket`` and report whether it is allowed.

    Returns ``False`` when the bucket already has ``max_count`` attempts within
    the window (and records nothing further); ``True`` otherwise (recording the
    attempt).
    """
    now = int(time.time())
    cutoff = now - window_seconds
    with session_factory() as db:
        count = db.execute(
            select(func.count())
            .select_from(RateEvent)
            .where(RateEvent.bucket == bucket, RateEvent.created_ts > cutoff)
        ).scalar_one()
        if count >= max_count:
            return False
        db.add(RateEvent(id=uuid.uuid4().hex, bucket=bucket, created_ts=now))
        db.commit()
        return True
