""""K2B 직접 제출함" 표시(2026-10-10 사용자) — 제출 완료 = 전송(또는 직접 제출함) + K2B 제출. K2B 사이트에 직접 넣은 보고서용.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_k2b_mark",
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("report.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("marked_at", sa.DateTime(), nullable=False),
        sa.Column("marked_by", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("report_k2b_mark")
