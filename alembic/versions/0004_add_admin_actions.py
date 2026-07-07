# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only
"""add admin_actions

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-07

Audit trail for admin moderation actions (suspend, reinstate, content takedown).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_actions",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("admin_id", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("target_user_id", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=True),
        sa.Column("created_ts", sa.Integer(), nullable=False),
    )
    op.create_index("ix_admin_actions_created_ts", "admin_actions", ["created_ts"])


def downgrade() -> None:
    op.drop_index("ix_admin_actions_created_ts", table_name="admin_actions")
    op.drop_table("admin_actions")
