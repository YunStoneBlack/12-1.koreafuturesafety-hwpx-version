"""사람마다 현장을 마지막으로 연 때(2026-10-08 사용자) — 현장 목록 "최근 열람순"(로그인한 사람 기준).

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-08
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "site_view",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("site.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("viewed_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("site_view")
