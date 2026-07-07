# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only
"""initial multi-tenant schema

Revision ID: 0001
Revises:
Create Date: 2026-07-06

Creates users, login_tokens, and the tenant-scoped links and templates tables.

Note: email uniqueness is enforced on an application-normalized (lowercased)
value rather than the Postgres citext extension, so the same schema runs on
SQLite in tests. See app/repository.py:normalize_email.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# JSONB on Postgres, plain JSON elsewhere. Mirrors app/models.py:ParamsJSON.
def _params_type() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(JSONB, "postgresql")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("workspace_name", sa.String(length=120), nullable=True),
        sa.Column("accent_color", sa.String(length=9), nullable=True),
        sa.Column("logo_url", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.Column("approved_at", sa.String(length=32), nullable=True),
        sa.Column("approved_by", sa.String(length=32), nullable=True),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "login_tokens",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.String(length=32), nullable=False),
        sa.Column("consumed_at", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name="fk_login_tokens_user_id"
        ),
        sa.UniqueConstraint("token_hash", name="uq_login_tokens_token_hash"),
    )
    op.create_index("ix_login_tokens_user_id", "login_tokens", ["user_id"])

    op.create_table(
        "links",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=False),
        sa.Column("params", _params_type(), nullable=False),
        sa.Column("generated_url", sa.String(length=4096), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name="fk_links_user_id"
        ),
    )
    op.create_index("ix_links_user_id", "links", ["user_id"])

    op.create_table(
        "templates",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("params", _params_type(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name="fk_templates_user_id"
        ),
    )
    op.create_index("ix_templates_user_id", "templates", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_templates_user_id", table_name="templates")
    op.drop_table("templates")
    op.drop_index("ix_links_user_id", table_name="links")
    op.drop_table("links")
    op.drop_index("ix_login_tokens_user_id", table_name="login_tokens")
    op.drop_table("login_tokens")
    op.drop_table("users")
