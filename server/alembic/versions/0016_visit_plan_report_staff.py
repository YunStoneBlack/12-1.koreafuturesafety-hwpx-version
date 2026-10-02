"""방문 예정의 보고서 담당자(visit_plan.report_staff_id) — 실제 출장자(staff_id)와 보고서에 이름이 들어갈 사람을 가른다(2026-10-02).

출장은 누가 몇 곳을 가든(회사 하루 = 요원 수 × 4곳), 보고서는 한 사람 하루 4곳(core/staff_load.py) — 예정마다 보고서 담당자를 미리 정해
달력 카드에 "보고서 담당자: ○○○"로 보이고, 그 예정으로 보고서를 만들면 이 사람으로 시작한다(server/api/report_staff.py).
기존 예정은 이 마이그레이션 뒤 server/scripts/fill_report_staff.py로 채운다.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-02
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("visit_plan", sa.Column("report_staff_id", sa.Integer(),
                                          sa.ForeignKey("staff.id", ondelete="SET NULL"), nullable=True))


def downgrade() -> None:
    op.drop_column("visit_plan", "report_staff_id")
