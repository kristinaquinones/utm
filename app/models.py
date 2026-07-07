# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

"""ORM models for the multi-tenant schema.

Tenancy rule: ``links`` and ``templates`` each carry a ``user_id`` foreign key,
and every query in the repository is filtered by it. ``login_tokens`` is defined
now so the initial migration is complete, but it is not exercised until the
magic-link work in Phase 2.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


# JSONB on Postgres, plain JSON elsewhere (SQLite in tests).
ParamsJSON = JSON().with_variant(JSONB, "postgresql")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    # Stored lowercased; uniqueness is enforced on the normalized value in place
    # of the Postgres citext extension, so the constraint holds on SQLite too.
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    workspace_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    accent_color: Mapped[str | None] = mapped_column(String(9), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)
    approved_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(32), nullable=True)


class LoginToken(Base):
    __tablename__ = "login_tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[str] = mapped_column(String(32), nullable=False)
    consumed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (Index("ix_login_tokens_user_id", "user_id"),)


class Link(Base):
    __tablename__ = "links"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    params: Mapped[dict] = mapped_column(ParamsJSON, nullable=False, default=dict)
    generated_url: Mapped[str] = mapped_column(String(4096), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (Index("ix_links_user_id", "user_id"),)


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    params: Mapped[dict] = mapped_column(ParamsJSON, nullable=False, default=dict)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (Index("ix_templates_user_id", "user_id"),)
