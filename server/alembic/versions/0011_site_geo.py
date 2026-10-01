"""현장 좌표(site_geo) — 카카오 로컬 API로 찾은 위도·경도(2026-10-01). 자동 배치·일정 변경에서 같은 시·군이라도 먼 현장은 안 묶고,
다른 시·군이라도 아주 가까우면 자리가 없을 때 묶는다(server/api/geocode.py, visit_scheduler.py).

address = 좌표를 찾을 때 쓴 주소(지도 방문 주소, 없으면 현장 주소) — 바뀌면 다시 찾는다. precise = 번지·도로명·읍면까지 찾았는지(시·군 중심이면 거리 안 씀).

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-01
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "site_geo",
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("site.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("address", sa.Text(), nullable=False, server_default=""),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("precise", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("found", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("site_geo")
