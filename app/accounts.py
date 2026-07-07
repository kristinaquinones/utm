# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

"""Account and admin management (not tenant-scoped).

These operate on the users table across tenants: signup, the admin approval
queue, and the first-admin seed. Kept separate from the tenant-scoped Store in
app/repository.py, which never touches other users' rows.

Policy decisions encoded here:
- Signup never resurrects an existing account. A brand-new email creates a
  ``pending`` row; any existing email (pending, approved, or denied) is left
  untouched, so re-submitting can't spam the queue or flip a denial back.
- ``is_admin`` is granted only by the ADMIN_EMAILS seed, never through the UI, so
  approving a user can't escalate privileges.
- The seed is additive: it promotes listed emails to admin + approved and never
  demotes anyone.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.branding import normalize_hex
from app.db import now_iso
from app.models import User
from app.repository import normalize_email


def _user_dict(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "status": user.status,
        "is_admin": user.is_admin,
        "workspace_name": user.workspace_name,
        "accent_color": user.accent_color,
        "created_at": user.created_at,
        "approved_at": user.approved_at,
        "approved_by": user.approved_by,
    }


def signup(session_factory: sessionmaker, email: str, workspace_name: str = "") -> bool:
    """Create a pending account for a new email. Returns True only if one was created.

    Returning False for an already-known email lets the caller skip re-notifying
    admins, while still showing the same response to the visitor.
    """
    normalized = normalize_email(email)
    if not normalized:
        return False

    with session_factory() as db:
        existing = db.execute(
            select(User).where(User.email == normalized)
        ).scalar_one_or_none()
        if existing is not None:
            return False

        now = now_iso()
        db.add(
            User(
                id=uuid.uuid4().hex,
                email=normalized,
                status="pending",
                is_admin=False,
                # Cap to the column width so an oversized value can't 500 on Postgres.
                workspace_name=workspace_name.strip()[:120] or None,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        return True


def list_pending_users(session_factory: sessionmaker) -> list[dict[str, Any]]:
    with session_factory() as db:
        rows = db.execute(
            select(User).where(User.status == "pending").order_by(User.created_at)
        ).scalars().all()
        return [_user_dict(row) for row in rows]


def set_status(
    session_factory: sessionmaker,
    user_id: str,
    status: str,
    approved_by: str | None = None,
) -> dict[str, Any] | None:
    """Approve or deny a user. Never touches ``is_admin`` (no privilege change)."""
    with session_factory() as db:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None:
            return None
        user.status = status
        user.updated_at = now_iso()
        if status == "approved":
            user.approved_at = now_iso()
            user.approved_by = approved_by
        db.commit()
        return _user_dict(user)


def update_branding(
    session_factory: sessionmaker,
    user_id: str,
    workspace_name: str,
    accent_color: str,
) -> dict[str, Any] | None:
    """Save a user's own branding. Accent is stored only if it's a valid hex."""
    with session_factory() as db:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None:
            return None
        user.workspace_name = workspace_name.strip()[:120] or None
        # normalize_hex returns None for anything that isn't a valid color, so a
        # junk value simply clears branding rather than being stored.
        user.accent_color = normalize_hex(accent_color)
        user.updated_at = now_iso()
        db.commit()
        return _user_dict(user)


def admin_emails(session_factory: sessionmaker) -> list[str]:
    with session_factory() as db:
        rows = db.execute(select(User.email).where(User.is_admin.is_(True))).scalars().all()
        return list(rows)


def promote_admins(session_factory: sessionmaker, emails: tuple[str, ...]) -> str:
    """Ensure each email is an approved admin. Additive: never demotes. Idempotent.

    Returns the first admin's id (used to seed app state).
    """
    first_id = ""
    for index, raw_email in enumerate(emails):
        normalized = normalize_email(raw_email)
        with session_factory() as db:
            user = db.execute(
                select(User).where(User.email == normalized)
            ).scalar_one_or_none()
            now = now_iso()
            if user is None:
                user = User(
                    id=uuid.uuid4().hex,
                    email=normalized,
                    status="approved",
                    is_admin=True,
                    created_at=now,
                    updated_at=now,
                    approved_at=now,
                )
                db.add(user)
            else:
                user.is_admin = True
                if user.status != "approved":
                    user.status = "approved"
                    user.approved_at = now
                user.updated_at = now
            db.commit()
            if index == 0:
                first_id = user.id
    return first_id
