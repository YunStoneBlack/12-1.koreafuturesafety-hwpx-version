"""현장 첫 지도 회차(site_contact.first_visit_no, 2026-10-01) — 이 시스템을 쓰기 전에 이미 다녀온 회차가 있는 현장(예: 30회 중 1~7회는 예전에 함)을
등록할 때 "첫 지도 회차 8"로 적으면, 보고서가 아직 없어도 7회 다녀온 것으로 보고 자동 배치·진행 막대를 계산하고 첫 보고서를 8회차로 만든다.
웹판 전용 표에 둬서 데스크톱 프로그램·보고서 표지와 무관. 기본 1.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-01
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("site_contact", sa.Column("first_visit_no", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("site_contact", "first_visit_no")
