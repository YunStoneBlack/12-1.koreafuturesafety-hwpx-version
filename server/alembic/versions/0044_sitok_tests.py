"""시특법 정밀안전점검 ② — 회차 재료시험 입력(표본층·부재 규격·강도·탄산화·기울기·부등침하) JSON 한 칸(2026-10-13 밤).

sitok_report.tests: {sample, sections, strength, carbonation, tilt, settlement} — 계산(등급·잔존수명·1/N)은 server/sitok/tests.py가 저장할 때 다시 함.

Revision ID: 0044
Revises: 0043
Create Date: 2026-10-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0044"
down_revision: Union[str, None] = "0043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_report", sa.Column("tests", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sitok_report", "tests")
