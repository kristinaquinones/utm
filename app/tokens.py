# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

"""Magic-link token lifecycle.

Tokens are high-entropy and never stored in the clear: only a SHA-256 hash lands
in the database, so a database leak cannot be replayed into a login. Each token
is single-use (``consumed_at``) and short-lived (``expires_at``). Lookups are by
hash, so there is no per-character timing signal to exploit.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db import now_iso
from app.models import LoginToken


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_login_token(session_factory: sessionmaker, user_id: str, ttl_seconds: int) -> str:
    """Mint a single-use token for ``user_id`` and return the raw value.

    Only the hash is persisted; the raw token exists only in the returned value
    (which goes into the emailed link) and is never recoverable from the row.
    """
    raw_token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat(
        timespec="seconds"
    )
    with session_factory() as db:
        db.add(
            LoginToken(
                id=uuid.uuid4().hex,
                user_id=user_id,
                token_hash=hash_token(raw_token),
                expires_at=expires_at,
                created_at=now_iso(),
            )
        )
        db.commit()
    return raw_token


def consume_login_token(session_factory: sessionmaker, raw_token: str) -> str | None:
    """Validate and burn a token, returning its ``user_id`` or ``None``.

    ``None`` covers unknown, already-consumed, and expired tokens alike, so the
    caller cannot distinguish the reasons.
    """
    if not raw_token:
        return None

    token_hash = hash_token(raw_token)
    with session_factory() as db:
        token = db.execute(
            select(LoginToken).where(LoginToken.token_hash == token_hash)
        ).scalar_one_or_none()
        if token is None or token.consumed_at is not None:
            return None
        if now_iso() > token.expires_at:
            return None
        token.consumed_at = now_iso()
        db.commit()
        return token.user_id
