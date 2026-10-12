"""시특법 시설물 목록 — 번호·담당자·계약 구분·열람 기록(2026-10-13).

사용자·민재형 10/13: 산안법 현장 목록과 같게(번호표 "26-4", 최근 열람순/번호순, 📞 전화·📍 지도, 민간/관급 거르기) +
시설물 목록함 구분 장기·지속계약 / 1회성·입찰계약 / 지속계약 종료.

Revision ID: 0042
Revises: 0041
Create Date: 2026-10-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0042"
down_revision: Union[str, None] = "0041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for name in ("mgmt_no", "contact_name", "contact_phone"):
        op.add_column("sitok_facility", sa.Column(name, sa.Text(), nullable=False, server_default=""))
    op.add_column("sitok_facility", sa.Column("contract_type", sa.Text(), nullable=False, server_default="1회성"))
    op.create_table(
        "sitok_view",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("facility_id", sa.Integer(), sa.ForeignKey("sitok_facility.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("viewed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("sitok_view")
    for name in ("contract_type", "contact_phone", "contact_name", "mgmt_no"):
        op.drop_column("sitok_facility", name)
