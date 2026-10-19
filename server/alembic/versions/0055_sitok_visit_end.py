"""방문 일정을 범위로(2026-10-19 민재형 "일정을 범위 설정 가능하도록, 디폴트 10.30~10.30") — sitok_visit.plan_end(끝 날, 비면 시작 날과 같은 하루).

Revision ID: 0055
Revises: 0054
Create Date: 2026-10-19
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0055"
down_revision: Union[str, None] = "0054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sitok_visit", sa.Column("plan_end", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("sitok_visit", "plan_end")
