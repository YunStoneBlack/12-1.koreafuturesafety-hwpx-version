"""Sub-phase 63: report_mail(고객사에 보고서 PDF를 메일로 보낸 기록) — 웹판 전용 표.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_mail",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("report.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.Column("to_addr", sa.Text(), nullable=False),
        sa.Column("cc_addr", sa.Text(), nullable=False),
        sa.Column("sent_by", sa.Text(), nullable=False),
    )
    op.create_index("ix_report_mail_report_id", "report_mail", ["report_id"])


def downgrade() -> None:
    op.drop_index("ix_report_mail_report_id", table_name="report_mail")
    op.drop_table("report_mail")
