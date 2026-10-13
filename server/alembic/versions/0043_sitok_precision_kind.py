"""시특법 정밀안전점검 ① — 회차 종류(정기/정밀) · 보고서 쪽 계약 회차 줄 · 결함 깊이(2026-10-13 밤, 사용자 "시작").

- sitok_report.kind: "정기" / "정밀" — 계약서의 그 반기 줄에서 자동, 틀리면 직접(민재형).
- sitok_contract.rounds: 서류 자동화 계약의 회차 줄 [{year, half, kind, amount}]을 보고서 쪽 계약에도 둠(예전엔 옮길 때 kind가 버려짐).
- sitok_defect.depth: 박리(0.5/1.0/2.5mm)·박락·층분리(15/20/25mm)는 깊이 기준이라 결함현황표에 깊이 칸(민재형 "추가해야").

Revision ID: 0043
Revises: 0042
Create Date: 2026-10-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0043"
down_revision: Union[str, None] = "0042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_report", sa.Column("kind", sa.Text(), nullable=False, server_default="정기"))
    op.add_column("sitok_contract", sa.Column("rounds", sa.JSON(), nullable=True))
    op.add_column("sitok_defect", sa.Column("depth", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("sitok_defect", "depth")
    op.drop_column("sitok_contract", "rounds")
    op.drop_column("sitok_report", "kind")
