"""정밀안전점검·정밀안전진단 도래주기(2026-10-20 민재형 — 시행령 별표 3, 계약서 쓸 때 실시할 점검을 넣음) — sitok_facility에
class_no(종별 "1종"/"2종"/"3종", 비면 보고서 틀로 짐작) · safety_grade(안전등급 A~E, 비면 최근 보고서) · last_precision·last_diagnosis(전회차 정밀안전점검·
정밀안전진단 완료일 — 우리 회차 기록이 없을 때 사람이 넣음) · precision_first·diagnosis_first(아직 한 적 없음 — 준공일로 최초 시기).

Revision ID: 0056
Revises: 0055
Create Date: 2026-10-20
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0056"
down_revision: Union[str, None] = "0055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_facility", sa.Column("class_no", sa.Text(), nullable=False, server_default=""))
    op.add_column("sitok_facility", sa.Column("safety_grade", sa.Text(), nullable=False, server_default=""))
    op.add_column("sitok_facility", sa.Column("last_precision", sa.Date(), nullable=True))
    op.add_column("sitok_facility", sa.Column("last_diagnosis", sa.Date(), nullable=True))
    op.add_column("sitok_facility", sa.Column("precision_first", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("sitok_facility", sa.Column("diagnosis_first", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    for c in ("diagnosis_first", "precision_first", "last_diagnosis", "last_precision", "safety_grade", "class_no"):
        op.drop_column("sitok_facility", c)
