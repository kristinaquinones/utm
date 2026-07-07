# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

"""Tenant-scoped data access, replacing the single-file JSON store.

A ``Store`` is bound to exactly one ``user_id`` and every query it runs is
filtered by that id. This is the app's #1 new invariant: there is no un-scoped
read or write path. Cross-tenant access degrades safely: a foreign ``get_*``
returns ``None`` and a foreign ``update``/``delete`` is a no-op, so an attacker
supplying someone else's id sees a 404, never another tenant's data.

Methods return plain dicts with the same shape the JSON store returned, so the
routes, templates, and CSV export are unchanged by the swap.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db import now_iso
from app.models import Link, Template, User


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _link_dict(link: Link) -> dict[str, Any]:
    return {
        "id": link.id,
        "name": link.name,
        "base_url": link.base_url,
        "params": dict(link.params or {}),
        "generated_url": link.generated_url,
        "created_at": link.created_at,
        "updated_at": link.updated_at,
    }


def _template_dict(template: Template) -> dict[str, Any]:
    return {
        "id": template.id,
        "name": template.name,
        "params": dict(template.params or {}),
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }


def ensure_user(
    session_factory: sessionmaker,
    email: str,
    *,
    is_admin: bool = False,
    status: str = "pending",
) -> str:
    """Idempotently create a user and return its id.

    Used to seed the first admin on boot and to provision tenants in tests.
    """
    normalized = normalize_email(email)
    with session_factory() as session:
        user = session.execute(
            select(User).where(User.email == normalized)
        ).scalar_one_or_none()
        if user is None:
            now = now_iso()
            user = User(
                id=uuid.uuid4().hex,
                email=normalized,
                status=status,
                is_admin=is_admin,
                created_at=now,
                updated_at=now,
                approved_at=now if status == "approved" else None,
            )
            session.add(user)
            session.commit()
        return user.id


class Store:
    """Repository bound to a single tenant. Never construct one un-scoped."""

    def __init__(self, session_factory: sessionmaker, user_id: str) -> None:
        self._session_factory = session_factory
        self.user_id = user_id

    @contextmanager
    def _txn(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # -- links ---------------------------------------------------------------

    def list_links(self) -> list[dict[str, Any]]:
        with self._txn() as session:
            rows = session.execute(
                select(Link)
                .where(Link.user_id == self.user_id)
                .order_by(Link.updated_at.desc())
            ).scalars().all()
            return [_link_dict(row) for row in rows]

    def get_link(self, link_id: str) -> dict[str, Any] | None:
        with self._txn() as session:
            row = self._find_link(session, link_id)
            return _link_dict(row) if row else None

    def create_link(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = now_iso()
        with self._txn() as session:
            link = Link(
                id=uuid.uuid4().hex,
                user_id=self.user_id,
                name=payload["name"],
                base_url=payload["base_url"],
                params=payload.get("params", {}),
                generated_url=payload["generated_url"],
                created_at=now,
                updated_at=now,
            )
            session.add(link)
            session.flush()
            return _link_dict(link)

    def update_link(self, link_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        with self._txn() as session:
            link = self._find_link(session, link_id)
            if link is None:
                return None
            for field in ("name", "base_url", "params", "generated_url"):
                if field in payload:
                    setattr(link, field, payload[field])
            link.updated_at = now_iso()
            session.flush()
            return _link_dict(link)

    def delete_link(self, link_id: str) -> bool:
        with self._txn() as session:
            link = self._find_link(session, link_id)
            if link is None:
                return False
            session.delete(link)
            return True

    def _find_link(self, session: Session, link_id: str) -> Link | None:
        return session.execute(
            select(Link).where(Link.id == link_id, Link.user_id == self.user_id)
        ).scalar_one_or_none()

    # -- templates -----------------------------------------------------------

    def list_templates(self) -> list[dict[str, Any]]:
        with self._txn() as session:
            rows = session.execute(
                select(Template).where(Template.user_id == self.user_id)
            ).scalars().all()
            ordered = sorted(rows, key=lambda row: row.name.lower())
            return [_template_dict(row) for row in ordered]

    def get_template(self, template_id: str) -> dict[str, Any] | None:
        with self._txn() as session:
            row = self._find_template(session, template_id)
            return _template_dict(row) if row else None

    def create_template(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = now_iso()
        with self._txn() as session:
            template = Template(
                id=uuid.uuid4().hex,
                user_id=self.user_id,
                name=payload["name"],
                params=payload.get("params", {}),
                created_at=now,
                updated_at=now,
            )
            session.add(template)
            session.flush()
            return _template_dict(template)

    def delete_template(self, template_id: str) -> bool:
        with self._txn() as session:
            template = self._find_template(session, template_id)
            if template is None:
                return False
            session.delete(template)
            return True

    def _find_template(self, session: Session, template_id: str) -> Template | None:
        return session.execute(
            select(Template).where(
                Template.id == template_id, Template.user_id == self.user_id
            )
        ).scalar_one_or_none()
