"""Sub-phase 53: report_edit(보고서별 마지막 수정 시각) — "PDF 수정 전 버전" 표시용 웹판 전용 표.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_edit",
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("report.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("edited_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("report_edit")
