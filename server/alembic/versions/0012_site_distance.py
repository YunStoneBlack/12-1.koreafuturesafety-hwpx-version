"""현장 사이 도로 거리(site_distance) — 카카오모빌리티 자동차 길찾기 거리(km, 2026-10-01). 직선거리 대신 이걸로 묶는다(사용자 "네비 기준").
운전 시간은 묻는 시각의 교통에 따라 달라 저장·사용하지 않는다(사용자 결정). site_a < site_b, 좌표가 바뀌면 다시 묻는다(lat/lng 함께 저장).

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-01
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "site_distance",
        sa.Column("site_a", sa.Integer(), sa.ForeignKey("site.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("site_b", sa.Integer(), sa.ForeignKey("site.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("coords", sa.Text(), nullable=False, server_default=""),
        sa.Column("road_km", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("site_distance")
