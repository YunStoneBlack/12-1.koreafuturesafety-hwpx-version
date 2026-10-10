"""시특법 보수 단가표(sitok_unit_price) + 보고서 AI 초안 칸(sitok_report.ai) — 2026-10-11.

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sitok_unit_price",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False, index=True),
        sa.Column("method", sa.Text(), nullable=False, server_default=""),
        sa.Column("unit", sa.Text(), nullable=False, server_default="m"),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("sitok_report", sa.Column("ai", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sitok_report", "ai")
    op.drop_table("sitok_unit_price")
