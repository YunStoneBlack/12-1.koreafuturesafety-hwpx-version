"""시특법 결함 사진 분류 교정 기록(sitok_correction) + 결함의 AI 첫 추천(sitok_defect.ai_guess) — 2026-10-12.

사용자: 사진 AI가 추천한 구분·부재·결함유형을 점검자가 바꿔 저장하면 기억해 다음 비슷한 사진 분석에 적용(원인 추천은 안 함).

Revision ID: 0038
Revises: 0037
Create Date: 2026-10-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_defect", sa.Column("ai_guess", sa.JSON(), nullable=True))
    op.create_table(
        "sitok_correction",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False, index=True),
        sa.Column("defect_id", sa.Integer(), nullable=True, index=True),
        sa.Column("ai_part", sa.Text(), nullable=False, server_default=""),
        sa.Column("ai_member", sa.Text(), nullable=False, server_default=""),
        sa.Column("ai_dtype", sa.Text(), nullable=False, server_default=""),
        sa.Column("part", sa.Text(), nullable=False, server_default=""),
        sa.Column("member", sa.Text(), nullable=False, server_default=""),
        sa.Column("dtype", sa.Text(), nullable=False, server_default=""),
        sa.Column("thumb", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("sitok_correction")
    op.drop_column("sitok_defect", "ai_guess")
