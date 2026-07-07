# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only
"""add rate_events

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-07

Append-only rate-limit log backing the magic-link request limiter (see
app/ratelimit.py). Shared across workers via the database.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rate_events",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("bucket", sa.String(length=200), nullable=False),
        sa.Column("created_ts", sa.Integer(), nullable=False),
    )
    op.create_index("ix_rate_events_bucket_ts", "rate_events", ["bucket", "created_ts"])


def downgrade() -> None:
    op.drop_index("ix_rate_events_bucket_ts", table_name="rate_events")
    op.drop_table("rate_events")
