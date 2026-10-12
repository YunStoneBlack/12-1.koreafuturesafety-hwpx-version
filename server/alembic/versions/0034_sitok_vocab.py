"""시특법 결함 부재·결함유형 목록(sitok_vocab) + 결함 원인 근거(sitok_defect.cause_note) — 2026-10-12.

회사 목록(report_id 없음, 처음 열 때 server/sitok/kinds.py 기본값)과 그 회차에만 추가한 것(report_id).

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sitok_vocab",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False, index=True),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("sitok_report.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("sitok_defect", sa.Column("cause_note", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("sitok_defect", "cause_note")
    op.drop_table("sitok_vocab")
