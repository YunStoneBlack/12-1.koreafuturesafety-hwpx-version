"""건축물관리점검(건축물관리법 정기점검) 건 표 blcm_job(2026-10-29 사용자 "건축물관리점검 보고서 자동화 — 생애이력시스템 입력·제출까지").

항목 결과는 results JSON(소항목 code → 판정·점검현황·글·사진), 사진은 저장소 _건축물관리점검/건 폴더. server/api/routers/blcm.py.

Revision ID: 0069
Revises: 0068
Create Date: 2026-10-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0069"
down_revision: Union[str, None] = "0068"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "blcm_job",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False, index=True),
        sa.Column("name", sa.Text(), nullable=False, server_default=""),
        sa.Column("address", sa.Text(), nullable=False, server_default=""),
        sa.Column("building", sa.JSON(), nullable=True),
        sa.Column("owner", sa.JSON(), nullable=True),
        sa.Column("contract", sa.JSON(), nullable=True),
        sa.Column("results", sa.JSON(), nullable=True),
        sa.Column("opinion", sa.JSON(), nullable=True),
        sa.Column("site", sa.JSON(), nullable=True),
        sa.Column("files", sa.JSON(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=""),
        sa.Column("memo", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("blcm_job")
