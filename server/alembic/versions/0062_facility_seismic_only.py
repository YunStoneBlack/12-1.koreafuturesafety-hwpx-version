"""내진성능평가 전용 건물(2026-10-21 사용자 "내진성능평가는 시특법 대상 시설물에 하는 과업이 아니야, 완전히 별도의 용역") — sitok_facility.seismic_only.
보고서 자동화 왼쪽 메뉴 "내진성능평가"에서 용역계약서·건축물대장으로 만든 건물(시특법 시설물 목록·서류·묶음·제출 현황·달력에서 빠짐).
건 하나 = 숨김 건물 + 성능평가 회차 하나(반기 칸·종류 "성능평가") — 현장 조사·철근탐사·보고서 만들기는 회차 그대로 씀(server/api/routers/seismic.py).

Revision ID: 0062
Revises: 0061
Create Date: 2026-10-21
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0062"
down_revision: Union[str, None] = "0061"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_facility", sa.Column("seismic_only", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("sitok_facility", "seismic_only")
