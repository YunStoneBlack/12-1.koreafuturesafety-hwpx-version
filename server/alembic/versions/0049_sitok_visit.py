"""시특법 방문 달력(2026-10-15 민재형 문서번호 일치화 문서 "보고서 달력관리").

sitok_visit: 시설물(묶인 동은 대표 동) 반기마다 현장 점검 날 — 계약이 덮는 반기에 하루씩 자동(같은 시·군끼리 같은 날, 하루 건물 4개까지,
관급은 착수일 1주일 안), 사람이 넣거나 옮긴 날은 source=manual(📌). 한 반기에 날을 더 넣을 수 있음(관리자 — 정밀 등 하루로 모자랄 때).

Revision ID: 0049
Revises: 0048
Create Date: 2026-10-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0049"
down_revision: Union[str, None] = "0048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sitok_visit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("company.id"), nullable=False, index=True),
        sa.Column("facility_id", sa.Integer(), sa.ForeignKey("sitok_facility.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("half", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False, server_default="정기"),
        sa.Column("plan_date", sa.Date(), nullable=False, index=True),
        sa.Column("source", sa.Text(), nullable=False, server_default="auto"),
        sa.Column("memo", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("sitok_visit")
