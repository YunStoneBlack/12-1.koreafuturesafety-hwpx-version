"""결함조사만(2026-10-21 사용자) — sitok_facility.survey_only. 보고서 틀이 아직 없는 시설물도 현장 결함조사만 쓰도록
보고서 자동화 왼쪽 메뉴 "결함조사"에서 만든 숨김 시설물(시설물 목록·서류·묶음·제출 현황·달력에서 빠짐). 층 탭 추가·숨김은 ledger(units_extra·units_hidden)라 칸 없음.

Revision ID: 0061
Revises: 0060
Create Date: 2026-10-21
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0061"
down_revision: Union[str, None] = "0060"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_facility", sa.Column("survey_only", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("sitok_facility", "survey_only")
