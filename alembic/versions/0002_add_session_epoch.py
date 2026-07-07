# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only
"""add users.session_epoch

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-06

Adds the session-epoch counter used to revoke a user's sessions en masse
(see app/auth.py). Existing rows default to 0.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("session_epoch", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "session_epoch")
