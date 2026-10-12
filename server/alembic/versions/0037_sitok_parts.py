"""시특법 회차 공중이용·기타시설 사진(sitok_report.parts) — 2026-10-12.

현장 화면 [공중이용]·[기타시설] 탭(사용자 10/12): 공중이용 = 추락방지시설·도로포장·도로부 신축이음부·환기구 등의 덮개 항목마다 사진 한 장 또는 해당없음,
기타시설 = 마감재 2장·부착물 등 2장. 보고서 1.3 6)·7) 사진 표(각 4칸)와 AI 초안(조사항목·상태평가기준으로 판단)에 씀.

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: Union[str, None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_report", sa.Column("parts", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sitok_report", "parts")
