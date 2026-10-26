"""치장벽돌 결함 정보(2026-10-26 민재형 "결함조사에서 부재를 치장벽돌로 선택하면 수직연속인지 층간구분인지 선택, 교체·보수는 AI가 판단하고 점검자가 변경") — sitok_defect.brick.

{"type": "수직연속"|"층간구분", "grade": 2~5(2 보수·3 보강·4 교체·5 즉시 교체), "by": "AI"|점검자 이름, "why": AI 근거}. 1.7 외부 치장벽돌 점검 현황 표(실수·상태등급)에 씀.

Revision ID: 0066
Revises: 0065
Create Date: 2026-10-26
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0066"
down_revision: Union[str, None] = "0065"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_defect", sa.Column("brick", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sitok_defect", "brick")
