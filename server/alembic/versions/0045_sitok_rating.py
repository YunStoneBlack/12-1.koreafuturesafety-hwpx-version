"""시특법 정밀안전점검 ③ — 상태평가 입력(표본층별 부재 전체 개수·전회차 등급·메모) JSON 한 칸(2026-10-13 밤).

sitok_report.rating: {counts: {"-3": {"기둥": 48, …}}, prev_grade: "B", note: ""}. 결과(층·부재 점수, 상태·변위·종합)는 server/sitok/condition.py가
결함현황표·재료시험(tests)·이 개수로 그때그때 계산(저장 안 함).

Revision ID: 0045
Revises: 0044
Create Date: 2026-10-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0045"
down_revision: Union[str, None] = "0044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_report", sa.Column("rating", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sitok_report", "rating")
