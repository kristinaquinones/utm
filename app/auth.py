# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

"""Session, CSRF, and current-user primitives.

The session is a signed (not encrypted) cookie, so it holds only non-secret
identifiers: the user id, the user's ``session_epoch`` at login, an issued-at
timestamp, and a CSRF token. Every protected request re-validates the session
against the database: the user must still exist and be ``approved``, the epoch
must still match (bumping it logs the user out everywhere), and the session must
be within its absolute lifetime.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import User


# Paths reachable without a session. Everything else is behind the auth gate.
EXEMPT_PREFIXES = ("/static", "/login", "/logout", "/signup", "/auth", "/healthz")


def is_exempt_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in EXEMPT_PREFIXES)


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


# -- CSRF (per session, including anonymous visitors) ------------------------


def ensure_csrf(request: Request) -> str:
    """Return this session's CSRF token, minting one on first use.

    Logged-out visitors get a token too, so the login and signup forms are
    protected before any user session exists.
    """
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


def verify_csrf(request: Request, submitted: str) -> bool:
    expected = request.session.get("csrf", "")
    return bool(expected) and secrets.compare_digest(submitted, expected)


# -- session lifecycle -------------------------------------------------------


def login_user(request: Request, user_id: str, session_epoch: int) -> None:
    request.session["user_id"] = user_id
    request.session["epoch"] = session_epoch
    request.session["iat"] = _now_ts()
    # Rotate the CSRF token on the privilege change (anonymous -> logged in).
    request.session["csrf"] = secrets.token_urlsafe(32)


def logout_user(request: Request) -> None:
    request.session.clear()


def load_session_user(
    session_factory: sessionmaker, request: Request, absolute_max_age: int
) -> dict[str, Any] | None:
    """Validate the session and return the current user, or ``None``.

    ``None`` means "treat as logged out": no session, expired, de-approved, or a
    stale epoch. Returns a detached dict so callers never hold a live ORM row.
    """
    session = request.session
    user_id = session.get("user_id")
    if not user_id:
        return None

    issued_at = int(session.get("iat", 0))
    if _now_ts() - issued_at > absolute_max_age:
        return None

    with session_factory() as db:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None or user.status != "approved":
            return None
        if session.get("epoch") != user.session_epoch:
            return None
        return {
            "id": user.id,
            "email": user.email,
            "is_admin": user.is_admin,
            "status": user.status,
            "workspace_name": user.workspace_name,
            "accent_color": user.accent_color,
        }
