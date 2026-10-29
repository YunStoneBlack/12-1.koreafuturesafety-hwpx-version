"""통합 견적 표 estimate(2026-10-29 사용자 "그룹웨어 통합 견적서 — 각 용역별로 선택해서 쓰고 관리").

용역 8가지(server/estimate/calc.KINDS)·금액 줄 rows JSON·상태(작성중·보냄·수주·실패). server/api/routers/estimates.py.

Revision ID: 0070
Revises: 0069
Create Date: 2026-10-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0070"
down_revision: Union[str, None] = "0069"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "estimate",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False, index=True),
        sa.Column("no", sa.Text(), nullable=False, server_default=""),
        sa.Column("kind", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("issued_on", sa.Date(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("client", sa.JSON(), nullable=True),
        sa.Column("project", sa.JSON(), nullable=True),
        sa.Column("staff", sa.JSON(), nullable=True),
        sa.Column("rows", sa.JSON(), nullable=True),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("totals", sa.JSON(), nullable=True),
        sa.Column("link", sa.JSON(), nullable=True),
        sa.Column("files", sa.JSON(), nullable=True),
        sa.Column("memo", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("estimate")
